"""Serious-event reports: create (24-hour clock), edit, sign, send to the mock sponsor inbox.

aware_at = first human acknowledgment of an escalation for the AE's check-in (the site became aware);
fallback: the AE's confirmation time. due_at = aware_at + 24h (example protocol p.106-107).
"""

import logging
from datetime import date, timedelta
from typing import Any

from sqlmodel import Session, select

from app import content
from app.audit import write_audit
from app.errors import ApiError
from app.models import CheckIn, DraftEntry, Escalation, Patient, SAEReport, Study
from app.schemas import SponsorInboxItem, ValidCaseChecks
from app.services import gemini, llm
from app.timeutil import ensure_utc, iso, local_date, utcnow

log = logging.getLogger("bv.sae")


def _aware_at(session: Session, d: DraftEntry):  # noqa: ANN202
    escs = session.exec(select(Escalation).where(Escalation.checkin_id == d.checkin_id)).all()
    linked = d.payload.get("escalation_id")
    acks = [ensure_utc(e.acknowledged_at) for e in escs if e.acknowledged_at and (not linked or e.id == linked)]
    if not acks:
        acks = [ensure_utc(e.acknowledged_at) for e in escs if e.acknowledged_at]
    if acks:
        return min(acks)
    return ensure_utc(d.reviewed_at) or utcnow()


def _last_dose(p: Patient, on: date) -> str | None:
    past = [d for d in p.dose_dates or [] if date.fromisoformat(d) <= on]
    return max(past) if past else None


def build_payload(session: Session, d: DraftEntry, user: str, aware_at, due_at) -> dict[str, Any]:  # noqa: ANN001
    p = session.get(Patient, d.patient_id)
    c = session.get(CheckIn, d.checkin_id)
    study = session.get(Study, c.study_id) if c else None
    assert p is not None and c is not None and study is not None
    pay = d.payload or {}
    inv = d.investigator or {}
    on = local_date(c.started_at or c.created_at)  # DISPLAY_TZ call date (docs/03 §6.4)
    cms = session.exec(
        select(DraftEntry).where(DraftEntry.patient_id == p.id, DraftEntry.kind == "CM", DraftEntry.status != "rejected")
    ).all()
    return {
        "report_type": "initial",
        "date_of_report": utcnow().date().isoformat(),
        "study": {"nct_id": study.nct_id, "site_id": study.site_id, "sponsor_study_number": study.sponsor_study_number},
        "patient": {"subject_id": p.subject_id, "initials": f"{p.first_name[:1]}.{p.last_name[:1]}.", "age": p.age,
                    "sex": p.sex, "country": "US"},
        "reaction": {
            "term": pay.get("term"), "onset_date": pay.get("onset_date") or on.isoformat(),
            "provisional_ctcae_grade": pay.get("provisional_grade"), "ctcae_version": content.ctcae_version(),
            "description": pay.get("verbatim_en"), "outcome": pay.get("outcome", "not_recovered"),
        },
        "seriousness": inv.get("seriousness_criteria", []),
        "suspect_product": {"description": f"Study drug ({study.drug_class})", "route": "intravenous",
                            "last_dose_date": _last_dose(p, on)},
        "concomitant": [
            {"medication": cm.payload.get("medication_name"), "start_date": cm.payload.get("start_date"),
             "otc": cm.payload.get("otc")} for cm in cms
        ],
        "causality": {"assessed_by": f"{user} (investigator)", "result": inv.get("relatedness")},
        "reporter": {"name": user, "role": "investigator", "site": study.site_name},
        "aware_at": iso(aware_at),
        "due_at": iso(due_at),
        "narrative": None,
        "narrative_ai_draft_used": False,
    }


def create_for(session: Session, d: DraftEntry, user: str) -> SAEReport:
    existing = session.exec(select(SAEReport).where(SAEReport.draft_entry_id == d.id)).first()
    if existing:
        return existing
    aware = _aware_at(session, d)
    due = aware + timedelta(hours=24)
    payload = build_payload(session, d, user, aware, due)
    quotes = [ev.get("quote", "") for ev in d.evidence or []]
    try:
        narrative = llm.draft_narrative(payload, quotes)
    except Exception as e:  # noqa: BLE001
        log.warning("narrative_fallback draft_id=%s error=%r", d.id, e)
        narrative = gemini.template_narrative(payload)
    from app.ids import new_id

    r = SAEReport(
        id=new_id("sae"), draft_entry_id=d.id, patient_id=d.patient_id, checkin_id=d.checkin_id, aware_at=aware,
        due_at=due, payload=payload, narrative_ai_draft=narrative,
    )
    session.add(r)
    write_audit(session, actor=user, role="investigator", action="sae.created", entity_type="SAEReport", entity_id=r.id,
                after={"aware_at": iso(aware), "due_at": iso(due)}, checkin_id=d.checkin_id)
    return r


