"""Agent tool endpoints (/agent/tools/*), called by the ElevenLabs agent as server tools.

Always HTTP 200 with the {ok, next, escalated} envelope (except 401 for a missing/bad shared secret).
One structured log line per call.
"""

import hmac
import logging
import secrets
import time
from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session, select

from app import content
from app.config import get_settings
from app.db import get_session, new_session
from app.ids import new_id
from app.models import CheckIn, Escalation, Patient
from app.schemas import (
    RecordAnswerIn,
    RecordMedicationIn,
    ReportRedFlagIn,
    RequestHumanIn,
    SetSpeakerIn,
    ToolBase,
    ToolEnvelope,
)
from app.services import escalation, interview
from app.services.interview import Next, ToolResult

log = logging.getLogger("bv.tools")
router = APIRouter(prefix="/agent/tools", tags=["agent-tools"])


def require_tool_secret(x_bv_tool_secret: str | None = Header(default=None)) -> None:
    expected = get_settings().tool_shared_secret
    if not x_bv_tool_secret or not hmac.compare_digest(x_bv_tool_secret, expected):
        raise HTTPException(status_code=401, detail={"code": "bad_tool_secret", "message": "missing or invalid X-BV-Tool-Secret"})


def find_checkin(session: Session, body: ToolBase) -> CheckIn | None:
    if body.checkin_id and body.checkin_id != "unknown":
        c = session.get(CheckIn, body.checkin_id)
        if c:
            return c
    if body.conversation_id:
        return session.exec(select(CheckIn).where(CheckIn.el_conversation_id == body.conversation_id)).first()
    return None


def _fail_safe(tool: str, body: ToolBase, err: Exception, possible_red_flag: bool) -> ToolEnvelope:
    """Internal error: escalate (urgent if a red flag may be involved, else callback) and close politely."""
    lang = "en"
    try:
        with new_session() as s:
            c = find_checkin(s, body)
            if c:
                lang = c.language
                p = s.get(Patient, c.patient_id)
                if p:
                    esc = Escalation(
                        id=new_id("esc"), checkin_id=c.id, patient_id=p.id,
                        level="urgent" if possible_red_flag else "callback", red_flag_ids=[],
                        reason="agent_report" if possible_red_flag else "patient_request",
                        summary_en=f"System error during the {tool} step of the call; please call the patient back.",
                        patient_language=c.language, ack_token=secrets.token_urlsafe(24),
                    )
                    s.add(esc)
                    s.flush()
                    if possible_red_flag:
                        escalation.page(s, esc, p)
                    s.commit()
    except Exception:  # noqa: BLE001
        log.exception("fail_safe_escalation_failed tool=%s checkin_id=%s", tool, body.checkin_id)
    say = content.script("fallback_error", lang)
    return ToolEnvelope(ok=False, error="internal", escalated=True, next={"action": "close", "item_code": None, "say": say})


def run_tool(
    tool: str,
    body: ToolBase,
    session: Session,
    fn: Callable[[Session, CheckIn], ToolResult],
    possible_red_flag: bool = False,
) -> ToolEnvelope:
    t0 = time.perf_counter()
    try:
        checkin = find_checkin(session, body)
        if checkin is None:
            say = content.script("wrong_person_close", "en")
            res = ToolResult(False, Next("close", None, say), False, "unknown_checkin")
        else:
            if body.conversation_id and not checkin.el_conversation_id:
                checkin.el_conversation_id = body.conversation_id
            res = fn(session, checkin)
            session.commit()
        env = ToolEnvelope(**res.envelope())
    except Exception as e:  # noqa: BLE001
        session.rollback()
        log.exception("tool_error tool=%s checkin_id=%s", tool, body.checkin_id)
        env = _fail_safe(tool, body, e, possible_red_flag)
    log.info(
        "tool=%s checkin_id=%s ok=%s action=%s item=%s escalated=%s error=%s ms=%d",
        tool, body.checkin_id, env.ok, env.next.action, env.next.item_code, env.escalated, env.error,
        (time.perf_counter() - t0) * 1000,
    )
    return env


def _is_symptom(code: str | None) -> bool:
    return bool(code and content.has_item(code) and content.term_of(code))


@router.post("/record_answer", response_model=ToolEnvelope, dependencies=[Depends(require_tool_secret)])
def record_answer(body: RecordAnswerIn, session: Session = Depends(get_session)) -> ToolEnvelope:
    return run_tool(
        "record_answer", body, session,
        lambda s, c: interview.record_answer(
            s, c, item_code=body.item_code, option_code=body.option_code, numeric_value=body.numeric_value,
            unit=body.unit, verbatim_quote=body.verbatim_quote,
        ),
        possible_red_flag=_is_symptom(body.item_code) or body.item_code is None,
    )


@router.post("/report_red_flag", response_model=ToolEnvelope, dependencies=[Depends(require_tool_secret)])
def report_red_flag(body: ReportRedFlagIn, session: Session = Depends(get_session)) -> ToolEnvelope:
    return run_tool(
        "report_red_flag", body, session,
        lambda s, c: interview.report_red_flag(s, c, red_flag_id=body.red_flag_id, verbatim_quote=body.verbatim_quote),
        possible_red_flag=True,
    )


@router.post("/record_medication_change", response_model=ToolEnvelope, dependencies=[Depends(require_tool_secret)])
def record_medication_change(body: RecordMedicationIn, session: Session = Depends(get_session)) -> ToolEnvelope:
    return run_tool(
        "record_medication_change", body, session,
        lambda s, c: interview.record_medication_change(
            s, c, description=body.description, verbatim_quote=body.verbatim_quote
        ),
    )


@router.post("/request_human", response_model=ToolEnvelope, dependencies=[Depends(require_tool_secret)])
def request_human(body: RequestHumanIn, session: Session = Depends(get_session)) -> ToolEnvelope:
    return run_tool(
        "request_human", body, session,
        lambda s, c: interview.request_human(s, c, reason=body.reason, verbatim_quote=body.verbatim_quote),
    )


@router.post("/set_speaker", response_model=ToolEnvelope, dependencies=[Depends(require_tool_secret)])
def set_speaker(body: SetSpeakerIn, session: Session = Depends(get_session)) -> ToolEnvelope:
    return run_tool(
        "set_speaker", body, session,
        lambda s, c: interview.set_speaker(s, c, speaker=body.speaker, relation=body.relation),
    )


TOOL_FUNCS = {
    "record_answer": (RecordAnswerIn, record_answer),
    "report_red_flag": (ReportRedFlagIn, report_red_flag),
    "record_medication_change": (RecordMedicationIn, record_medication_change),
    "request_human": (RequestHumanIn, request_human),
    "set_speaker": (SetSpeakerIn, set_speaker),
}


def call_tool_inprocess(tool: str, body: dict, session: Session) -> ToolEnvelope:
    """Same code path as HTTP, minus the secret check (used by replay and the eval harness)."""
    model, fn = TOOL_FUNCS[tool]
    return fn(model(**body), session)  # type: ignore[operator]
