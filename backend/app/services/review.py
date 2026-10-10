"""Human review of drafts: edit, confirm, reject, investigator assessment. Every action is audited (REQ-010)."""

from typing import Any

from sqlmodel import Session

from app.audit import write_audit
from app.errors import ApiError
from app.models import DraftEntry, SAEReport
from app.schemas import InvestigatorIn
from app.services import sae
from app.timeutil import iso, utcnow


def _snapshot(d: DraftEntry) -> dict[str, Any]:
    return {"status": d.status, "payload": dict(d.payload or {})}


def edit(session: Session, d: DraftEntry, patch: dict[str, Any], note: str | None, user: str, role: str) -> DraftEntry:
    if d.status != "draft":
        raise ApiError(409, "not_editable", f"Draft is {d.status}; only drafts can be edited.")
    before = _snapshot(d)
    d.payload = {**(d.payload or {}), **patch}
    session.add(d)
    write_audit(session, actor=user, role=role, action="draft.edited", entity_type="DraftEntry", entity_id=d.id,
                before=before, after=_snapshot(d), note=note, checkin_id=d.checkin_id)
    return d


def confirm(session: Session, d: DraftEntry, note: str | None, user: str, role: str) -> DraftEntry:
    if d.status != "draft":
        raise ApiError(409, "not_draft", f"Draft is already {d.status}.")
    before = _snapshot(d)
    d.status = "confirmed"
    d.reviewed_by, d.reviewed_at, d.review_note = user, utcnow(), note
    session.add(d)
    write_audit(session, actor=user, role=role, action="draft.confirmed", entity_type="DraftEntry", entity_id=d.id,
                before=before, after=_snapshot(d), note=note, checkin_id=d.checkin_id)
    return d


def reject(session: Session, d: DraftEntry, reason: str, user: str, role: str) -> DraftEntry:
    if d.status != "draft":
        raise ApiError(409, "not_draft", f"Draft is already {d.status}.")
    if not reason.strip():
        raise ApiError(422, "reason_required", "A reason is required to reject a draft.")
    before = _snapshot(d)
    d.status = "rejected"
    d.reviewed_by, d.reviewed_at, d.review_note = user, utcnow(), reason
    session.add(d)
    write_audit(session, actor=user, role=role, action="draft.rejected", entity_type="DraftEntry", entity_id=d.id,
                before=before, after=_snapshot(d), note=reason, checkin_id=d.checkin_id)
    return d


def investigator(session: Session, d: DraftEntry, body: InvestigatorIn, user: str) -> SAEReport | None:
    if d.kind != "AE" or d.status != "confirmed":
        raise ApiError(409, "not_confirmed_ae", "Seriousness and relatedness apply to confirmed AE drafts only.")
    if body.is_serious and not body.seriousness_criteria:
        raise ApiError(422, "criteria_required", "Pick at least one seriousness criterion for a serious event.")
    before = {"investigator": d.investigator}
    now = utcnow()
    d.investigator = {
        "is_serious": body.is_serious,
        "seriousness_criteria": list(body.seriousness_criteria) if body.is_serious else [],
        "relatedness": body.relatedness,
        "signed_by": user if body.sign else None,
        "signed_at": iso(now) if body.sign else None,
    }
    session.add(d)
    write_audit(session, actor=user, role="investigator", action="draft.investigator_assessed",
                entity_type="DraftEntry", entity_id=d.id, before=before, after={"investigator": d.investigator},
                checkin_id=d.checkin_id)
    if body.is_serious:
        return sae.create_for(session, d, user)
    return None
