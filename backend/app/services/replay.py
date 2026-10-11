"""Demo replay (docs/01 Flow D): play scenarios/<id>.json through the same service functions as a live call.

Events: call_started · tool (record_answer, report_red_flag, ...) · page_ack · call_ended · post_call.
checkin_id is injected into every tool body. Timing is scaled by the playback multiplier (docs/03 §6.2): the
`?speed=` parameter, then REPLAY_SPEED, then 2 in demo mode. Scenario provenance (scripted or recorded) is
reported by list_scenarios().
"""

import json
import logging
import re
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.config import SCENARIOS_DIR, get_settings
from app.db import new_session
from app.errors import ApiError
from app.models import CheckIn, Escalation, Patient
from app.services import checkins as checkin_svc
from app.services import escalation, gemini
from app.timeutil import utcnow

log = logging.getLogger("bv.replay")

DEMO_DEFAULT_SPEED = 2.0  # docs/03 §6.2: default multiplier in demo mode
REAL_TIME_SPEED = 1.0  # outside demo mode (direct service calls), unless a speed is given
# Scenario labels (docs/03 §6.2). A scenario that is not marked `recorded: true` is always "Scripted", so a
# scripted replay is never presented as a real call (docs/10 § data_origin).
SCRIPTED_LABEL = "Scripted"
RECORDED_LABEL = "Recorded real call; synthetic patient played by a teammate"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def resolve_speed(requested: float | None = None) -> float:
    """Playback multiplier: `requested` (the ?speed= value), then REPLAY_SPEED, then 2 in demo mode.

    Outside demo mode (tests and scripts calling start() directly) the fallback is real time.
    """
    if requested is not None:
        return float(requested)
    settings = get_settings()
    if settings.replay_speed is not None:
        return settings.replay_speed
    return DEMO_DEFAULT_SPEED if settings.demo_mode else REAL_TIME_SPEED


def audio_path(scenario_id: str) -> Path | None:
    """`scenarios/audio/<id>.mp3`, or None for an ID that is not a plain slug. Recorded calls' audio is gitignored and
    never committed; scripted scenarios' synthesized audio (agent/synthesize_scenario.py) is committed."""
    if not _SAFE_ID.match(scenario_id):
        return None
    return SCENARIOS_DIR / "audio" / f"{scenario_id}.mp3"


def audio_url(scenario_id: str) -> str | None:
    """The scenario audio route (docs/03 §6.2), only when the mp3 exists on this server."""
    path = audio_path(scenario_id)
    if path is None or not path.is_file():
        return None
    return f"/api/demo/scenarios/{scenario_id}/audio"


def scenario_audio_file(scenario_id: str) -> Path:
    """The mp3 behind `GET /api/demo/scenarios/{id}/audio` (docs/03 §6.2, WS1 V11).

    404 `scenario_not_found` when `scenarios/<id>.json` does not exist (or the ID is not a plain slug), then
    404 `audio_not_found` when `scenarios/audio/<id>.mp3` is absent. Audio is gitignored and never committed; a
    recorded call's audio is on a server only when the teammate who played the patient consented in writing.
    """
    path = audio_path(scenario_id)
    if path is None or not (SCENARIOS_DIR / f"{scenario_id}.json").is_file():
        raise ApiError(404, "scenario_not_found", f"scenario {scenario_id} not found")
    if not path.is_file():
        raise ApiError(404, "audio_not_found", f"no audio for scenario {scenario_id} on this server")
    return path


def _recorded_at(value: Any, scenario_id: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        log.warning("scenario_recorded_at_invalid scenario=%s value=%r", scenario_id, value)
        return None


def provenance(scenario_id: str, sc: dict[str, Any]) -> dict[str, Any]:
    """`recorded`, `recorded_at`, `label`, `audio_url` for one scenario file (docs/03 §6.2)."""
    recorded = sc.get("recorded") is True
    label = sc.get("label")
    if not recorded:
        label = SCRIPTED_LABEL
    elif not isinstance(label, str) or not label.strip():
        label = RECORDED_LABEL
    return {
        "recorded": recorded,
        "recorded_at": _recorded_at(sc.get("recorded_at"), scenario_id) if recorded else None,
        "label": label,
        "audio_url": audio_url(scenario_id),
    }


def list_scenarios() -> list[dict[str, Any]]:
    """Scenarios by their optional `order` (the first is the demo default), then by file name."""
    found = []
    for p in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict) or "events" not in d:
            continue
        sid = d.get("id", p.stem)
        order = d.get("order") if isinstance(d.get("order"), int) else 1_000
        found.append((order, {"id": sid, "title": d.get("title", sid), "patient_id": d["patient_id"],
                              "duration_s": max((e.get("t", 0) for e in d["events"]), default=0),
                              **provenance(sid, d)}))
    return [s for _, s in sorted(found, key=lambda x: x[0])]


