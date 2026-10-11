"""Dashboard API (/api). Thin: logic lives in app/services/*."""

import json
from datetime import date

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, select

from app import content
from app.audit import write_audit
from app.config import ROOT, get_settings
from app.db import get_session
from app.errors import ApiError
from app.models import AuditEvent, CheckIn, CheckInPlan, DraftEntry, Escalation, Patient, SAEReport, Study
from app.schemas import (
    AuditOut,
    CheckInDetail,
    CheckInListItem,
    CheckInOut,
    ConfirmIn,
    CreateCheckInIn,
    CreateCheckInOut,
    DraftOut,
    DraftPatchIn,
    EscalationOut,
    Health,
    InvestigatorIn,
    InvestigatorOut,
    OkOut,
    PatientDetail,
    PatientSummary,
    PlanItemOut,
    PlanOut,
    PlanRedFlagOut,
    RejectIn,
    ResolveIn,
    SAEOut,
    SAEPatchIn,
    SponsorInboxItem,
    StudyOut,
    TermTimeline,
    TimelinePoint,
    WebSession,
    WebStartedIn,
)
from app.seed import today_local
from app.serialize import checkin_detail, checkin_out, draft_out, escalation_out, patient_summary, sae_out
from app.services import checkins as checkin_svc
from app.services import elevenlabs, review, sae
from app.services import escalation as esc_svc
from app.services import export as export_svc
from app.timeutil import local_date, utcnow

router = APIRouter(prefix="/api", tags=["api"])


class Actor:
    def __init__(self, user: str, role: str):
        self.user, self.role = user, role


def actor(
    x_bv_user: str | None = Header(default=None), x_bv_role: str | None = Header(default=None)
) -> Actor:
    return Actor(x_bv_user or "Unknown user", (x_bv_role or "coordinator").lower())


def _get(session: Session, model, id_: str, what: str):  # noqa: ANN001, ANN202
    row = session.get(model, id_)
    if row is None:
        raise ApiError(404, f"{what}_not_found", f"{what} {id_} not found")
    return row


# ---- health and reference -----------------------------------------------------------------------------


@router.get("/health", response_model=Health)
def health(request: Request) -> Health:
    s = get_settings()
    ready = elevenlabs.readiness()
    return Health(ok=True, demo_mode=s.demo_mode, version=request.app.version, commit=request.app.state.commit,
                  app_env=s.app_env, pager_channel=s.effective_pager_channel,
                  phone_calls_enabled=ready["phone"] is None, browser_calls_enabled=ready["web"] is None,
                  phone_calls_note=ready["phone"], browser_calls_note=ready["web"])


@router.get("/study", response_model=StudyOut)
def study(session: Session = Depends(get_session)) -> StudyOut:
    st, _ = checkin_svc.active_plan(session)
    return StudyOut(**st.model_dump(include=set(StudyOut.model_fields)))


def plan_out(plan: CheckInPlan) -> PlanOut:
    items: list[PlanItemOut] = []
    codes = [*plan.items, "MEDS_NEW", "CARE_VISIT", "ANYTHING_ELSE"]
    for code in codes:
        it = content.item(code)
        fups = [f["item"] for f in it.get("followups", [])]
        for c in [code, *fups]:
            ci = content.item(c)
            text = {lang: content.item_text(c, lang)["text"] or "" for lang in ("en", "es")}
            opts = {lang: content.item_text(c, lang)["options_say"] or "" for lang in ("en", "es")}
            items.append(PlanItemOut(
                item_code=c, term=ci.get("term"), attribute=content.attribute_of(c), kind=ci.get("kind", "symptom"),
                text=text, options_say=opts if any(opts.values()) else None, source=content.item_source(c),
                followups=[f["item"] for f in ci.get("followups", [])],
            ))
    flags = [
        PlanRedFlagOut(id=rf["id"], level=rf["level"], label_en=rf["label_en"], rule_based=bool(rf.get("rule")))
        for rf in content.red_flags() if rf["id"] in plan.red_flag_ids
    ]
    return PlanOut(
        id=plan.id, version=plan.version, status=plan.status, approved_by=plan.approved_by,
        approved_at=plan.approved_at, schedule_days_after_dose=plan.schedule_days_after_dose, items=items,
        red_flags=flags, source=plan.source, source_citations=plan.source_citations,
    )


