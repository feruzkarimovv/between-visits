"""Table rows → response models (docs/03 shapes)."""

from datetime import date

from sqlmodel import Session, select

from app import content
from app.models import Answer, CheckIn, DraftEntry, Escalation, Finding, Patient, SAEReport
from app.schemas import (
    AnswerOut,
    CheckInDetail,
    CheckInOut,
    DraftOut,
    EscalationOut,
    EvidenceOut,
    FindingOut,
    InterviewStateOut,
    NextDue,
    PatientBrief,
    PatientSummary,
    SAEOut,
    TranscriptTurn,
)
from app.services import escalation as esc_svc
from app.timeutil import ensure_utc, utcnow


def patient_brief(p: Patient) -> PatientBrief:
    return PatientBrief(
        id=p.id, subject_id=p.subject_id, first_name=p.first_name, last_name=p.last_name, language=p.language,
        pace=p.pace, caregiver_name=p.caregiver_name,
    )


def next_due(p: Patient, schedule: list[int], today: date) -> NextDue | None:
    best: NextDue | None = None
    for d in p.dose_dates or []:
        dose = date.fromisoformat(d)
        for day in schedule:
            when = dose.fromordinal(dose.toordinal() + day)
            if when >= today and (best is None or when < best.date):
                best = NextDue(day_after_dose=day, date=when)
    return best


def patient_summary(session: Session, p: Patient, schedule: list[int], today: date) -> PatientSummary:
    last = session.exec(
        select(CheckIn).where(CheckIn.patient_id == p.id, CheckIn.status != "scheduled").order_by(CheckIn.created_at.desc())  # type: ignore[attr-defined]
    ).first()
    open_n = len(
        session.exec(
            select(Escalation).where(Escalation.patient_id == p.id, Escalation.status == "open")
        ).all()
    )
    return PatientSummary(
        id=p.id, subject_id=p.subject_id, first_name=p.first_name, last_name=p.last_name, age=p.age, sex=p.sex,
        language=p.language, pace=p.pace, hearing=p.hearing, caregiver_name=p.caregiver_name,
        caregiver_relation=p.caregiver_relation, caregiver_may_answer=p.caregiver_may_answer,
        next_due=next_due(p, schedule, today), last_checkin_status=last.status if last else None,
        open_escalations=open_n,
    )


def checkin_out(c: CheckIn) -> CheckInOut:
    st = c.interview_state or {}
    return CheckInOut(
        id=c.id, patient_id=c.patient_id, status=c.status, channel=c.channel, language=c.language, pace=c.pace,
        agent_variant=c.agent_variant, day_after_dose=c.day_after_dose, scheduled_for=c.scheduled_for,
        speaker=c.speaker, started_at=c.started_at, ended_at=c.ended_at, duration_s=c.duration_s,
        termination_reason=c.termination_reason, el_conversation_id=c.el_conversation_id, summary_en=c.summary_en,
        postcall_status=c.postcall_status, created_at=c.created_at,
        interview_state=InterviewStateOut(
            current=st.get("current"), asked=st.get("asked", []), queue=st.get("queue", []),
            escalated=bool(st.get("escalated")), closed=bool(st.get("closed")),
        ),
    )


def answer_out(a: Answer) -> AnswerOut:
    return AnswerOut(**a.model_dump(include=set(AnswerOut.model_fields)))


def finding_out(f: Finding) -> FindingOut:
    return FindingOut(**f.model_dump(include=set(FindingOut.model_fields)))


