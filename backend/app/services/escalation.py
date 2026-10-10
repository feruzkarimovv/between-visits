"""Escalations: create / add-to / raise, page the nurse, acknowledge, resolve, re-page loop.

Ladder (docs/05 § 4): a red flag at the same or lower level than an open page is added to it (no
second page); a higher level raises the escalation and re-pages. `callback` escalations are tasks,
never paged. Pages go out synchronously, before the tool call returns to the agent (REQ-005).
"""

import asyncio
import logging
import secrets
from datetime import timedelta
from typing import Any

from sqlmodel import Session, select

from app.audit import write_audit
from app.config import get_settings
from app.db import new_session
from app.ids import new_id
from app.models import CheckIn, Escalation, Patient
from app.services import clinical, pager, rules
from app.timeutil import ensure_utc, utcnow

log = logging.getLogger("bv.escalation")

PAGED_LEVELS = ("urgent", "emergency")


def open_page_escalation(session: Session, checkin_id: str) -> Escalation | None:
    """Highest-level unresolved urgent/emergency escalation for the check-in."""
    rows = session.exec(
        select(Escalation).where(
            Escalation.checkin_id == checkin_id,
            Escalation.status != "resolved",
            Escalation.level.in_(PAGED_LEVELS),  # type: ignore[attr-defined]
        )
    ).all()
    return max(rows, key=lambda e: rules.LEVEL_RANK[e.level], default=None)


def _page_values(session: Session, checkin_id: str, patient: Patient) -> dict[str, Any]:
    amap = clinical.answers_map(clinical.answers_for(session, checkin_id))
    return clinical.page_values(amap, clinical.baseline_of(patient))


def summary_for(session: Session, esc: Escalation, patient: Patient) -> str:
    if esc.level in PAGED_LEVELS:
        return pager.findings_sentence(esc.red_flag_ids, _page_values(session, esc.checkin_id, patient))
    return esc.summary_en


def page(session: Session, esc: Escalation, patient: Patient, *, backup: bool = False, actor: str = "system") -> bool:
    """Send a page now. Never raises: on failure logs, leaves paged state unchanged (the re-page loop retries)."""
    msg = pager.build_message(
        escalation_id=esc.id,
        level=esc.level,
        subject_id=patient.subject_id,
        language=esc.patient_language,
        flag_ids=esc.red_flag_ids,
        values=_page_values(session, esc.checkin_id, patient),
        ack_token=esc.ack_token,
        backup=backup,
    )
    try:
        res = pager.send(msg)
    except Exception as e:  # noqa: BLE001  fail safe: log, keep the escalation open, retry later
        log.error("page_failed escalation_id=%s checkin_id=%s error=%r", esc.id, esc.checkin_id, e)
        write_audit(
            session, actor=actor, role="system", action="escalation.page_failed", entity_type="Escalation",
            entity_id=esc.id, note=str(e)[:500], checkin_id=esc.checkin_id,
        )
        return False
    now = utcnow()
    if backup:
        esc.backup_paged_at = now
    else:
        esc.paged_at = esc.paged_at or now
        esc.page_channel = res.channel
        esc.page_target_name = res.target_name
        esc.page_ref = res.ref
    esc.last_paged_at = now
    session.add(esc)
    log.info(
        "paged escalation_id=%s checkin_id=%s level=%s channel=%s backup=%s ref=%s",
        esc.id, esc.checkin_id, esc.level, res.channel, backup, res.ref,
    )
    write_audit(
        session, actor=actor, role="system", action="escalation.backup_paged" if backup else "escalation.paged",
        entity_type="Escalation", entity_id=esc.id, after={"channel": res.channel, "ref": res.ref, "level": esc.level},
        checkin_id=esc.checkin_id,
    )
    return True


def escalate_flags(
    session: Session,
    checkin: CheckIn,
    patient: Patient,
    hits: list[rules.RedFlagHit],
    reason: str,
    actor: str = "agent",
) -> tuple[str, Escalation | None]:
    """Escalate red-flag hits that no escalation on this check-in covers yet.

    Returns (outcome, escalation) with outcome in none | new | added | raised."""
    known = clinical.all_escalated_flag_ids(session, checkin.id)
    new_hits = [h for h in hits if h.id not in known and h.level in PAGED_LEVELS]
    if not new_hits:
        return "none", None
    level = rules.level_for(new_hits)
    ids = [h.id for h in new_hits]
    existing = open_page_escalation(session, checkin.id)
    if existing and rules.LEVEL_RANK[existing.level] >= rules.LEVEL_RANK[level]:
        before = {"red_flag_ids": list(existing.red_flag_ids)}
        existing.red_flag_ids = [*existing.red_flag_ids, *ids]
        existing.summary_en = summary_for(session, existing, patient)
        session.add(existing)
        write_audit(
            session, actor=actor, role="agent" if actor == "agent" else "system", action="escalation.flags_added",
            entity_type="Escalation", entity_id=existing.id, before=before,
            after={"red_flag_ids": existing.red_flag_ids}, checkin_id=checkin.id,
        )
        log.info("escalation_added escalation_id=%s checkin_id=%s flags=%s", existing.id, checkin.id, ids)
        return "added", existing
    if existing:
        before = {"level": existing.level, "status": existing.status, "red_flag_ids": list(existing.red_flag_ids)}
        existing.level = level
        existing.red_flag_ids = [*existing.red_flag_ids, *ids]
        existing.status = "open"
        existing.acknowledged_at = None
        existing.acknowledged_by = None
        existing.ack_method = None
        existing.repage_count = 0
        existing.summary_en = summary_for(session, existing, patient)
        session.add(existing)
        write_audit(
            session, actor=actor, role="system", action="escalation.raised", entity_type="Escalation",
            entity_id=existing.id, before=before,
            after={"level": level, "red_flag_ids": existing.red_flag_ids}, checkin_id=checkin.id,
        )
        session.flush()
        page(session, existing, patient, actor=actor)
        return "raised", existing
    esc = Escalation(
        id=new_id("esc"),
        checkin_id=checkin.id,
        patient_id=patient.id,
        level=level,
        red_flag_ids=ids,
        reason=reason,
        patient_language=checkin.language,
        ack_token=secrets.token_urlsafe(24),
    )
    esc.summary_en = summary_for(session, esc, patient)
    session.add(esc)
    session.flush()
    write_audit(
        session, actor=actor, role="system", action="escalation.created", entity_type="Escalation",
        entity_id=esc.id, after={"level": level, "red_flag_ids": ids, "reason": reason}, checkin_id=checkin.id,
    )
    page(session, esc, patient, actor=actor)
    return "new", esc