def edit(session: Session, r: SAEReport, narrative_final: str | None, payload: dict[str, Any] | None,
         user: str, role: str) -> SAEReport:
    if r.status == "sent":
        raise ApiError(409, "already_sent", "This report was already sent to the sponsor.")
    before = {"narrative_final": r.narrative_final, "payload": r.payload, "status": r.status}
    if narrative_final is not None:
        r.narrative_final = narrative_final
    if payload:
        r.payload = {**r.payload, **payload}
    if r.status == "signed":
        r.status = "draft"  # edits after signing need a new signature
        r.signed_by = r.signed_at = None
    session.add(r)
    write_audit(session, actor=user, role=role, action="sae.edited", entity_type="SAEReport", entity_id=r.id,
                before=before, after={"narrative_final": r.narrative_final, "payload": r.payload, "status": r.status},
                checkin_id=r.checkin_id)
    return r


def sign(session: Session, r: SAEReport, user: str, role: str) -> SAEReport:
    if r.status == "sent":
        raise ApiError(409, "already_sent", "This report was already sent to the sponsor.")
    if not r.narrative_final:
        r.narrative_final = r.narrative_ai_draft
    used_ai = r.narrative_final.strip() == r.narrative_ai_draft.strip()
    r.payload = {**r.payload, "narrative": r.narrative_final, "narrative_ai_draft_used": used_ai}
    r.status, r.signed_by, r.signed_at = "signed", user, utcnow()
    session.add(r)
    write_audit(session, actor=user, role=role, action="sae.signed", entity_type="SAEReport", entity_id=r.id,
                after={"status": "signed"}, checkin_id=r.checkin_id)
    return r


def send(session: Session, r: SAEReport, user: str, role: str) -> SAEReport:
    if r.status != "signed":
        raise ApiError(409, "not_signed", "The investigator must sign the report before it is sent.")
    now = utcnow()
    r.status, r.sent_at, r.sponsor_received_at = "sent", now, now
    session.add(r)
    write_audit(session, actor=user, role=role, action="sae.sent", entity_type="SAEReport", entity_id=r.id,
                after={"status": "sent", "sent_at": iso(now)}, checkin_id=r.checkin_id)
    return r


def valid_case(payload: dict[str, Any]) -> ValidCaseChecks:
    pt, rep, sp, rx = (payload.get(k) or {} for k in ("patient", "reporter", "suspect_product", "reaction"))
    return ValidCaseChecks(
        identifiable_patient=bool(pt.get("subject_id") and (pt.get("age") or pt.get("sex"))),
        identifiable_reporter=bool(rep.get("name") and rep.get("role")),
        suspect_product=bool(sp.get("description")),
        adverse_event=bool(rx.get("term")),
    )


def inbox(session: Session) -> list[SponsorInboxItem]:
    rows = session.exec(select(SAEReport).where(SAEReport.status == "sent").order_by(SAEReport.sent_at.desc())).all()  # type: ignore[attr-defined]
    out = []
    for r in rows:
        p = r.payload
        received = ensure_utc(r.sponsor_received_at or r.sent_at)
        due = ensure_utc(r.due_at)
        assert received is not None and due is not None
        out.append(SponsorInboxItem(
            sae_id=r.id, received_at=received, due_at=due, on_time=received <= due,
            seconds_before_deadline=int((due - received).total_seconds()),
            study=p.get("study", {}).get("nct_id", ""), site=p.get("study", {}).get("site_id", ""),
            subject_id=p.get("patient", {}).get("subject_id", ""), event_term=p.get("reaction", {}).get("term", ""),
            seriousness_criteria=p.get("seriousness", []),
            provisional_grade=p.get("reaction", {}).get("provisional_ctcae_grade"),
            relatedness=p.get("causality", {}).get("result"), valid_case_checks=valid_case(p),
            narrative=r.narrative_final or r.narrative_ai_draft, report=p,
        ))
    return out
