"""Webhooks: ElevenLabs post-call (HMAC) and inbound-init, ntfy Acknowledge button, Twilio page callbacks."""

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import JSONResponse, Response
from sqlmodel import select

from app import content
from app.config import SCENARIOS_DIR, get_settings
from app.db import new_session
from app.errors import ApiError
from app.models import CheckIn, Escalation, Patient, Study
from app.seed import variant_for
from app.services import checkins as checkin_svc
from app.services import elevenlabs, escalation, interview, pager, postcall
from app.timeutil import utcnow

log = logging.getLogger("bv.webhooks")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ---- ElevenLabs post-call ------------------------------------------------------------------------------


def verify_elevenlabs_signature(raw: bytes, sig_header: str | None, secret: str, now: float | None = None) -> bool:
    if not sig_header or not secret:
        return False
    try:
        parts = dict(x.split("=", 1) for x in sig_header.split(","))
        ts = int(parts["t"])
        if ts < (now or time.time()) - 1800:
            return False
        mac = hmac.new(secret.encode(), f"{parts['t']}.{raw.decode()}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, parts["v0"])
    except (KeyError, ValueError):
        return False


def sign_elevenlabs(raw: bytes, secret: str, ts: int | None = None) -> str:
    """Helper for tests and the replay engine."""
    ts = ts or int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.{raw.decode()}".encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v0={mac}"


def _find_checkin(session, data: dict[str, Any]) -> CheckIn | None:  # noqa: ANN001
    conv = data.get("conversation_id")
    if conv:
        c = session.exec(select(CheckIn).where(CheckIn.el_conversation_id == conv)).first()
        if c:
            return c
    dyn = ((data.get("conversation_initiation_client_data") or {}).get("dynamic_variables")) or {}
    cid = dyn.get("checkin_id")
    if cid and cid != "unknown":
        c = session.get(CheckIn, cid)
        if c:
            if conv and not c.el_conversation_id:
                c.el_conversation_id = conv
            return c
    return None


def process_post_call(data: dict[str, Any]) -> None:
    """Background task: store the transcript and run the post-call pipeline."""
    with new_session() as s:
        c = _find_checkin(s, data)
        if c is None:
            log.warning("post_call_unmatched conversation_id=%s", data.get("conversation_id"))
            return
        if c.postcall_status in ("processing", "done"):
            log.info("post_call_duplicate checkin_id=%s conversation_id=%s", c.id, data.get("conversation_id"))
            return
        turns = postcall.turns_from_elevenlabs(data, c.language)
        postcall.apply_call_metadata(c, data, turns)
        s.commit()
        try:
            postcall.run(s, c, turns)
            s.commit()
        except Exception as e:  # noqa: BLE001  fail safe: page a human to review this call
            s.rollback()
            log.exception("postcall_failed checkin_id=%s", c.id)
            c = s.get(CheckIn, c.id)
            p = s.get(Patient, c.patient_id) if c else None
            if c and p:
                c.postcall_status = "failed"
                esc = escalation.create_callback(s, c, p, "post_call_safety_net",
                                                 f"Post-call processing failed ({type(e).__name__}); review the call now.",
                                                 actor="system")
                esc.level = "urgent"
                s.flush()
                escalation.page(s, esc, p)
                s.commit()


def handle_initiation_failure(data: dict[str, Any]) -> None:
    with new_session() as s:
        c = _find_checkin(s, data)
        if c is None:
            return
        reason = str(data.get("failure_reason") or "unknown")
        c.status = "no_answer" if reason in ("busy", "no-answer", "no_answer") else "failed"
        c.termination_reason = f"call initiation failure: {reason}"
        c.ended_at = utcnow()
        s.add(c)
        s.commit()
        log.info("call_initiation_failure checkin_id=%s reason=%s", c.id, reason)


def save_audio(data: dict[str, Any]) -> None:
    with new_session() as s:
        c = _find_checkin(s, data)
        audio = data.get("full_audio")
        if c is None or not audio:
            return
        out = SCENARIOS_DIR / "audio" / f"{c.id}.mp3"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(audio))
        log.info("post_call_audio_saved checkin_id=%s path=%s", c.id, out)


