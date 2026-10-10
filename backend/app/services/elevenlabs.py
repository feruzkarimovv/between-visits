"""ElevenLabs Agents: outbound phone calls (native Twilio) and browser session tokens.

Exact request shapes: docs/04-voice-agent.md. The variant → agent_id map is written by
agent/sync_agent.py to agent/agents.lock.json. Tests install a fake with set_client().
"""

import json
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app import content
from app.config import AGENT_DIR, get_settings
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


def load_lock() -> dict[str, str]:
    p = AGENT_DIR / "agents.lock.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def agent_id_for(variant: str) -> str:
    agent_id = load_lock().get(variant)
    if not agent_id:
        raise TelephonyUnavailable(f"no agent for variant {variant}; run `make sync-agent`")
    return agent_id


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


_override: Client | None = None


def set_client(c: Client | None) -> None:
    global _override
    _override = c


def client() -> Client:
    if _override is not None:
        return _override
    if get_settings().demo_mode:
        raise TelephonyUnavailable("demo mode: no calls (use Replay scenario)")
    return HttpClient()
