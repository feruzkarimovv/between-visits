"""Paging the on-call nurse. Channels: ntfy (default), twilio_voice (optional), console (demo mode / tests).

Page text comes only from data/scripts.json `page_templates_en` and each red flag's `page_phrase_en`
(never from an LLM) and carries the subject ID only, never names.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

import httpx

from app import content
from app.config import get_settings

log = logging.getLogger("bv.pager")


@dataclass
class PageMessage:
    escalation_id: str
    level: str
    title: str
    text: str
    ack_token: str
    backup: bool = False


@dataclass
class PageResult:
    channel: str
    target_name: str
    ref: str


# Tests (and the eval harness) install a fake with set_pager(); None means use the configured channel.
_override: Callable[[PageMessage], PageResult] | None = None


def set_pager(fn: Callable[[PageMessage], PageResult] | None) -> None:
    global _override
    _override = fn


# ---- message text -------------------------------------------------------------------------------------

_SOB_DETAIL = {"at_rest": "at rest", "light_activity": "with light activity", "heavy_activity": "with heavy activity"}


def _fmt_num(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.1f}".rstrip("0").rstrip(".")
    return str(v)


def flag_phrase(flag_id: str, values: dict[str, Any]) -> str:
    """One sentence for the nurse about a red flag, from the flag's page_phrase_en filled with rule inputs.
    Falls back to the flag's label when an input is unknown (e.g. a flag reported by the agent)."""
    if not content.has_red_flag(flag_id):
        return f"Reported a red flag ({flag_id})."
    rf = content.red_flag(flag_id)
    phrase: str = rf["page_phrase_en"]
    fill: dict[str, str] = {}
    for name in re.findall(r"\{(\w+)\}", phrase):
        if name == "temp_c" and values.get("temp_c") is not None:
            fill[name] = _fmt_num(values["temp_c"])
        elif name == "stools_over_baseline" and values.get("stools_over_baseline") is not None:
            fill[name] = _fmt_num(values["stools_over_baseline"])
        elif name == "blood_note":
            fill[name] = ", with blood, mucus or black stool" if values.get("STOOL_BLOOD") == "yes" else ""
        elif name == "sob_detail" and (values.get("SOB_EXERTION") or values.get("SOB_SEV")):
            ex = values.get("SOB_EXERTION")
            fill[name] = _SOB_DETAIL.get(ex, "") if ex else f"rated {str(values['SOB_SEV']).replace('_', ' ')}"
        else:
            return f"Reports: {rf['label_en']}."
    if flag_id == "RF_DIARRHEA_SEVERE" and values.get("stools_over_baseline") is None:
        return f"Reports: {rf['label_en']}."
    return re.sub(r"\{(\w+)\}", lambda m: fill[m.group(1)], phrase)


def findings_sentence(flag_ids: list[str], values: dict[str, Any]) -> str:
    return " ".join(flag_phrase(f, values) for f in flag_ids)


def subject_id_spoken(subject_id: str) -> str:
    return ", ".join(" ".join(part) for part in subject_id.split("-"))


def build_message(
    *,
    escalation_id: str,
    level: str,
    subject_id: str,
    language: str,
    flag_ids: list[str],
    values: dict[str, Any],
    ack_token: str,
    backup: bool = False,
) -> PageMessage:
    tmpl_level = "emergency" if level == "emergency" else "urgent"
    note = content.page_template("interpreter_note") if language != "en" else ""
    text = content.page_template(tmpl_level).format(
        subject_id_spoken=subject_id,
        findings_sentence=findings_sentence(flag_ids, values),
        language_name=content.language_name(language, "en"),
        interpreter_note=note,
    )
    title = content.page_template("push_title")[tmpl_level].format(subject_id=subject_id)
    return PageMessage(escalation_id, level, title, text, ack_token, backup)


# ---- channels -----------------------------------------------------------------------------------------


def _ntfy(msg: PageMessage) -> PageResult:
    s = get_settings()
    topic = s.ntfy_backup_topic if msg.backup else s.ntfy_topic
    if not topic:
        raise RuntimeError("NTFY_TOPIC is not set")
    body = {
        "topic": topic,
        "title": msg.title,
        "message": msg.text,
        "priority": 5,
        "tags": ["rotating_light"],
        "actions": [
            {
                "action": "http",
                "label": "Acknowledge",
                "method": "POST",
                "url": f"{s.public_base_url.rstrip('/')}/webhooks/ntfy/ack/{msg.escalation_id}",
                "headers": {"Authorization": f"Bearer {msg.ack_token}"},
                "clear": True,
            }
        ],
    }
    r = httpx.post(f"{s.ntfy_server.rstrip('/')}/", json=body, timeout=5)
    r.raise_for_status()
    ref = str(r.json().get("id", ""))
    name = s.backup_investigator_name if msg.backup else s.oncall_nurse_name
    return PageResult("ntfy", name, ref)


def twiml_for(msg: PageMessage) -> str:
    s = get_settings()
    action = f"{s.public_base_url.rstrip('/')}/webhooks/twilio/page-ack?escalation_id={msg.escalation_id}"
    say = f"{msg.text} {content.page_template('voice_suffix')}"
    return (
        f'<Response><Gather numDigits="1" action="{escape(action)}" method="POST" timeout="10">'
        f"<Say>{escape(say)}</Say></Gather><Say>{escape(content.page_template('no_input'))}</Say></Response>"
    )


def _twilio_voice(msg: PageMessage) -> PageResult:
    from twilio.rest import Client

    s = get_settings()
    to = s.backup_investigator_phone if msg.backup else s.oncall_nurse_phone
    client = Client(s.twilio_account_sid, s.twilio_auth_token)
    status_cb = f"{s.public_base_url.rstrip('/')}/webhooks/twilio/page-status?escalation_id={msg.escalation_id}"
    call = client.calls.create(
        to=to,
        from_=s.twilio_from_number,
        twiml=twiml_for(msg),
        status_callback=status_cb,
        status_callback_event=["completed"],
    )
    name = s.backup_investigator_name if msg.backup else s.oncall_nurse_name
    return PageResult("twilio_voice", name, call.sid)


def _console(msg: PageMessage) -> PageResult:
    s = get_settings()
    log.warning("PAGE (console) %s | %s | %s", msg.escalation_id, msg.title, msg.text)
    name = s.backup_investigator_name if msg.backup else s.oncall_nurse_name
    return PageResult("console", name, f"console-{msg.escalation_id}")


def send(msg: PageMessage) -> PageResult:
    if _override is not None:
        return _override(msg)
    channel = get_settings().effective_pager_channel
    if channel == "ntfy":
        return _ntfy(msg)
    if channel == "twilio_voice":
        return _twilio_voice(msg)
    return _console(msg)
