#!/usr/bin/env python3
"""Export a real ElevenLabs call as a recorded replay scenario (WS1 V11).

Run from the repo root after a real call against the live backend (WS1 V10):

    uv run --project backend python agent/export_scenario.py --conversation-id conv_... --checkin-id ci_... \\
        --id rec_en_g2 --title "James, English, standard, grade 2 diarrhea" [--audio]

It reads
  * the conversation from ElevenLabs, `GET /v1/convai/conversations/{id}`: transcript turns and the agent's
    tool calls, each with seconds from call start;
  * the check-in from the backend the call ran against, `GET {--api}/api/checkins/{id}`: the synthetic patient,
    the day after dose and the escalation acknowledgment time;
and writes `scenarios/<id>.json` in the replay format (docs/04-voice-agent.md § Replay format) with
`recorded: true`, `recorded_at` (local date in DISPLAY_TZ), the recorded label and a consent note in `_about`.
`--audio` also saves the call audio (`GET /v1/convai/conversations/{id}/audio`) as `scenarios/audio/<id>.mp3`,
which is gitignored and never committed.

Field whitelist (CLAUDE.md rule 8). The scenario holds only:
  * transcript turns: `role`, `text`, `t_s` (seconds from call start);
  * tool calls: tool name, the arguments declared in agent/tools.json (minus `checkin_id` and
    `conversation_id`; the replay engine injects the check-in), seconds from call start;
  * the escalation acknowledgment time (`page_ack`; acknowledged by the generic "RN on call", never a name);
  * provenance: `id`, `title`, `patient_id`, `day_after_dose`, `recorded`, `recorded_at`, `label`, `_about`,
    `audio`, and `agent_id_suffix` / `conversation_id_suffix` (the last 4 characters only).
Everything else (caller identifiers, dynamic variables, phone numbers, user IDs, analysis blocks, tool results,
LLM metadata) is dropped. check_whitelist() re-checks the finished document before anything is written.

A human reads every exported transcript before it is committed, to catch a real name or number spoken
off-script. The script prints that reminder and never prints transcript text itself.

Offline: `--conversation-file` / `--checkin-file` read saved JSON instead of calling the APIs.
Needs in `.env` (or the environment): ELEVENLABS_API_KEY; LIVE_API (else `--api`, else PUBLIC_BASE_URL);
BV_DASHBOARD_TOKEN when the live instance has one (sent as X-BV-Token). Optional: DISPLAY_TZ.
Dependencies: stdlib; httpx only for the network reads (the backend's uv environment has it).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_agent import API_BASE, load_env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = ROOT / "scenarios"
TOOLS_PATH = ROOT / "agent" / "tools.json"
PATIENTS_PATH = ROOT / "data" / "patients.json"

RECORDED_LABEL = "Recorded real call; synthetic patient played by a teammate"  # = app.services.replay
ABOUT = (
    "RECORDED real call, exported by agent/export_scenario.py (WS1 V11) from ElevenLabs conversation "
    "...{conv} and the backend check-in. Synthetic patient played by a teammate. Consent: the teammate agreed to "
    "the recording and to this transcript export before it was run; serving the audio from the public demo needs "
    "their written consent (otherwise transcript-only). Only whitelisted fields are kept: transcript turns, tool calls "
    "(declared arguments only), the acknowledgment time and provenance; agent and conversation IDs are cut to "
    "their last 4 characters. A human reads this transcript before it is committed (a real name or number "
    "spoken off-script). Format: docs/04-voice-agent.md § Replay format; checkin_id is injected by the replay "
    "engine."
)
ACK_BY = "RN on call"  # never the real acknowledger's name
ACK_METHODS = frozenset({"push_button", "phone_keypress", "dashboard"})
PAGED_LEVELS = frozenset({"urgent", "emergency"})  # what the replay's page_ack acknowledges
END_CALL_TOOL = "end_call"
END_CALL_REASON = "end_call tool was called."
ID_SUFFIX_CHARS = 4
INJECTED_TOOL_ARGS = frozenset({"checkin_id", "conversation_id"})
SCENARIO_ID = re.compile(r"^[A-Za-z0-9_-]+$")  # = app.services.replay._SAFE_ID
TEXT_ROLES = frozenset({"agent", "user"})
LONG_NUMBER = re.compile(r"\d(?:[\s().-]?\d){6,}")  # 7+ digits: a phone or record number to check by hand

# The whitelist, as a structure: the only keys a scenario document may hold.
TOP_LEVEL_KEYS = frozenset({
    "_about", "id", "title", "patient_id", "day_after_dose", "recorded", "recorded_at", "label",
    "agent_id_suffix", "conversation_id_suffix", "audio", "events",
})
EVENT_KEYS = {
    "call_started": frozenset({"t", "type"}),
    "tool": frozenset({"t", "type", "tool", "body"}),
    "page_ack": frozenset({"t", "type", "by", "method"}),
    "call_ended": frozenset({"t", "type", "termination_reason"}),
    "post_call": frozenset({"t", "type", "transcript"}),
}
TURN_KEYS = frozenset({"role", "text", "t_s"})
SCALARS = (str, int, float, bool, type(None))


class ExportError(Exception):
    """A problem the user must fix; the message is shown as is (never contains a key or transcript text)."""


# ---------------------------------------------------------------- small helpers


def suffix(value: str) -> str:
    return value[-ID_SUFFIX_CHARS:]


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


def tool_arg_whitelist(path: Path = TOOLS_PATH) -> dict[str, frozenset[str]]:
    """{tool name: argument names it may keep}: the request body properties in agent/tools.json, minus the IDs."""
    tools = json.loads(path.read_text(encoding="utf-8"))["tools"]
    out = {}
    for t in tools:
        props = (t.get("api_schema", {}).get("request_body_schema") or {}).get("properties") or {}
        out[t["name"]] = frozenset(props) - INJECTED_TOOL_ARGS
    return out


def known_patients(path: Path = PATIENTS_PATH) -> set[str]:
    try:
        return {p["id"] for p in json.loads(path.read_text(encoding="utf-8"))["patients"]}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return round(float(value), 1)


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def local_date(unix_secs: float, tz_name: str) -> date:
    """The DISPLAY_TZ date of a call start (docs/03 §6.4); UTC if the zone is unknown."""
    try:
        tz: Any = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = UTC
    return datetime.fromtimestamp(unix_secs, tz=tz).date()


# ---------------------------------------------------------------- the whitelist check


def check_whitelist(doc: Any, tool_args: dict[str, frozenset[str]]) -> list[str]:
    """Every key outside the whitelist (empty list = clean). Values nested under a whitelisted key must be scalars,
    except the documented containers (events, body, transcript)."""
    bad: list[str] = []
    if not isinstance(doc, dict):
        return ["$: not an object"]
    bad += [f"$.{k}" for k in doc if k not in TOP_LEVEL_KEYS]
    bad += [f"$.{k}: not a scalar" for k, v in doc.items() if k != "events" and not isinstance(v, SCALARS)]
    for k in ("agent_id_suffix", "conversation_id_suffix"):
        if isinstance(doc.get(k), str) and len(doc[k]) > ID_SUFFIX_CHARS:
            bad.append(f"$.{k}: longer than {ID_SUFFIX_CHARS} characters")
    events = doc.get("events")
    if not isinstance(events, list):
        return bad + ["$.events: not a list"]
    for i, ev in enumerate(events):
        where = f"$.events[{i}]"
        allowed = EVENT_KEYS.get(ev.get("type")) if isinstance(ev, dict) else None
        if allowed is None:
            bad.append(f"{where}: unknown event")
            continue
        bad += [f"{where}.{k}" for k in ev if k not in allowed]
        bad += [f"{where}.{k}: not a scalar" for k, v in ev.items()
                if k not in ("body", "transcript") and not isinstance(v, SCALARS)]
        if ev["type"] == "tool":
            body = ev.get("body")
            keep = tool_args.get(ev.get("tool"))
            if keep is None:
                bad.append(f"{where}.tool: not a tool in agent/tools.json")
            elif not isinstance(body, dict):
                bad.append(f"{where}.body: not an object")
            else:
                bad += [f"{where}.body.{k}" for k in body if k not in keep]
                bad += [f"{where}.body.{k}: not a scalar" for k, v in body.items() if not isinstance(v, SCALARS)]
        if ev["type"] == "page_ack" and ev.get("by") != ACK_BY:
            bad.append(f"{where}.by: must be {ACK_BY!r}")
        if ev["type"] == "post_call":
            turns = ev.get("transcript")
            if not isinstance(turns, list):
                bad.append(f"{where}.transcript: not a list")
                continue
            for j, turn in enumerate(turns):
                if not isinstance(turn, dict):
                    bad.append(f"{where}.transcript[{j}]: not an object")
                    continue
                bad += [f"{where}.transcript[{j}].{k}" for k in turn if k not in TURN_KEYS]
                bad += [f"{where}.transcript[{j}].{k}: not a scalar" for k, v in turn.items()
                        if not isinstance(v, SCALARS)]
    return bad


# ---------------------------------------------------------------- building the scenario


def check_link(conversation: dict[str, Any], checkin: dict[str, Any], conversation_id: str, checkin_id: str) -> list[str]:
    """Reasons the conversation and the check-in may not belong together (IDs shown as suffixes only)."""
    problems = []
    conv_id = conversation.get("conversation_id")
    if conv_id != conversation_id:
        problems.append(f"the conversation read is ...{suffix(str(conv_id))}, not ...{suffix(conversation_id)}")
    if checkin.get("id") != checkin_id:
        problems.append(f"the check-in read is ...{suffix(str(checkin.get('id')))}, not ...{suffix(checkin_id)}")
    stored = checkin.get("el_conversation_id")
    dyn = ((conversation.get("conversation_initiation_client_data") or {}).get("dynamic_variables") or {}).get(
        "checkin_id")
    if stored and stored != conversation_id:
        problems.append(f"check-in ...{suffix(checkin_id)} belongs to conversation ...{suffix(str(stored))}")
    if dyn and dyn != checkin_id:
        problems.append(f"conversation ...{suffix(conversation_id)} was started for check-in ...{suffix(str(dyn))}")
    if not stored and not dyn:
        problems.append("nothing links the conversation to the check-in (no el_conversation_id, no checkin_id "
                        "dynamic variable)")
    status = conversation.get("status")
    if status is not None and status != "done":
        problems.append(f"conversation status is {status!r}, not 'done' (the transcript may be incomplete)")
    return problems


def _tool_events(transcript: list[Any], tool_args: dict[str, frozenset[str]],
                 warnings: list[str]) -> tuple[list[dict[str, Any]], bool]:
    events: list[dict[str, Any]] = []
    ended_by_tool = False
    for turn in transcript:
        if not isinstance(turn, dict):
            continue
        t = _seconds(turn.get("time_in_call_secs"))
        for call in turn.get("tool_calls") or []:
            if not isinstance(call, dict) or call.get("tool_has_been_called") is False:
                continue
            name = call.get("tool_name")
            if name == END_CALL_TOOL:
                ended_by_tool = True
                continue
            keep = tool_args.get(name) if isinstance(name, str) else None
            if keep is None:
                continue  # system tools (skip_turn, language detection, ...) are not replayed
            if t is None:
                warnings.append(f"{name}: no time_in_call_secs; tool call skipped")
                continue
            try:
                params = json.loads(call.get("params_as_json") or "{}")
            except (TypeError, ValueError):
                warnings.append(f"{name} at {t} s: params_as_json is not JSON; tool call skipped")
                continue
            if not isinstance(params, dict):
                warnings.append(f"{name} at {t} s: arguments are not an object; tool call skipped")
                continue
            body = {k: v for k, v in params.items() if k in keep and isinstance(v, SCALARS)}
            dropped = sorted(k for k in params if k not in body and k not in INJECTED_TOOL_ARGS)
            if dropped:  # names only, never values
                warnings.append(f"{name} at {t} s: dropped arguments {dropped}")
            if not body:
                warnings.append(f"{name} at {t} s: no whitelisted argument left")
            events.append({"t": t, "type": "tool", "tool": name, "body": body})
    return events, ended_by_tool


def _turns(transcript: list[Any]) -> list[dict[str, Any]]:
    turns = []
    for turn in transcript:
        if not isinstance(turn, dict) or turn.get("role") not in TEXT_ROLES:
            continue
        text, t = turn.get("message"), _seconds(turn.get("time_in_call_secs"))
        if isinstance(text, str) and text.strip() and t is not None:
            turns.append({"role": turn["role"], "text": text.strip(), "t_s": t})
    return turns


def _ack_event(checkin_detail: dict[str, Any], start_unix: float | None, tool_events: list[dict[str, Any]],
               warnings: list[str]) -> dict[str, Any] | None:
    acks = []
    for e in checkin_detail.get("escalations") or []:
        if isinstance(e, dict) and e.get("level") in PAGED_LEVELS:
            at = parse_utc(e.get("acknowledged_at"))
            if at is not None:
                acks.append((at, e.get("ack_method")))
    if not acks:
        return None
    if start_unix is None:
        warnings.append("no call start time: the acknowledgment time cannot be placed; page_ack left out")
        return None
    at, method = min(acks, key=lambda a: a[0])
    t = round(at.timestamp() - start_unix, 1)
    if t < 0:
        warnings.append(f"acknowledgment is {t} s before the call start (clock mismatch?); page_ack left out")
        return None
    if not any(ev["t"] <= t for ev in tool_events):
        warnings.append(f"page_ack at {t} s comes before every tool call; the replay will acknowledge nothing")
    ev: dict[str, Any] = {"t": t, "type": "page_ack", "by": ACK_BY}
    if method in ACK_METHODS:
        ev["method"] = method
    return ev


def build_scenario(
    conversation: dict[str, Any],
    checkin_detail: dict[str, Any],
    *,
    scenario_id: str,
    title: str | None = None,
    recorded_at: date | None = None,
    audio: str | None = None,
    tz_name: str = "America/New_York",
    tool_args: dict[str, frozenset[str]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """The whitelisted scenario document and warnings. No network; reads only agent/tools.json and
    data/patients.json (to warn about a patient the demo database does not seed)."""
    tool_args = tool_args if tool_args is not None else tool_arg_whitelist()
    warnings: list[str] = []
    checkin = checkin_detail.get("checkin") or {}
    transcript = conversation.get("transcript") or []
    if not isinstance(transcript, list) or not transcript:
        raise ExportError("the conversation has no transcript")
    patient_id = checkin.get("patient_id")
    if not isinstance(patient_id, str) or not patient_id:
        raise ExportError("the check-in has no patient_id")
    if patient_id not in known_patients():
        warnings.append(f"{patient_id} is not in data/patients.json, so the demo database cannot replay it")

    meta = conversation.get("metadata") or {}
    start_unix = _seconds(meta.get("start_time_unix_secs"))
    if start_unix is None:
        started = parse_utc(checkin.get("started_at"))
        start_unix = started.timestamp() if started else None
        warnings.append("no start_time_unix_secs in the conversation; the check-in's started_at is the call start")

    tool_events, ended_by_tool = _tool_events(transcript, tool_args, warnings)
    turns = _turns(transcript)
    if not tool_events:
        warnings.append("no tool calls: the replay will grade nothing")
    end_t = _seconds(meta.get("call_duration_secs"))
    if end_t is None:
        end_t = max([e["t"] for e in tool_events] + [t["t_s"] for t in turns] + [0.0])
        warnings.append("no call_duration_secs; the last turn ends the call")

    events: list[dict[str, Any]] = [{"t": 0.0, "type": "call_started"}, *tool_events]
    ack = _ack_event(checkin_detail, start_unix, tool_events, warnings)
    if ack is not None:
        events.append(ack)
    ended: dict[str, Any] = {"t": end_t, "type": "call_ended"}
    if ended_by_tool:
        ended["termination_reason"] = END_CALL_REASON
    events += [ended, {"t": end_t, "type": "post_call", "transcript": turns}]
    events.sort(key=lambda e: e["t"])  # stable: call_ended stays before post_call

    if recorded_at is None:
        if start_unix is None:
            raise ExportError("no call start time to date the recording; pass --recorded-at YYYY-MM-DD")
        recorded_at = local_date(start_unix, tz_name)
    conv_id = str(conversation.get("conversation_id") or "")
    agent_id = str(conversation.get("agent_id") or "")
    doc: dict[str, Any] = {
        "_about": ABOUT.format(conv=suffix(conv_id)),
        "id": scenario_id,
        "title": title or f"Recorded call: {patient_id}, {checkin.get('agent_variant') or 'unknown variant'}",
        "patient_id": patient_id,
        "day_after_dose": checkin.get("day_after_dose") if isinstance(checkin.get("day_after_dose"), int) else None,
        "recorded": True,
        "recorded_at": recorded_at.isoformat(),
        "label": RECORDED_LABEL,
        "agent_id_suffix": suffix(agent_id) if agent_id else None,
        "conversation_id_suffix": suffix(conv_id) if conv_id else None,
    }
    if audio:
        doc["audio"] = audio
    doc["events"] = events

    for i, turn in enumerate(turns):
        if LONG_NUMBER.search(turn["text"]):
            warnings.append(f"transcript turn {i} ({turn['role']}, {turn['t_s']} s) holds a long number: check it")
    for ev in tool_events:
        if any(isinstance(v, str) and LONG_NUMBER.search(v) for v in ev["body"].values()):
            warnings.append(f"{ev['tool']} at {ev['t']} s holds a long number: check it")
    bad = check_whitelist(doc, tool_args)
    if bad:  # cannot happen unless the code above is changed; never write a document that fails it
        raise ExportError(f"whitelist check failed: {bad}")
    return doc, warnings


# ---------------------------------------------------------------- reading and writing


def http_get(url: str, headers: dict[str, str], *, binary: bool = False) -> Any:
    try:
        import httpx
    except ImportError:
        raise ExportError("httpx is missing: run with `uv run --project backend python agent/export_scenario.py`") from None
    try:
        r = httpx.get(url, headers=headers, timeout=60.0, follow_redirects=True)
    except httpx.HTTPError as e:
        raise ExportError(f"network error on GET {url}: {type(e).__name__}") from None
    if r.status_code >= 400:
        hint = " (set BV_DASHBOARD_TOKEN for the live instance)" if r.status_code == 401 else ""
        raise ExportError(f"GET {url} -> HTTP {r.status_code}{hint}")
    if binary:
        return r.content
    try:
        return r.json()
    except ValueError:
        raise ExportError(f"GET {url}: response is not JSON") from None


def elevenlabs_headers() -> dict[str, str]:
    key = env("ELEVENLABS_API_KEY")
    if not key:
        raise ExportError("ELEVENLABS_API_KEY is empty (see .env.example)")
    return {"xi-api-key": key}


def backend_base(api: str | None) -> str:
    base = (api or env("LIVE_API") or env("PUBLIC_BASE_URL")).rstrip("/")
    if not base:
        raise ExportError("no backend URL: pass --api or set LIVE_API (the backend the call ran against)")
    return base


def backend_headers() -> dict[str, str]:
    token = env("BV_DASHBOARD_TOKEN")
    return {"X-BV-Token": token} if token else {}


def read_json_file(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ExportError(f"cannot read {path}: {type(e).__name__}") from None
    if not isinstance(data, dict):
        raise ExportError(f"{path}: not a JSON object")
    return data


def read_conversation(args: argparse.Namespace) -> dict[str, Any]:
    if args.conversation_file:
        data = read_json_file(args.conversation_file)
        return data.get("data", data) if data.get("type") == "post_call_transcription" else data
    return http_get(f"{API_BASE}/v1/convai/conversations/{args.conversation_id}", elevenlabs_headers())


def read_checkin(args: argparse.Namespace) -> dict[str, Any]:
    if args.checkin_file:
        return read_json_file(args.checkin_file)
    return http_get(f"{backend_base(args.api)}/api/checkins/{args.checkin_id}", backend_headers())


def read_audio(conversation_id: str) -> bytes:
    return http_get(f"{API_BASE}/v1/convai/conversations/{conversation_id}/audio", elevenlabs_headers(), binary=True)


def audio_is_gitignored(path: Path) -> bool:
    """True when git ignores `path` (inside this repo) or `path` is outside the repo; False if git would track it."""
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return True
    try:
        r = subprocess.run(["git", "check-ignore", "-q", str(rel)], cwd=ROOT, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export a real call as a recorded replay scenario (WS1 V11).")
    p.add_argument("--conversation-id", required=True, help="ElevenLabs conversation ID (conv_...)")
    p.add_argument("--checkin-id", required=True, help="backend check-in ID of the call (ci_...)")
    p.add_argument("--id", required=True, dest="scenario_id", help="scenario ID: scenarios/<id>.json")
    p.add_argument("--title", help="scenario title (default: patient and agent variant)")
    p.add_argument("--audio", action="store_true", help="also save scenarios/audio/<id>.mp3 (gitignored)")
    p.add_argument("--api", help="backend base URL (default: LIVE_API, then PUBLIC_BASE_URL)")
    p.add_argument("--recorded-at", type=date.fromisoformat, help="local date of the call (default: from start)")
    p.add_argument("--force", action="store_true", help="overwrite an existing scenarios/<id>.json")
    p.add_argument("--skip-link-check", action="store_true",
                   help="export even if nothing confirms the conversation belongs to the check-in")
    p.add_argument("--out-dir", type=Path, default=SCENARIOS_DIR, help=argparse.SUPPRESS)
    p.add_argument("--conversation-file", help="read the conversation from this JSON file (offline)")
    p.add_argument("--checkin-file", help="read GET /api/checkins/{id} output from this JSON file (offline)")
    return p.parse_args(argv)


def looks_like_mp3(data: bytes) -> bool:
    return data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)


def export(args: argparse.Namespace) -> Path:
    if not SCENARIO_ID.match(args.scenario_id):
        raise ExportError(f"--id must be letters, digits, '_' or '-': {args.scenario_id!r}")
    out_dir: Path = args.out_dir
    path = out_dir / f"{args.scenario_id}.json"
    if path.exists() and not args.force:
        raise ExportError(f"{path} exists; pass --force to overwrite it")
    audio_file = out_dir / "audio" / f"{args.scenario_id}.mp3"
    if args.audio and not audio_is_gitignored(audio_file):
        raise ExportError(f"{audio_file} would not be gitignored; audio is never committed (.gitignore)")

    conversation = read_conversation(args)
    detail = read_checkin(args)
    problems = check_link(conversation, detail.get("checkin") or {}, args.conversation_id, args.checkin_id)
    if problems and not args.skip_link_check:
        raise ExportError("the conversation and the check-in do not match:\n  - " + "\n  - ".join(problems)
                          + "\n(pass --skip-link-check only if you are sure they are the same call)")
    if args.audio and conversation.get("has_audio") is False:
        raise ExportError("ElevenLabs has no audio for this conversation; rerun without --audio")

    doc, warnings = build_scenario(
        conversation, detail, scenario_id=args.scenario_id, title=args.title, recorded_at=args.recorded_at,
        audio=f"scenarios/audio/{args.scenario_id}.mp3" if args.audio else None,
        tz_name=env("DISPLAY_TZ") or "America/New_York",
    )
    if args.audio:
        data = read_audio(args.conversation_id)
        if not data:
            raise ExportError("the conversation audio is empty")
        if not looks_like_mp3(data):
            warnings.append("the audio does not start like an MP3 file; play it before the demo")
        audio_file.parent.mkdir(parents=True, exist_ok=True)
        audio_file.write_bytes(data)
        print(f"  saved audio ({len(data)} bytes) to {audio_file} (gitignored; never commit it)")
    for p in problems:
        print(f"  warning (--skip-link-check): {p}")
    for w in warnings:
        print(f"  warning: {w}")
    write_json(path, doc)
    tools: dict[str, int] = {}
    for ev in doc["events"]:
        if ev["type"] == "tool":
            tools[ev["tool"]] = tools.get(ev["tool"], 0) + 1
    post = next(e for e in doc["events"] if e["type"] == "post_call")
    ack = next((e["t"] for e in doc["events"] if e["type"] == "page_ack"), None)
    print(f"  wrote {path}: {len(post['transcript'])} transcript turns, tool calls {tools}, "
          f"page_ack {'at ' + str(ack) + ' s' if ack is not None else 'none'}, call end {post['t']} s, "
          f"recorded_at {doc['recorded_at']}")
    print("  BEFORE COMMITTING: read every transcript turn and tool argument in that file (a real name or "
          "number spoken off-script must not reach git).")
    return path


def main(argv: list[str] | None = None) -> int:
    load_env()
    args = parse_args(argv)
    try:
        export(args)
    except ExportError as e:
        print(f"export_scenario: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