@router.get("/plan/active", response_model=PlanOut)
def active_plan(session: Session = Depends(get_session)) -> PlanOut:
    _, plan = checkin_svc.active_plan(session)
    return plan_out(plan)


# ---- patients -----------------------------------------------------------------------------------------


@router.get("/patients", response_model=list[PatientSummary])
def patients(session: Session = Depends(get_session)) -> list[PatientSummary]:
    _, plan = checkin_svc.active_plan(session)
    today = today_local()
    rows = session.exec(select(Patient).order_by(Patient.subject_id)).all()
    return [patient_summary(session, p, plan.schedule_days_after_dose, today) for p in rows]


@router.get("/patients/{patient_id}", response_model=PatientDetail)
def patient_detail(patient_id: str, session: Session = Depends(get_session)) -> PatientDetail:
    p = _get(session, Patient, patient_id, "patient")
    _, plan = checkin_svc.active_plan(session)
    summ = patient_summary(session, p, plan.schedule_days_after_dose, today_local())
    cis = session.exec(
        select(CheckIn).where(CheckIn.patient_id == p.id).order_by(CheckIn.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    from app.models import Answer, Finding

    timeline: dict[str, list[TimelinePoint]] = {}
    for c in sorted(cis, key=lambda c: c.created_at):
        if c.status == "scheduled":
            continue
        d = local_date(c.started_at or c.created_at)
        for f in session.exec(select(Finding).where(Finding.checkin_id == c.id)).all():
            ans = session.exec(select(Answer).where(Answer.checkin_id == c.id, Answer.term == f.term)).first()
            timeline.setdefault(f.term, []).append(TimelinePoint(
                checkin_id=c.id, date=d, provisional_grade=f.provisional_grade,
                answer=(ans.option_code or (str(ans.numeric_value) if ans.numeric_value is not None else None)) if ans else None,
            ))
    return PatientDetail(
        **summ.model_dump(), phone_on_file=bool(p.phone_e164 and not p.phone_e164.startswith("+1555555")),
        baseline=p.baseline or {}, notes=p.notes, dose_dates=[date.fromisoformat(x) for x in p.dose_dates or []],
        checkins=[checkin_out(c) for c in cis],
        timeline=[TermTimeline(term=t, points=pts) for t, pts in sorted(timeline.items())],
    )


# ---- check-ins ----------------------------------------------------------------------------------------


@router.get("/checkins", response_model=list[CheckInListItem])
def list_checkins(date_: date | None = Query(default=None, alias="date"), session: Session = Depends(get_session)) -> list[CheckInListItem]:
    from app.seed import due_day

    _, plan = checkin_svc.active_plan(session)
    day = date_ or today_local()
    today = today_local()
    out: list[CheckInListItem] = []
    pats = {p.id: p for p in session.exec(select(Patient)).all()}
    seen: set[str] = set()
    rows = session.exec(select(CheckIn).order_by(CheckIn.created_at.desc())).all()  # type: ignore[attr-defined]
    for c in rows:
        # `day` is a DISPLAY_TZ local day (docs/03 §6.4): compare local dates, never UTC dates
        when = c.started_at or c.scheduled_for or c.created_at
        if local_date(when) != day and local_date(c.created_at) != day:
            continue
        p = pats.get(c.patient_id)
        if p is None:
            continue
        seen.add(p.id)
        n_open = len(session.exec(select(Escalation).where(Escalation.checkin_id == c.id, Escalation.status == "open")).all())
        out.append(CheckInListItem(
            id=c.id, status=c.status, channel=c.channel, day_after_dose=c.day_after_dose, started_at=c.started_at,
            patient=patient_summary(session, p, plan.schedule_days_after_dose, today), open_escalations=n_open,
        ))
    for p in pats.values():
        if p.id in seen:
            continue
        d = due_day(p.dose_dates, plan.schedule_days_after_dose, day)
        if d is not None:
            out.append(CheckInListItem(
                id=None, status="due", channel=None, day_after_dose=d,
                patient=patient_summary(session, p, plan.schedule_days_after_dose, today),
            ))
    order = {"in_progress": 0, "dialing": 1, "scheduled": 2, "due": 2, "completed": 3}
    out.sort(key=lambda x: (order.get(x.status, 4), x.patient.subject_id))
    return out


@router.post("/patients/{patient_id}/checkins", response_model=CreateCheckInOut, status_code=201)
def create_checkin(patient_id: str, body: CreateCheckInIn, who: Actor = Depends(actor),
                   session: Session = Depends(get_session)) -> CreateCheckInOut:
    p = _get(session, Patient, patient_id, "patient")
    not_ready = elevenlabs.readiness()["phone" if body.channel == "phone" else "web"]
    if not_ready and not elevenlabs.has_client_override():
        raise ApiError(503, "telephony_unavailable", not_ready)
    c = checkin_svc.new_checkin(session, p, body.channel, body.day_after_dose, who.user, who.role)
    web = None
    if body.channel == "phone":
        checkin_svc.start_phone(session, c, p)
    else:
        web = WebSession(**checkin_svc.start_web(session, c, p))
    session.commit()
    session.refresh(c)
    return CreateCheckInOut(checkin=checkin_out(c), web_session=web)


@router.post("/checkins/{checkin_id}/web-started", response_model=OkOut)
def web_started(checkin_id: str, body: WebStartedIn, session: Session = Depends(get_session)) -> OkOut:
    c = _get(session, CheckIn, checkin_id, "checkin")
    if body.conversation_id:
        c.el_conversation_id = body.conversation_id
    if c.status in ("dialing", "scheduled"):
        c.status = "in_progress"
        c.started_at = c.started_at or utcnow()
    session.add(c)
    session.commit()
    return OkOut()


@router.post("/checkins/{checkin_id}/cancel", response_model=CheckInOut)
def cancel_checkin(checkin_id: str, who: Actor = Depends(actor), session: Session = Depends(get_session)) -> CheckInOut:
    c = _get(session, CheckIn, checkin_id, "checkin")
    before = {"status": c.status}
    if c.status not in ("completed",):
        c.status = "cancelled"
        c.ended_at = c.ended_at or utcnow()
    session.add(c)
    write_audit(session, actor=who.user, role=who.role, action="checkin.cancelled", entity_type="CheckIn",
                entity_id=c.id, before=before, after={"status": c.status}, checkin_id=c.id)
    session.commit()
    return checkin_out(c)


@router.get("/checkins/{checkin_id}", response_model=CheckInDetail)
def get_checkin(checkin_id: str, session: Session = Depends(get_session)) -> CheckInDetail:
    return checkin_detail(session, _get(session, CheckIn, checkin_id, "checkin"))


# ---- escalations --------------------------------------------------------------------------------------


@router.get("/escalations", response_model=list[EscalationOut])
def escalations(status: str | None = None, checkin_id: str | None = None,
                session: Session = Depends(get_session)) -> list[EscalationOut]:
    q = select(Escalation)
    if status:
        q = q.where(Escalation.status.in_(status.split(",")))  # type: ignore[attr-defined]
    if checkin_id:
        q = q.where(Escalation.checkin_id == checkin_id)
    rows = list(session.exec(q).all())
    st_rank = {"open": 0, "acknowledged": 1, "resolved": 2}
    lv_rank = {"emergency": 0, "urgent": 1, "callback": 2}
    rows.sort(key=lambda e: (st_rank.get(e.status, 3), lv_rank.get(e.level, 3), e.created_at.timestamp()))
    return [escalation_out(session, e, with_patient=True) for e in rows]


@router.post("/escalations/{escalation_id}/ack", response_model=EscalationOut)
def ack_escalation(escalation_id: str, who: Actor = Depends(actor), session: Session = Depends(get_session)) -> EscalationOut:
    e = _get(session, Escalation, escalation_id, "escalation")
    esc_svc.acknowledge(session, e, by=who.user, method="dashboard", role=who.role)
    session.commit()
    return escalation_out(session, e, with_patient=True)


@router.post("/escalations/{escalation_id}/resolve", response_model=EscalationOut)
def resolve_escalation(escalation_id: str, body: ResolveIn, who: Actor = Depends(actor),
                       session: Session = Depends(get_session)) -> EscalationOut:
    e = _get(session, Escalation, escalation_id, "escalation")
    esc_svc.resolve(session, e, by=who.user, role=who.role, note=body.note)
    session.commit()
    return escalation_out(session, e, with_patient=True)


# ---- drafts -------------------------------------------------------------------------------------------


@router.get("/drafts", response_model=list[DraftOut])
def drafts(status: str | None = None, kind: str | None = None, patient_id: str | None = None,
           checkin_id: str | None = None, session: Session = Depends(get_session)) -> list[DraftOut]:
    q = select(DraftEntry)
    if status:
        q = q.where(DraftEntry.status.in_(status.split(",")))  # type: ignore[attr-defined]
    if kind:
        q = q.where(DraftEntry.kind.in_(kind.split(",")))  # type: ignore[attr-defined]
    if patient_id:
        q = q.where(DraftEntry.patient_id == patient_id)
    if checkin_id:
        q = q.where(DraftEntry.checkin_id == checkin_id)
    rows = session.exec(q.order_by(DraftEntry.created_at.desc())).all()  # type: ignore[attr-defined]
    return [draft_out(session, d, with_patient=True) for d in rows]


@router.patch("/drafts/{draft_id}", response_model=DraftOut)
def edit_draft(draft_id: str, body: DraftPatchIn, who: Actor = Depends(actor), session: Session = Depends(get_session)) -> DraftOut:
    d = review.edit(session, _get(session, DraftEntry, draft_id, "draft"), body.payload, body.note, who.user, who.role)
    session.commit()
    return draft_out(session, d, with_patient=True)


@router.post("/drafts/{draft_id}/confirm", response_model=DraftOut)
def confirm_draft(draft_id: str, body: ConfirmIn | None = None, who: Actor = Depends(actor),
                  session: Session = Depends(get_session)) -> DraftOut:
    d = review.confirm(session, _get(session, DraftEntry, draft_id, "draft"), (body.note if body else None), who.user, who.role)
    session.commit()
    return draft_out(session, d, with_patient=True)


@router.post("/drafts/{draft_id}/reject", response_model=DraftOut)
def reject_draft(draft_id: str, body: RejectIn, who: Actor = Depends(actor), session: Session = Depends(get_session)) -> DraftOut:
    d = review.reject(session, _get(session, DraftEntry, draft_id, "draft"), body.reason, who.user, who.role)
    session.commit()
    return draft_out(session, d, with_patient=True)


@router.post("/drafts/{draft_id}/investigator", response_model=InvestigatorOut)
def investigator(draft_id: str, body: InvestigatorIn, who: Actor = Depends(actor),
                 session: Session = Depends(get_session)) -> InvestigatorOut:
    if who.role != "investigator":
        raise ApiError(409, "wrong_role", "Only the investigator role can assess seriousness and relatedness.")
    d = _get(session, DraftEntry, draft_id, "draft")
    report = review.investigator(session, d, body, who.user)
    session.commit()
    return InvestigatorOut(draft=draft_out(session, d, with_patient=True),
                           sae_report=sae_out(session, report) if report else None)


# ---- SAE and sponsor ----------------------------------------------------------------------------------


@router.get("/sae", response_model=list[SAEOut])
def sae_list(session: Session = Depends(get_session)) -> list[SAEOut]:
    rows = session.exec(select(SAEReport).order_by(SAEReport.created_at.desc())).all()  # type: ignore[attr-defined]
    return [sae_out(session, r) for r in rows]


@router.get("/sae/{sae_id}", response_model=SAEOut)
def sae_get(sae_id: str, session: Session = Depends(get_session)) -> SAEOut:
    return sae_out(session, _get(session, SAEReport, sae_id, "sae"))


@router.patch("/sae/{sae_id}", response_model=SAEOut)
def sae_patch(sae_id: str, body: SAEPatchIn, who: Actor = Depends(actor), session: Session = Depends(get_session)) -> SAEOut:
    if who.role != "investigator":
        raise ApiError(409, "wrong_role", "Only the investigator role can edit the serious-event report.")
    r = sae.edit(session, _get(session, SAEReport, sae_id, "sae"), body.narrative_final, body.payload, who.user, who.role)
    session.commit()
    return sae_out(session, r)


@router.post("/sae/{sae_id}/sign", response_model=SAEOut)
def sae_sign(sae_id: str, who: Actor = Depends(actor), session: Session = Depends(get_session)) -> SAEOut:
    if who.role != "investigator":
        raise ApiError(409, "wrong_role", "Only the investigator role can sign the serious-event report.")
    r = sae.sign(session, _get(session, SAEReport, sae_id, "sae"), who.user, who.role)
    session.commit()
    return sae_out(session, r)


@router.post("/sae/{sae_id}/send", response_model=SAEOut)
def sae_send(sae_id: str, who: Actor = Depends(actor), session: Session = Depends(get_session)) -> SAEOut:
    r = sae.send(session, _get(session, SAEReport, sae_id, "sae"), who.user, who.role)
    session.commit()
    return sae_out(session, r)


@router.get("/sponsor/inbox", response_model=list[SponsorInboxItem])
def sponsor_inbox(session: Session = Depends(get_session)) -> list[SponsorInboxItem]:
    return sae.inbox(session)


# ---- exports, audit, eval, validation -----------------------------------------------------------------


@router.get("/export/ae.csv", response_class=PlainTextResponse)
def export_ae(session: Session = Depends(get_session)) -> PlainTextResponse:
    return PlainTextResponse(export_svc.ae_csv(session), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=ae.csv",
                                      "X-BV-Note": export_svc.ae_note()})


@router.get("/export/cm.csv", response_class=PlainTextResponse)
def export_cm(session: Session = Depends(get_session)) -> PlainTextResponse:
    return PlainTextResponse(export_svc.cm_csv(session), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=cm.csv",
                                      "X-BV-Note": export_svc.CM_NOTE})


@router.get("/export/sae/{sae_id}.json")
def export_sae(sae_id: str, session: Session = Depends(get_session)) -> dict:
    r = _get(session, SAEReport, sae_id, "sae")
    return export_svc.sae_json(r)


@router.get("/audit", response_model=list[AuditOut])
def audit(entity_id: str | None = None, checkin_id: str | None = None, limit: int = 200,
          session: Session = Depends(get_session)) -> list[AuditOut]:
    q = select(AuditEvent)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    if checkin_id:
        q = q.where(AuditEvent.checkin_id == checkin_id)
    rows = session.exec(q.order_by(AuditEvent.ts.desc(), AuditEvent.id.desc()).limit(min(limit, 1000))).all()  # type: ignore[attr-defined]
    return [AuditOut(**a.model_dump()) for a in rows]


def _read_json(path: str, code: str) -> dict:
    p = ROOT / path
    if not p.exists():
        raise ApiError(404, code, f"{path} not found")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/eval/latest")
def eval_latest() -> dict:
    return _read_json("eval/results/latest.json", "no_eval_run")


@router.get("/validation/latest")
def validation_latest() -> dict:
    return _read_json("validation/summary.json", "no_validation_run")


_ = Study  # re-exported for type checkers