def escalation_out(session: Session, e: Escalation, with_patient: bool = False) -> EscalationOut:
    labels = [content.red_flag(f)["label_en"] if content.has_red_flag(f) else f for f in e.red_flag_ids or []]
    to_ack = None
    if e.acknowledged_at:
        to_ack = int((ensure_utc(e.acknowledged_at) - ensure_utc(e.paged_at or e.created_at)).total_seconds())  # type: ignore[operator]
    p = session.get(Patient, e.patient_id) if with_patient else None
    return EscalationOut(
        id=e.id, checkin_id=e.checkin_id, patient_id=e.patient_id, level=e.level, status=e.status, reason=e.reason,
        red_flag_ids=e.red_flag_ids or [], red_flag_labels=labels, summary_en=e.summary_en,
        patient_language=e.patient_language, created_at=e.created_at, paged_at=e.paged_at,
        page_channel=e.page_channel, page_target_name=e.page_target_name, repage_count=e.repage_count,
        backup_paged_at=e.backup_paged_at, acknowledged_at=e.acknowledged_at, acknowledged_by=e.acknowledged_by,
        ack_method=e.ack_method, resolved_at=e.resolved_at, resolution_note=e.resolution_note,
        seconds_open=esc_svc.seconds_open(e), seconds_to_ack=max(0, to_ack) if to_ack is not None else None,
        patient=patient_brief(p) if p else None,
    )


def draft_out(session: Session, d: DraftEntry, with_patient: bool = False) -> DraftOut:
    sae = session.exec(select(SAEReport).where(SAEReport.draft_entry_id == d.id)).first()
    p = session.get(Patient, d.patient_id) if with_patient else None
    return DraftOut(
        id=d.id, checkin_id=d.checkin_id, patient_id=d.patient_id, kind=d.kind, status=d.status, payload=d.payload,
        evidence=[EvidenceOut(**{k: ev.get(k) for k in EvidenceOut.model_fields}) for ev in d.evidence or []],
        reviewed_by=d.reviewed_by, reviewed_at=d.reviewed_at, review_note=d.review_note,
        investigator=d.investigator, created_at=d.created_at, sae_report_id=sae.id if sae else None,
        patient=patient_brief(p) if p else None,
    )


def sae_out(session: Session, r: SAEReport, with_patient: bool = True) -> SAEOut:
    p = session.get(Patient, r.patient_id) if with_patient else None
    secs = int((ensure_utc(r.due_at) - utcnow()).total_seconds())  # type: ignore[operator]
    return SAEOut(
        id=r.id, draft_entry_id=r.draft_entry_id, patient_id=r.patient_id, checkin_id=r.checkin_id, status=r.status,
        aware_at=r.aware_at, due_at=r.due_at, seconds_until_due=secs, payload=r.payload,
        narrative_ai_draft=r.narrative_ai_draft, narrative_final=r.narrative_final, signed_by=r.signed_by,
        signed_at=r.signed_at, sent_at=r.sent_at, sponsor_received_at=r.sponsor_received_at,
        created_at=r.created_at, patient=patient_brief(p) if p else None,
    )


def checkin_detail(session: Session, c: CheckIn) -> CheckInDetail:
    p = session.get(Patient, c.patient_id)
    assert p is not None
    answers = session.exec(select(Answer).where(Answer.checkin_id == c.id).order_by(Answer.created_at)).all()  # type: ignore[arg-type]
    findings = session.exec(select(Finding).where(Finding.checkin_id == c.id)).all()
    escs = session.exec(select(Escalation).where(Escalation.checkin_id == c.id).order_by(Escalation.created_at)).all()  # type: ignore[arg-type]
    drs = session.exec(select(DraftEntry).where(DraftEntry.checkin_id == c.id).order_by(DraftEntry.created_at)).all()  # type: ignore[arg-type]
    findings_sorted = sorted(findings, key=lambda f: (-(f.provisional_grade or 0), f.term))
    current = None
    st = c.interview_state or {}
    if st.get("current") and not st.get("closed"):
        try:
            from app.services import interview

            current = interview.current_say(session, c)
        except Exception:  # noqa: BLE001
            current = None
    return CheckInDetail(
        checkin=checkin_out(c),
        patient=patient_brief(p),
        answers=[answer_out(a) for a in answers],
        findings=[finding_out(f) for f in findings_sorted],
        escalations=[escalation_out(session, e) for e in escs],
        drafts=[draft_out(session, d) for d in drs],
        transcript=[TranscriptTurn(**{k: t.get(k) for k in TranscriptTurn.model_fields}) for t in c.transcript or []],
        current_question=current,
    )
