"""Draft entries (AE / CM / NURSE_TASK). Every draft carries evidence: verbatim quote, language, source."""

from typing import Any

from sqlmodel import Session, select

from app.audit import write_audit
from app.ids import new_id
from app.models import CheckIn, DraftEntry

TRANSLATION_LABEL = "AI translation, verify"


def evidence(
    quote: str,
    lang: str,
    source: str,
    *,
    t_s: float | None = None,
    turn_index: int | None = None,
    translation_en: str | None = None,
) -> dict[str, Any]:
    return {
        "quote": quote,
        "quote_lang": lang,
        "translation_en": translation_en,
        "translation_label": TRANSLATION_LABEL if translation_en else None,
        "t_s": t_s,
        "turn_index": turn_index,
        "source": source,
    }


def drafts_for(session: Session, checkin_id: str, kind: str | None = None) -> list[DraftEntry]:
    q = select(DraftEntry).where(DraftEntry.checkin_id == checkin_id)
    if kind:
        q = q.where(DraftEntry.kind == kind)
    return list(session.exec(q.order_by(DraftEntry.created_at)).all())  # type: ignore[arg-type]


def create_draft(
    session: Session,
    checkin: CheckIn,
    kind: str,
    payload: dict[str, Any],
    ev: list[dict[str, Any]],
    actor: str = "agent",
) -> DraftEntry:
    d = DraftEntry(
        id=new_id("dr"),
        checkin_id=checkin.id,
        patient_id=checkin.patient_id,
        kind=kind,
        payload=payload,
        evidence=ev,
    )
    session.add(d)
    write_audit(
        session, actor=actor, role="agent" if actor == "agent" else "system", action="draft.created",
        entity_type="DraftEntry", entity_id=d.id, after={"kind": kind, "payload": payload}, checkin_id=checkin.id,
    )
    return d


def nurse_task(
    session: Session, checkin: CheckIn, category: str, text_en: str, quote: str, lang: str, source: str = "live_tool"
) -> DraftEntry:
    return create_draft(
        session, checkin, "NURSE_TASK", {"category": category, "text_en": text_en},
        [evidence(quote, lang, source)], actor="agent" if source == "live_tool" else "system",
    )


def medication(
    session: Session, checkin: CheckIn, description: str, quote: str, lang: str, source: str = "live_tool"
) -> DraftEntry:
    """Create a CM draft, or append evidence to the most recent CM draft with the same description."""
    for d in drafts_for(session, checkin.id, "CM"):
        if d.status == "draft" and d.payload.get("medication_name", "").lower() == description.lower():
            d.evidence = [*d.evidence, evidence(quote, lang, source)]
            session.add(d)
            return d
    payload = {
        "medication_name": description,
        "otc": None,
        "indication_en": None,
        "start_date": None,
        "dose_text": None,
    }
    return create_draft(session, checkin, "CM", payload, [evidence(quote, lang, source)],
                        actor="agent" if source == "live_tool" else "system")
