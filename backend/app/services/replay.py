"""Demo replay (docs/01 Flow D): play scenarios/<id>.json through the same service functions as a live call.

Events: call_started · tool (record_answer, report_red_flag, ...) · page_ack · call_ended · post_call.
checkin_id is injected into every tool body. REPLAY_SPEED (env, default 1.0) scales the timing.
"""

import json
import logging
import os
import threading
import time
from typing import Any

from sqlmodel import Session, select

from app.config import SCENARIOS_DIR
from app.db import new_session
from app.errors import ApiError
from app.models import CheckIn, Escalation, Patient
from app.services import checkins as checkin_svc
from app.services import escalation, gemini
from app.timeutil import utcnow

log = logging.getLogger("bv.replay")


def list_scenarios() -> list[dict[str, Any]]:
    out = []
    for p in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "events" not in d:
            continue
        out.append({"id": d["id"], "title": d.get("title", d["id"]), "patient_id": d["patient_id"],
                    "duration_s": max((e.get("t", 0) for e in d["events"]), default=0)})
    return out


def load(scenario_id: str) -> dict[str, Any]:
    p = SCENARIOS_DIR / f"{scenario_id}.json"
    if not p.exists() or "/" in scenario_id:
        raise ApiError(404, "scenario_not_found", f"scenario {scenario_id} not found")
    return json.loads(p.read_text(encoding="utf-8"))


def start(session: Session, scenario_id: str, speed: float | None = None, run_async: bool = True) -> str:
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
    speed = speed or float(os.environ.get("REPLAY_SPEED", "1.0"))
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
