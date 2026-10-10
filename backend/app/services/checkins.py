"""Creating and starting check-ins (phone, web, inbound, replay)."""

import logging
from datetime import timedelta

from sqlmodel import Session, select

from app.audit import write_audit
from app.errors import ApiError
from app.ids import new_id
from app.models import CheckIn, CheckInPlan, Patient, Study
from app.seed import due_day, today_local, variant_for
from app.services import elevenlabs, interview
from app.timeutil import ensure_utc, utcnow

log = logging.getLogger("bv.checkins")

LIVE = ("dialing", "in_progress")
STALE_AFTER = timedelta(minutes=30)


def live_checkin(session: Session, patient_id: str) -> CheckIn | None:
    rows = session.exec(select(CheckIn).where(CheckIn.patient_id == patient_id, CheckIn.status.in_(LIVE))).all()  # type: ignore[attr-defined]
    now = utcnow()
    for c in rows:
        if now - ensure_utc(c.started_at or c.created_at) < STALE_AFTER:  # type: ignore[operator]
            return c
        c.status = "failed"  # a call that never finished: don't block new check-ins forever
        c.termination_reason = c.termination_reason or "stale: no call activity for 30 minutes"
        session.add(c)
    return None


def active_plan(session: Session) -> tuple[Study, CheckInPlan]:
    study = session.exec(select(Study)).first()
    if study is None:
        raise ApiError(503, "not_seeded", "Database is empty; run `make seed`.")
    plan = session.get(CheckInPlan, study.active_plan_id) if study.active_plan_id else None
    if plan is None:
        raise ApiError(503, "no_active_plan", "No approved check-in plan.")
    return study, plan


def new_checkin(
    session: Session, patient: Patient, channel: str, day_after_dose: int | None, actor: str, role: str
) -> CheckIn:
    """Reuse today's scheduled check-in for the patient if there is one, else create a new one."""
    if live_checkin(session, patient.id):
        raise ApiError(409, "checkin_in_progress", "This patient already has a live check-in.")
    study, plan = active_plan(session)
    if day_after_dose is None:
        day_after_dose = due_day(patient.dose_dates, plan.schedule_days_after_dose, today_local())
    sched = session.exec(
        select(CheckIn).where(CheckIn.patient_id == patient.id, CheckIn.status == "scheduled")
    ).first()
    c = sched or CheckIn(id=new_id("ci"), patient_id=patient.id, study_id=study.id, plan_id=plan.id)
    c.plan_id = plan.id
    c.channel = channel
    c.day_after_dose = day_after_dose if day_after_dose is not None else c.day_after_dose
    c.language, c.pace = patient.language, patient.pace
    c.agent_variant = variant_for(patient.language, patient.pace)
    c.status = "dialing"
    c.created_at = utcnow()
    interview.start(c, plan)
    session.add(c)
    write_audit(session, actor=actor, role=role, action="checkin.started", entity_type="CheckIn", entity_id=c.id,
                after={"channel": channel, "variant": c.agent_variant}, checkin_id=c.id)
    session.flush()
    return c


def start_phone(session: Session, c: CheckIn, patient: Patient) -> None:
    study = session.get(Study, c.study_id)
    try:
        cl = elevenlabs.client()
        agent_id = elevenlabs.agent_id_for(c.agent_variant)
    except elevenlabs.TelephonyUnavailable as e:
        raise ApiError(503, "telephony_unavailable", str(e)) from e
    c.el_agent_id = agent_id
    dyn = elevenlabs.dynamic_variables(c, patient, study)
    try:
        res = cl.outbound_call(agent_id, patient.phone_e164, patient.subject_id, dyn)
    except Exception as e:  # noqa: BLE001
        c.status = "failed"
        c.termination_reason = f"outbound call failed: {e}"[:500]
        session.add(c)
        session.commit()
        log.error("outbound_call_failed checkin_id=%s error=%s", c.id, e)
        raise ApiError(502, "call_failed", str(e)[:300]) from e
    c.el_conversation_id = res.conversation_id
    c.twilio_call_sid = res.call_sid
    session.add(c)
    log.info("outbound_call checkin_id=%s conversation_id=%s", c.id, res.conversation_id)


def start_web(session: Session, c: CheckIn, patient: Patient) -> dict:
    study = session.get(Study, c.study_id)
    try:
        cl = elevenlabs.client()
        agent_id = elevenlabs.agent_id_for(c.agent_variant)
        tok = cl.web_token(agent_id)
    except elevenlabs.TelephonyUnavailable as e:
        raise ApiError(503, "telephony_unavailable", str(e)) from e
    except Exception as e:  # noqa: BLE001
        c.status = "failed"
        c.termination_reason = f"web token failed: {e}"[:500]
        session.add(c)
        session.commit()
        raise ApiError(502, "call_failed", str(e)[:300]) from e
    c.el_agent_id = agent_id
    c.el_conversation_id = tok.conversation_id
    session.add(c)
    return {
        "agent_id": agent_id,
        "conversation_token": tok.token,
        "conversation_id": tok.conversation_id,
        "dynamic_variables": elevenlabs.dynamic_variables(c, patient, study),
        "user_id": patient.subject_id,
    }
