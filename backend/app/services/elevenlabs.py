"""ElevenLabs Agents: outbound phone calls (native Twilio) and browser session tokens.

Exact request shapes: docs/04-voice-agent.md. The variant → agent_id map is written by
agent/sync_agent.py to agent/agents.lock.json; a cloud host without that (gitignored) file reads the same JSON
from AGENTS_LOCK_JSON (docs/03 §6.9). Tests install a fake with set_client().
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app import content
from app.config import AGENTS_LOCK_PATH, get_settings
from app.models import CheckIn, Patient, Study

log = logging.getLogger("bv.elevenlabs")
API = "https://api.elevenlabs.io"


class TelephonyUnavailable(Exception):
    pass


@dataclass
class CallStarted:
    conversation_id: str | None
    call_sid: str | None


@dataclass
class WebToken:
    token: str
    conversation_id: str | None


class Client(Protocol):
    def outbound_call(self, agent_id: str, to_number: str, user_id: str, dynamic_variables: dict[str, str]) -> CallStarted: ...
    def web_token(self, agent_id: str) -> WebToken: ...
    def get_conversation(self, conversation_id: str) -> dict[str, Any]: ...


def load_lock() -> dict[str, str]:
    """Variant → agent_id: agent/agents.lock.json, else AGENTS_LOCK_JSON (cloud deploys, docs/03 §6.9).

    A missing or unreadable map means "not synced" ({}): calls stay off and the dashboard says why. The raw
    value is never logged.
    """
    if AGENTS_LOCK_PATH.exists():
        origin, raw = "agent/agents.lock.json", AGENTS_LOCK_PATH.read_text(encoding="utf-8")
    else:
        origin, raw = "AGENTS_LOCK_JSON", get_settings().agents_lock_json
        if not raw.strip():
            return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.error("agents_lock_invalid source=%s reason=not_json", origin)
        return {}
    if not isinstance(data, dict):
        log.error("agents_lock_invalid source=%s reason=not_an_object", origin)
        return {}
    return {str(variant): agent_id for variant, agent_id in data.items() if isinstance(agent_id, str) and agent_id}


def agent_id_for(variant: str) -> str:
    agent_id = load_lock().get(variant)
    if not agent_id:
        raise TelephonyUnavailable(f"no agent for variant {variant}; run `make sync-agent`")
    return agent_id


def readiness() -> dict[str, str | None]:
    """Why each call channel is unavailable (None = ready). Shown on the dashboard instead of failing a call."""
    s = get_settings()
    lock = load_lock()
    base = None
    if s.demo_mode:
        base = "Demo mode: calls are off. Use Replay scenario."
    elif not s.elevenlabs_api_key:
        base = "ElevenLabs isn't configured (ELEVENLABS_API_KEY)."
    elif len(lock) < 4:
        base = "ElevenLabs agents aren't synced yet (make sync-agent; on a cloud host, set AGENTS_LOCK_JSON)."
    phone = base or (None if s.elevenlabs_phone_number_id else
                     "Phone calls aren't set up yet: import the Twilio number into ElevenLabs "
                     "(ELEVENLABS_PHONE_NUMBER_ID). Use Call in browser.")
    return {"phone": phone, "web": base}


def dynamic_variables(checkin: CheckIn, patient: Patient, study: Study | None) -> dict[str, str]:
    lang = checkin.language
    team = (study.study_team_name if study else None) or content.study_doc()["study_team_name"]
    return {
        "checkin_id": checkin.id,
        "patient_first_name": patient.first_name,
        "study_team_name": team.get(lang) or team["en"],
        "language_name": content.language_name(lang, "en"),
        "pace_instructions": content.pace_instructions(checkin.pace),
        "caregiver_name": patient.caregiver_name or ("un cuidador" if lang == "es" else "a caregiver"),
    }


class HttpClient:
    def __init__(self) -> None:
        s = get_settings()
        if not s.elevenlabs_api_key:
            raise TelephonyUnavailable("ELEVENLABS_API_KEY is not set")
        self.headers = {"xi-api-key": s.elevenlabs_api_key}

    def outbound_call(self, agent_id: str, to_number: str, user_id: str, dynamic_variables: dict[str, str]) -> CallStarted:
        s = get_settings()
        if not s.elevenlabs_phone_number_id:
            raise TelephonyUnavailable("ELEVENLABS_PHONE_NUMBER_ID is not set")
        body = {
            "agent_id": agent_id,
            "agent_phone_number_id": s.elevenlabs_phone_number_id,
            "to_number": to_number,
            "conversation_initiation_client_data": {"user_id": user_id, "dynamic_variables": dynamic_variables},
            "telephony_call_config": {"ringing_timeout_secs": 45},
        }
        r = httpx.post(f"{API}/v1/convai/twilio/outbound-call", json=body, headers=self.headers, timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs outbound-call {r.status_code}: {r.text[:500]}")
        data = r.json()
        if data.get("success") is False:
            raise RuntimeError(f"ElevenLabs outbound-call failed: {data.get('message')}")
        return CallStarted(data.get("conversation_id"), data.get("callSid") or data.get("call_sid"))

    def web_token(self, agent_id: str) -> WebToken:
        r = httpx.get(
            f"{API}/v1/convai/conversation/token", params={"agent_id": agent_id}, headers=self.headers, timeout=10
        )
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs token {r.status_code}: {r.text[:500]}")
        data = r.json()
        return WebToken(data["token"], data.get("conversation_id"))

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        """`GET /v1/convai/conversations/{id}`: the same transcript, metadata and analysis as the post-call webhook."""
        r = httpx.get(f"{API}/v1/convai/conversations/{conversation_id}", headers=self.headers, timeout=15)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs conversation {r.status_code}: {r.text[:300]}")
        return r.json()


_override: Client | None = None


def set_client(c: Client | None) -> None:
    global _override
    _override = c


def has_client_override() -> bool:
    return _override is not None


def client() -> Client:
    if _override is not None:
        return _override
    if get_settings().demo_mode:
        raise TelephonyUnavailable("demo mode: no calls (use Replay scenario)")
    return HttpClient()