@router.post("/elevenlabs/post-call")
async def elevenlabs_post_call(
    request: Request, background: BackgroundTasks, elevenlabs_signature: str | None = Header(default=None)
) -> dict[str, bool]:
    raw = await request.body()
    if not verify_elevenlabs_signature(raw, elevenlabs_signature, get_settings().elevenlabs_webhook_secret):
        log.warning("post_call_bad_signature")
        raise ApiError(401, "bad_signature", "invalid ElevenLabs-Signature")
    event = json.loads(raw)
    kind, data = event.get("type"), event.get("data") or {}
    log.info("webhook=elevenlabs type=%s conversation_id=%s", kind, data.get("conversation_id"))
    if kind == "post_call_transcription":
        background.add_task(process_post_call, data)
    elif kind == "call_initiation_failure":
        background.add_task(handle_initiation_failure, data)
    elif kind == "post_call_audio":
        background.add_task(save_audio, data)
    return {"ok": True}


# ---- ElevenLabs inbound-init (patient calls the study line) --------------------------------------------


def _unknown_caller(lang: str = "en") -> dict[str, Any]:
    sd = content.study_doc()
    team = sd["study_team_name"][lang]
    return {
        "type": "conversation_initiation_client_data",
        "dynamic_variables": {
            "checkin_id": "unknown", "patient_first_name": "", "study_team_name": team,
            "language_name": content.language_name(lang, "en"), "pace_instructions": content.pace_instructions("standard"),
            "caregiver_name": "",
        },
        "conversation_config_override": {
            "agent": {"first_message": content.script("first_message_inbound_unknown", lang, study_team_name=team)}
        },
    }


@router.post("/elevenlabs/inbound-init")
async def elevenlabs_inbound_init(request: Request, x_bv_tool_secret: str | None = Header(default=None)) -> JSONResponse:
    """Always 200 and fast: a failing webhook can stop the call from starting."""
    s_ = get_settings()
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    if not x_bv_tool_secret or not hmac.compare_digest(x_bv_tool_secret, s_.tool_shared_secret):
        log.warning("inbound_init_bad_secret")
        return JSONResponse(_unknown_caller())
    called, caller = body.get("called_number"), body.get("caller_id")
    if s_.twilio_from_number and called and called != s_.twilio_from_number:
        log.warning("inbound_init_wrong_number called=%s", called)
        return JSONResponse(_unknown_caller())
    try:
        with new_session() as s:
            p = s.exec(select(Patient).where(Patient.phone_e164 == caller)).first() if caller else None
            if p is None:
                log.warning("inbound_init_unknown_caller")
                return JSONResponse(_unknown_caller())
            existing = checkin_svc.live_checkin(s, p.id)
            if existing:
                c = existing
            else:
                c = checkin_svc.new_checkin(s, p, "phone_inbound", None, "system", "system")
            c.channel = "phone_inbound"
            c.status = "in_progress"
            c.started_at = c.started_at or utcnow()
            c.el_conversation_id = body.get("conversation_id") or c.el_conversation_id
            c.twilio_call_sid = body.get("call_sid")
            c.el_agent_id = body.get("agent_id")
            c.agent_variant = variant_for(p.language, p.pace)
            if not c.interview_state:
                interview.start(c, None)
            s.add(c)
            study = s.get(Study, c.study_id)
            dyn = elevenlabs.dynamic_variables(c, p, study)
            first = content.script("first_message_inbound", c.language, study_team_name=dyn["study_team_name"],
                                   patient_first_name=p.first_name)
            s.commit()
            log.info("inbound_init checkin_id=%s subject=%s", c.id, p.subject_id)
            return JSONResponse({
                "type": "conversation_initiation_client_data",
                "dynamic_variables": dyn,
                "conversation_config_override": {"agent": {"first_message": first}},
                "user_id": p.subject_id,
            })
    except Exception:  # noqa: BLE001
        log.exception("inbound_init_error")
        return JSONResponse(_unknown_caller())