def create_callback(
    session: Session, checkin: CheckIn, patient: Patient, reason: str, summary_en: str, actor: str = "agent"
) -> Escalation:
    esc = Escalation(
        id=new_id("esc"),
        checkin_id=checkin.id,
        patient_id=patient.id,
        level="callback",
        reason=reason,
        summary_en=summary_en,
        patient_language=checkin.language,
        ack_token=secrets.token_urlsafe(24),
    )
    session.add(esc)
    write_audit(
        session, actor=actor, role="agent" if actor == "agent" else "system", action="escalation.created",
        entity_type="Escalation", entity_id=esc.id, after={"level": "callback", "reason": reason},
        checkin_id=checkin.id,
    )
    log.info("callback_created escalation_id=%s checkin_id=%s reason=%s", esc.id, checkin.id, reason)
    return esc


def acknowledge(session: Session, esc: Escalation, *, by: str, method: str, role: str = "nurse") -> Escalation:
    """Idempotent: acknowledging twice keeps the first acknowledgment."""
    if esc.status in ("acknowledged", "resolved"):
        return esc
    esc.status = "acknowledged"
    esc.acknowledged_at = utcnow()
    esc.acknowledged_by = by
    esc.ack_method = method
    session.add(esc)
    write_audit(
        session, actor=by, role=role, action="escalation.acknowledged", entity_type="Escalation", entity_id=esc.id,
        before={"status": "open"}, after={"status": "acknowledged", "ack_method": method}, checkin_id=esc.checkin_id,
    )
    log.info("acknowledged escalation_id=%s checkin_id=%s method=%s by=%s", esc.id, esc.checkin_id, method, by)
    return esc


def resolve(session: Session, esc: Escalation, *, by: str, role: str, note: str | None) -> Escalation:
    before = {"status": esc.status}
    if esc.status == "open":
        acknowledge(session, esc, by=by, method="dashboard", role=role)
    esc.status = "resolved"
    esc.resolved_at = utcnow()
    esc.resolution_note = note
    session.add(esc)
    write_audit(
        session, actor=by, role=role, action="escalation.resolved", entity_type="Escalation", entity_id=esc.id,
        before=before, after={"status": "resolved"}, note=note, checkin_id=esc.checkin_id,
    )
    return esc


def seconds_open(esc: Escalation) -> int:
    end = esc.acknowledged_at or esc.resolved_at or utcnow()
    return max(0, int((ensure_utc(end) - ensure_utc(esc.created_at)).total_seconds()))  # type: ignore[operator]


# ---- re-page loop -------------------------------------------------------------------------------------


def repage_due(session: Session, now=None) -> int:  # noqa: ANN001
    """Re-page open urgent/emergency escalations: never paged (retry), or unacknowledged after ACK_TIMEOUT.
    After 2 re-pages the backup contact is paged too. Returns the number of pages sent."""
    now = now or utcnow()
    timeout = timedelta(seconds=get_settings().ack_timeout_seconds)
    sent = 0
    rows = session.exec(
        select(Escalation).where(Escalation.status == "open", Escalation.level.in_(PAGED_LEVELS))  # type: ignore[attr-defined]
    ).all()
    for esc in rows:
        patient = session.get(Patient, esc.patient_id)
        if patient is None:
            continue
        if esc.paged_at is None:
            if esc.last_paged_at is None or now - ensure_utc(esc.last_paged_at) >= timedelta(seconds=10):  # type: ignore[operator]
                esc.last_paged_at = now  # throttle retries even when the page fails
                sent += page(session, esc, patient)
            continue
        if esc.last_paged_at and now - ensure_utc(esc.last_paged_at) < timeout:  # type: ignore[operator]
            continue
        esc.repage_count += 1
        write_audit(
            session, actor="system", role="system", action="escalation.repaged", entity_type="Escalation",
            entity_id=esc.id, after={"repage_count": esc.repage_count}, checkin_id=esc.checkin_id,
        )
        sent += page(session, esc, patient)
        if esc.repage_count >= 2 and esc.backup_paged_at is None:
            sent += page(session, esc, patient, backup=True)
        esc.last_paged_at = now
        session.add(esc)
    session.commit()
    return sent


async def repage_loop(interval_s: float = 10.0) -> None:
    while True:
        try:
            await asyncio.to_thread(_repage_once)
        except Exception as e:  # noqa: BLE001
            log.error("repage_loop_error %r", e)
        await asyncio.sleep(interval_s)


def _repage_once() -> None:
    with new_session() as s:
        repage_due(s)
