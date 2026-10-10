"""Glue between stored answers and the pure rules engine: findings recompute and page values."""

from typing import Any

from sqlmodel import Session, select

from app import content
from app.ids import new_id
from app.models import Answer, CheckIn, Escalation, Finding, Patient
from app.services import rules
from app.timeutil import utcnow


def answers_for(session: Session, checkin_id: str) -> list[Answer]:
    return list(session.exec(select(Answer).where(Answer.checkin_id == checkin_id)).all())


def answers_map(answers: list[Answer]) -> rules.Answers:
    return {
        a.item_code: rules.AnswerInput(a.option_code, a.numeric_value, a.unit)
        for a in answers
        if content.has_item(a.item_code)
    }


def baseline_of(patient: Patient | None) -> dict[str, Any]:
    return dict(patient.baseline or {}) if patient else {}


def page_values(answers: rules.Answers, baseline: dict[str, Any]) -> dict[str, Any]:
    """Inputs the nurse page phrases may mention."""
    values: dict[str, Any] = {}
    sob = rules.derived_value("stools_over_baseline", answers, baseline)
    if sob is not None:
        values["stools_over_baseline"] = int(sob) if float(sob).is_integer() else sob
    t = answers.get("TEMP_HIGHEST")
    if t and t.numeric_value is not None and t.option_code not in rules.NON_VALUES - {None}:
        values["temp_c"] = round(rules.to_celsius(t.numeric_value, t.unit), 1)
    for code in ("STOOL_BLOOD", "SOB_EXERTION", "SOB_SEV"):
        a = answers.get(code)
        if a and a.option_code not in ("unknown", None):
            values[code] = a.option_code
    return values


def reported_flag_ids(session: Session, checkin: CheckIn) -> list[str]:
    return list((checkin.interview_state or {}).get("reported_flags", []))


def all_escalated_flag_ids(session: Session, checkin_id: str) -> set[str]:
    out: set[str] = set()
    for e in session.exec(select(Escalation).where(Escalation.checkin_id == checkin_id)).all():
        out |= set(e.red_flag_ids or [])
    return out


def recompute_findings(session: Session, checkin: CheckIn, patient: Patient, plan_flag_ids: list[str]) -> list[Finding]:
    """Recompute one Finding per term that has answers. Findings for absent symptoms are removed."""
    answers = answers_for(session, checkin.id)
    amap = answers_map(answers)
    baseline = baseline_of(patient)
    hits = rules.red_flags(amap, baseline, None, checkin.day_after_dose, plan_flag_ids)
    terms = {content.term_of(a.item_code) for a in answers if content.has_item(a.item_code)} - {None}
    existing = {f.term: f for f in session.exec(select(Finding).where(Finding.checkin_id == checkin.id)).all()}
    out: list[Finding] = []
    for term in sorted(t for t in terms if t):
        g = rules.grade(term, amap, baseline)
        present = rules.term_present(term, amap) or g.provisional_grade is not None
        term_hits = [h for h in hits if term in rules.flag_terms(h.id, h.inputs)]
        if not present and not term_hits:
            if term in existing:
                session.delete(existing[term])
            continue
        f = existing.get(term) or Finding(id=new_id("fnd"), checkin_id=checkin.id, term=term)
        f.provisional_grade = g.provisional_grade
        f.grade_basis = g.grade_basis
        f.rule_id = g.rule_id
        f.rule_text = g.rule_text
        f.inputs = dict(g.inputs)
        f.red_flag_ids = sorted(h.id for h in term_hits)
        f.escalation_level = rules.level_for(term_hits)
        f.answer_ids = [a.id for a in answers if content.has_item(a.item_code) and content.term_of(a.item_code) == term]
        f.updated_at = utcnow()
        session.add(f)
        out.append(f)
    return out


def current_hits(session: Session, checkin: CheckIn, patient: Patient, plan_flag_ids: list[str]) -> list[rules.RedFlagHit]:
    amap = answers_map(answers_for(session, checkin.id))
    return rules.red_flags(
        amap, baseline_of(patient), reported_flag_ids(session, checkin), checkin.day_after_dose, plan_flag_ids
    )