# ---- paging acknowledgments ---------------------------------------------------------------------------


@router.post("/ntfy/ack/{escalation_id}")
def ntfy_ack(escalation_id: str, authorization: str | None = Header(default=None)) -> dict[str, bool]:
    with new_session() as s:
        e = s.get(Escalation, escalation_id)
        token = (authorization or "").removeprefix("Bearer ").strip()
        if e is None or not token or not hmac.compare_digest(token, e.ack_token):
            log.warning("ntfy_ack_rejected escalation_id=%s", escalation_id)
            raise ApiError(401, "bad_token", "invalid acknowledgment token")
        escalation.acknowledge(s, e, by=get_settings().oncall_nurse_name, method="push_button")
        s.commit()
        log.info("webhook=ntfy_ack escalation_id=%s checkin_id=%s", e.id, e.checkin_id)
    return {"ok": True}


def _twilio_valid(request: Request, params: dict[str, str]) -> bool:
    from twilio.request_validator import RequestValidator

    s = get_settings()
    url = f"{s.public_base_url.rstrip('/')}{request.url.path}"
    if request.url.query:
        url += f"?{request.url.query}"
    ok = RequestValidator(s.twilio_auth_token).validate(url, params, request.headers.get("X-Twilio-Signature", ""))
    if not ok and s.app_env == "dev":
        log.warning("twilio_signature_invalid_but_dev_mode url=%s (accepting because APP_ENV=dev)", url)
        return True
    return ok


def _twiml(body: str) -> Response:
    return Response(content=f"<Response>{body}</Response>", media_type="application/xml")


@router.post("/twilio/page-ack")
async def twilio_page_ack(request: Request, escalation_id: str, attempt: int = 1) -> Response:
    form = dict((await request.form()).items())
    params = {k: str(v) for k, v in form.items()}
    if not _twilio_valid(request, params):
        raise ApiError(403, "bad_signature", "invalid X-Twilio-Signature")
    with new_session() as s:
        e = s.get(Escalation, escalation_id)
        if e is None:
            return _twiml("<Hangup/>")
        if params.get("Digits") == "1":
            escalation.acknowledge(s, e, by=get_settings().oncall_nurse_name, method="phone_keypress")
            s.commit()
            log.info("webhook=twilio_page_ack escalation_id=%s checkin_id=%s", e.id, e.checkin_id)
            return _twiml(f"<Say>{content.page_template('ack_confirmation')}</Say>")
        if attempt < 2:
            action = f"{get_settings().public_base_url.rstrip('/')}/webhooks/twilio/page-ack?escalation_id={e.id}&amp;attempt=2"
            return _twiml(
                f'<Gather numDigits="1" action="{action}" method="POST" timeout="10">'
                f"<Say>{content.page_template('voice_suffix')}</Say></Gather>"
                f"<Say>{content.page_template('no_input')}</Say>"
            )
        return _twiml(f"<Say>{content.page_template('no_input')}</Say>")


@router.post("/twilio/page-status")
async def twilio_page_status(request: Request, escalation_id: str) -> dict[str, bool]:
    params = {k: str(v) for k, v in (await request.form()).items()}
    if not _twilio_valid(request, params):
        raise ApiError(403, "bad_signature", "invalid X-Twilio-Signature")
    status = params.get("CallStatus")
    log.info("webhook=twilio_page_status escalation_id=%s status=%s", escalation_id, status)
    if status in ("busy", "no-answer", "failed"):
        with new_session() as s:
            e = s.get(Escalation, escalation_id)
            p = s.get(Patient, e.patient_id) if e else None
            if e and p and e.status == "open":
                msg = pager.build_message(escalation_id=e.id, level=e.level, subject_id=p.subject_id,
                                          language=e.patient_language, flag_ids=e.red_flag_ids, values={},
                                          ack_token=e.ack_token)
                try:
                    pager._ntfy(msg)  # immediate push instead of waiting for the re-page loop
                except Exception as ex:  # noqa: BLE001
                    log.error("status_push_failed escalation_id=%s error=%r", e.id, ex)
    return {"ok": True}