def load(scenario_id: str) -> dict[str, Any]:
    p = SCENARIOS_DIR / f"{scenario_id}.json"
    if not p.exists() or "/" in scenario_id:
        raise ApiError(404, "scenario_not_found", f"scenario {scenario_id} not found")
    return json.loads(p.read_text(encoding="utf-8"))


def start(session: Session, scenario_id: str, speed: float | None = None, run_async: bool = True) -> str:
    """Create the replay check-in and play the scenario; `speed` None means resolve_speed()'s fallbacks."""
    speed = resolve_speed(speed)
    if not speed > 0:
        raise ValueError(f"replay speed must be positive, got {speed!r}")
    sc = load(scenario_id)
    patient = session.get(Patient, sc["patient_id"])
    if patient is None:
        raise ApiError(404, "patient_not_found", f"scenario patient {sc['patient_id']} not seeded")
    live = checkin_svc.live_checkin(session, patient.id)
    if live:  # a stuck rehearsal shouldn't block the demo
        live.status = "cancelled"
        session.add(live)
        session.flush()
    c = checkin_svc.new_checkin(session, patient, "replay", sc.get("day_after_dose"), "demo", "system")
    c.el_conversation_id = f"replay_{c.id}"
    session.add(c)
    session.commit()
    gemini.KNOWN_TRANSLATIONS.update(sc.get("translations_en", {}))
    log.info("replay_started checkin_id=%s scenario=%s speed=%s", c.id, scenario_id, speed)
    if run_async:
        threading.Thread(target=_run, args=(c.id, sc, speed), daemon=True, name=f"replay-{c.id}").start()
    else:
        _run(c.id, sc, speed)
    return c.id


def _run(checkin_id: str, sc: dict[str, Any], speed: float) -> None:
    from app.routers.agent_tools import call_tool_inprocess
    from app.routers.webhooks import process_post_call

    t0 = time.monotonic()
    for ev in sorted(sc["events"], key=lambda e: e.get("t", 0)):
        wait = ev.get("t", 0) / max(speed, 0.001) - (time.monotonic() - t0)
        if wait > 0:
            time.sleep(wait)
        try:
            with new_session() as s:
                c = s.get(CheckIn, checkin_id)
                if c is None or c.status == "cancelled":
                    log.info("replay_stopped checkin_id=%s", checkin_id)
                    return
                kind = ev["type"]
                if kind == "call_started":
                    c.status, c.started_at = "in_progress", utcnow()
                    s.add(c)
                    s.commit()
                elif kind == "tool":
                    env = call_tool_inprocess(ev["tool"], {**ev.get("body", {}), "checkin_id": checkin_id}, s)
                    log.info("replay_tool checkin_id=%s tool=%s next=%s", checkin_id, ev["tool"], env.next.item_code)
                elif kind == "page_ack":
                    for e in s.exec(select(Escalation).where(Escalation.checkin_id == checkin_id, Escalation.status == "open",
                                                             Escalation.level.in_(("urgent", "emergency")))).all():  # type: ignore[attr-defined]
                        escalation.acknowledge(s, e, by=ev.get("by", "RN on call"), method=ev.get("method", "push_button"))
                    s.commit()
                elif kind == "call_ended":
                    c.ended_at = utcnow()
                    c.termination_reason = ev.get("termination_reason")
                    s.add(c)
                    s.commit()
                elif kind == "post_call":
                    turns = ev.get("transcript", [])
                    data = {
                        "conversation_id": c.el_conversation_id,
                        "transcript": [{"role": t["role"], "message": t["text"], "time_in_call_secs": t.get("t_s")} for t in turns],
                        "metadata": {"call_duration_secs": int(ev.get("t", 0)), "termination_reason": c.termination_reason,
                                     "main_language": c.language},
                        "analysis": {"transcript_summary": sc.get("summary_en")},
                        "conversation_initiation_client_data": {"dynamic_variables": {"checkin_id": checkin_id}},
                    }
                    s.close()
                    process_post_call(data)
        except Exception:  # noqa: BLE001
            log.exception("replay_event_failed checkin_id=%s event=%s", checkin_id, ev.get("type"))
    log.info("replay_done checkin_id=%s", checkin_id)
