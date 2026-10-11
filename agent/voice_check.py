#!/usr/bin/env python3
"""Log one real browser call against the live backend in eval/results/voice_checks.json (WS1 V10).

Run from the repo root after each call (procedure and checklist: agent/README.md):

    uv run --project backend python agent/voice_check.py --checkin-id ci_... --scenario james_g2_diarrhea \\
        [--conversation-id conv_...] [--backend render-live|tunnel] [--dry-run]

It reads
  * the conversation from ElevenLabs, `GET /v1/convai/conversations/{id}`: the first agent turn, the patient
    turns and the tool calls and results, each with seconds from call start, and the call start time;
  * the check-in from the backend the call ran against, `GET {--api}/api/checkins/{id}`: language, variant,
    findings and escalations (`paged_at`, `acknowledged_at`);
and writes one row (docs/03-api-contracts.md §6.11):
  * `disclosure_first_turn`: the first agent turn contains the approved first message for the call's language
    (data/scripts.json `lines.first_message`, `{study_team_name}` from data/study.json, any other `{variable}`
    matches any text);
  * `paged`, `page_level`, `red_flag_ids`: from the urgent or emergency escalations that were paged;
  * `utterance_to_page_s`: first `paged_at` minus the start of the patient turn that triggered the page (the last
    patient turn before the first tool call whose result says `escalated: true`);
  * `page_to_ack_s`: `acknowledged_at - paged_at` of that escalation (null until acknowledged);
  * `term`, `grade`, `rule_id`: the finding for the planned term (else the highest provisional grade).
The row fills the pending row of the same `--scenario` in place; rerunning for the same conversation updates it.
The header gets `run_at` (earliest logged call start), `backend` and `agent_llm` (agent/deployed_snapshot.json).

Nothing here grades or decides anything: grades, rule IDs and pages are read from the backend, which applies the
fixed rules (CLAUDE.md rule 1). The script never prints a key or token, and stores and prints IDs cut to their
prefix and last 4 characters (`conv_...9s0t`).

Offline: `--conversation-file` / `--checkin-file` read saved JSON instead of calling the APIs.
Needs in `.env` (or the environment): ELEVENLABS_API_KEY; LIVE_API (else `--api`, else PUBLIC_BASE_URL);
BV_DASHBOARD_TOKEN when the live instance has one (sent as X-BV-Token).
Dependencies: stdlib; httpx only for the network reads (the backend's uv environment has it).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export_scenario as ex  # noqa: E402
from sync_agent import API_BASE, load_env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VOICE_CHECKS = ROOT / "eval" / "results" / "voice_checks.json"
SNAPSHOT = ROOT / "agent" / "deployed_snapshot.json"
SCRIPTS = ROOT / "data" / "scripts.json"
STUDY = ROOT / "data" / "study.json"

PAGED_LEVELS = frozenset({"urgent", "emergency"})  # = backend app.services.escalation.PAGED_LEVELS
BACKENDS = ("render-live", "tunnel")
PENDING, LOGGED = "pending", "logged"
ID_SUFFIX_CHARS = 4
# Key order of a row (docs/03 §6.11 first, then the optional fields).
ROW_KEYS = ("variant", "conversation_id", "checkin_id", "scenario", "status", "started_at", "disclosure_first_turn",
            "red_flag_expected", "paged", "page_level", "red_flag_ids", "utterance_to_page_s", "page_to_ack_s",
            "term", "grade", "rule_id", "expected")
# Everything a call measures: null on a pending row.
MEASURED_KEYS = ("conversation_id", "checkin_id", "started_at", "disclosure_first_turn", "paged", "page_level",
                 "red_flag_ids", "utterance_to_page_s", "page_to_ack_s", "term", "grade", "rule_id")
SHORT_ID = re.compile(r"^(?:[A-Za-z]+_)?\.\.\.\S{1,4}$")
QUOTES = str.maketrans({"‘": "'", "’": "'", "ʼ": "'", "“": '"', "”": '"'})
TEMPLATE_VAR = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class VoiceCheckError(Exception):
    """A problem the user must fix; the message is shown as is (never contains a key or a full ID)."""


# ---------------------------------------------------------------- small helpers


def short_id(value: Any) -> str | None:
    """`conv_3h8j...9s0t` -> `conv_...9s0t`: the prefix and the last 4 characters (never the full ID)."""
    if not isinstance(value, str) or not value:
        return None
    m = re.match(r"^([A-Za-z]+_)(.+)$", value)
    prefix, rest = (m.group(1), m.group(2)) if m else ("", value)
    return f"{prefix}...{rest[-ID_SUFFIX_CHARS:]}"


def is_short_id(value: Any) -> bool:
    return isinstance(value, str) and bool(SHORT_ID.match(value))


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def iso_utc(unix_secs: float) -> str:
    return datetime.fromtimestamp(unix_secs, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise VoiceCheckError(f"cannot read {path}: {type(e).__name__}") from None
    except ValueError:
        raise VoiceCheckError(f"{path} is not valid JSON") from None


# ---------------------------------------------------------------- disclosure (rule 4)


def normalize(text: str) -> str:
    """NFC, straight quotes, case folding, collapsed whitespace: what the disclosure comparison ignores."""
    t = unicodedata.normalize("NFC", text).translate(QUOTES)
    t = unicodedata.normalize("NFC", t.casefold())
    return re.sub(r"\s+", " ", t).strip()


def disclosure_pattern(language: str, scripts: dict[str, Any] | None = None,
                       study: dict[str, Any] | None = None) -> re.Pattern[str]:
    """The approved first message for `language` as a regex over normalized text. `{study_team_name}` is the
    study's approved name in that language; any other `{variable}` (the patient's first name) matches any text."""
    scripts = scripts if scripts is not None else read_json(SCRIPTS)
    study = study if study is not None else read_json(STUDY)
    template = ((scripts.get("lines") or {}).get("first_message") or {}).get(language)
    team = (study.get("study_team_name") or {}).get(language)
    if not isinstance(template, str) or not template.strip():
        raise VoiceCheckError(f"data/scripts.json has no approved first_message for language {language!r}")
    if not isinstance(team, str) or not team.strip():
        raise VoiceCheckError(f"data/study.json has no study_team_name for language {language!r}")
    parts = TEMPLATE_VAR.split(normalize(template))  # literal, var, literal, var, ..., literal
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            out.append(re.escape(part))
        elif part == "study_team_name":
            out.append(re.escape(normalize(team)))
        else:
            out.append(r".+?")
    return re.compile("".join(out))


def first_agent_turn(transcript: list[Any]) -> dict[str, Any] | None:
    for turn in transcript:
        if isinstance(turn, dict) and turn.get("role") == "agent":
            text = turn.get("message")
            if isinstance(text, str) and text.strip():
                return turn
    return None


# ---------------------------------------------------------------- timing


def _user_turns(transcript: list[Any]) -> list[float]:
    out = []
    for turn in transcript:
        if isinstance(turn, dict) and turn.get("role") == "user":
            t, text = _seconds(turn.get("time_in_call_secs")), turn.get("message")
            if t is not None and isinstance(text, str) and text.strip():
                out.append(t)
    return out


def _result_escalated(result: Any) -> bool:
    value = result.get("result_value") if isinstance(result, dict) else None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return False
    return isinstance(value, dict) and value.get("escalated") is True


def first_escalating_tool_call(transcript: list[Any]) -> float | None:
    """Seconds from call start of the first tool call whose result says `escalated: true` (the backend's tool
    envelope, docs/03 §2), matched by request_id; a result without a matching call counts at its own turn."""
    call_times: dict[str, float] = {}
    hits: list[float] = []
    for turn in transcript:
        if not isinstance(turn, dict):
            continue
        t = _seconds(turn.get("time_in_call_secs"))
        for call in turn.get("tool_calls") or []:
            if isinstance(call, dict) and isinstance(call.get("request_id"), str) and t is not None:
                call_times.setdefault(call["request_id"], t)
        for result in turn.get("tool_results") or []:
            if not _result_escalated(result):
                continue
            at = call_times.get(result.get("request_id")) if isinstance(result.get("request_id"), str) else None
            at = at if at is not None else t
            if at is not None:
                hits.append(at)
    return min(hits) if hits else None


def trigger_turn_start(transcript: list[Any], t_page: float | None) -> tuple[float | None, str]:
    """(seconds from call start of the patient turn that triggered the page, how it was found)."""
    anchor = first_escalating_tool_call(transcript)
    basis = f"last patient turn before the first escalating tool call ({anchor:.1f} s)" if anchor is not None else ""
    if anchor is None:
        if t_page is None:
            return None, "no escalating tool result and no page time"
        anchor = t_page
        basis = f"last patient turn before the page ({t_page:.1f} s; no tool result says escalated)"
    before = [t for t in _user_turns(transcript) if t <= anchor]
    if not before:
        return None, f"no patient turn before {anchor:.1f} s"
    return max(before), basis


# ---------------------------------------------------------------- measuring one call


def pick_finding(findings: list[Any], term: str | None) -> dict[str, Any] | None:
    rows = [f for f in findings if isinstance(f, dict)]
    if term:
        rows = [f for f in rows if isinstance(f.get("term"), str) and f["term"].casefold() == term.casefold()]
        if not rows:
            return None
    graded = [f for f in rows if isinstance(f.get("provisional_grade"), int)]
    if graded:
        return max(graded, key=lambda f: f["provisional_grade"])  # first of the highest grade
    return rows[0] if term and rows else None


def measure(
    conversation: dict[str, Any],
    detail: dict[str, Any],
    *,
    term: str | None = None,
    scripts: dict[str, Any] | None = None,
    study: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """(measured fields, notes, warnings) for one call. No network, no writes."""
    notes: list[str] = []
    warnings: list[str] = []
    checkin = detail.get("checkin") or {}
    transcript = conversation.get("transcript")
    if not isinstance(transcript, list) or not transcript:
        raise VoiceCheckError("the conversation has no transcript")

    language = checkin.get("language") or str(checkin.get("agent_variant") or "").split("-")[0]
    if not language:
        raise VoiceCheckError("the check-in names no language or agent variant")
    turn = first_agent_turn(transcript)
    if turn is None:
        disclosure = False
        warnings.append("no agent turn with text: disclosure_first_turn is false")
    else:
        disclosure = bool(disclosure_pattern(language, scripts, study).search(normalize(turn["message"])))
        if turn.get("interrupted") is True:
            warnings.append("the first agent turn was interrupted: listen to the recording to confirm the "
                            "disclosure was heard in full")
        notes.append(f"disclosure: first agent turn {'contains' if disclosure else 'does NOT contain'} the "
                     f"approved {language} first message")

    meta = conversation.get("metadata") or {}
    start = _seconds(meta.get("start_time_unix_secs"))
    if start is None:
        started = ex.parse_utc(checkin.get("started_at"))
        start = started.timestamp() if started else None
        warnings.append("no start_time_unix_secs in the conversation; the check-in's started_at is the call start")

    escalations = [e for e in detail.get("escalations") or [] if isinstance(e, dict) and e.get("level") in PAGED_LEVELS]
    paged = sorted(((at, e) for e in escalations if (at := ex.parse_utc(e.get("paged_at"))) is not None),
                   key=lambda pe: pe[0])
    unpaged = [e for e in escalations if ex.parse_utc(e.get("paged_at")) is None]
    if unpaged:
        warnings.append(f"{len(unpaged)} urgent or emergency escalation(s) have no paged_at yet (page failed or "
                        "pending re-page): check the live backend log")

    row: dict[str, Any] = {
        "started_at": iso_utc(start) if start is not None else None,
        "disclosure_first_turn": disclosure,
        "paged": bool(paged),
        "page_level": None,
        "red_flag_ids": [],
        "utterance_to_page_s": None,
        "page_to_ack_s": None,
    }
    if paged:
        page_at, esc = paged[0]
        row["page_level"] = esc.get("level")
        ids: list[str] = []
        for _, e in paged:
            ids += [i for i in e.get("red_flag_ids") or [] if isinstance(i, str) and i not in ids]
        row["red_flag_ids"] = ids
        t_page = page_at.timestamp() - start if start is not None else None
        trigger, basis = trigger_turn_start(transcript, t_page)
        if t_page is None or trigger is None:
            warnings.append(f"utterance_to_page_s left null: {basis if trigger is None else 'no call start time'}")
        else:
            value = round(t_page - trigger, 1)
            if value < 0:
                warnings.append(f"utterance_to_page_s would be {value} s (clock mismatch?); left null")
            else:
                row["utterance_to_page_s"] = value
                notes.append(f"page trigger: patient turn at {trigger:.1f} s, the {basis}; page at {t_page:.1f} s")
        ack_at = ex.parse_utc(esc.get("acknowledged_at"))
        if ack_at is None:
            warnings.append("the page is not acknowledged yet: page_to_ack_s is null (rerun after the nurse "
                            "acknowledges; the row is updated in place)")
        else:
            value = round(ack_at.timestamp() - page_at.timestamp(), 1)
            if value < 0:
                warnings.append(f"page_to_ack_s would be {value} s; left null")
            else:
                row["page_to_ack_s"] = value

    finding = pick_finding(detail.get("findings") or [], term)
    if finding is None:
        warnings.append(f"no finding{f' for {term}' if term else ' with a provisional grade'}: grade and rule_id "
                        "are null")
    row["term"] = finding.get("term") if finding else (term or None)
    row["grade"] = finding.get("provisional_grade") if finding else None
    row["rule_id"] = finding.get("rule_id") if finding else None
    return row, notes, warnings


# ---------------------------------------------------------------- the file


def ordered_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row[k] for k in ROW_KEYS if k in row}
    out.update({k: v for k, v in row.items() if k not in out})
    return out


def snapshot_llm(path: Path = SNAPSHOT) -> str:
    snap = read_json(path)
    llms = sorted({v.get("llm") for v in (snap.get("variants") or {}).values() if isinstance(v, dict)} - {None})
    if len(llms) != 1:
        raise VoiceCheckError(f"agent/deployed_snapshot.json lists {len(llms)} agent LLMs ({llms}); expected one. "
                              "Run `make sync-agent` then `make sync-agent ARGS=--snapshot`")
    return llms[0]


def snapshot_suffix(variant: str, path: Path = SNAPSHOT) -> str | None:
    try:
        return ((read_json(path).get("variants") or {}).get(variant) or {}).get("agent_id_suffix")
    except VoiceCheckError:
        return None


def infer_backend(base_url: str | None) -> str | None:
    host = (urlparse(base_url).hostname or "") if base_url else ""
    if host.endswith(".onrender.com"):
        return "render-live"
    if "ngrok" in host:
        return "tunnel"
    return None


def find_target(calls: list[dict[str, Any]], scenario: str, conv_short: str | None,
                append: bool) -> tuple[int | None, dict[str, Any] | None]:
    """(index of the row to replace or None to append, the plan row whose `expected` the new row keeps)."""
    same = [(i, c) for i, c in enumerate(calls) if isinstance(c, dict) and c.get("scenario") == scenario]
    if not same:
        return None, None
    plan = same[0][1]
    for i, c in same:
        if c.get("status") != PENDING and conv_short and c.get("conversation_id") == conv_short:
            return i, plan  # the same call again: update its row
    pending = [i for i, c in same if c.get("status") == PENDING]
    if pending:
        return pending[0], plan
    if append:
        return None, plan
    logged = ", ".join(str(c.get("conversation_id")) for _, c in same)
    raise VoiceCheckError(f"scenario {scenario!r} is already logged ({logged}). A repeat call is added as an extra "
                          "row with --append; never delete a logged row to hide a failed call")


# ---------------------------------------------------------------- reading


def http_get(url: str, headers: dict[str, str], what: str) -> Any:
    try:
        import httpx
    except ImportError:
        raise VoiceCheckError("httpx is missing: run with `uv run --project backend python agent/voice_check.py`") from None
    try:
        r = httpx.get(url, headers=headers, timeout=60.0, follow_redirects=True)
    except httpx.HTTPError as e:
        raise VoiceCheckError(f"network error reading {what}: {type(e).__name__}") from None
    if r.status_code >= 400:
        hint = " (set BV_DASHBOARD_TOKEN for the live instance)" if r.status_code == 401 else ""
        raise VoiceCheckError(f"reading {what} -> HTTP {r.status_code}{hint}")
    try:
        return r.json()
    except ValueError:
        raise VoiceCheckError(f"reading {what}: response is not JSON") from None


def read_checkin(args: argparse.Namespace) -> dict[str, Any]:
    if args.checkin_file:
        return ex.read_json_file(args.checkin_file)
    return http_get(f"{ex.backend_base(args.api)}/api/checkins/{args.checkin_id}", ex.backend_headers(),
                    f"check-in {short_id(args.checkin_id)} from the live backend")


def read_conversation(args: argparse.Namespace, conversation_id: str) -> dict[str, Any]:
    if args.conversation_file:
        data = ex.read_json_file(args.conversation_file)
        return data.get("data", data) if data.get("type") == "post_call_transcription" else data
    return http_get(f"{API_BASE}/v1/convai/conversations/{conversation_id}", ex.elevenlabs_headers(),
                    f"ElevenLabs conversation {short_id(conversation_id)}")


# ---------------------------------------------------------------- main


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Log one real call in eval/results/voice_checks.json (WS1 V10).")
    p.add_argument("--checkin-id", required=True, help="backend check-in ID of the call (ci_...)")
    p.add_argument("--conversation-id", help="ElevenLabs conversation ID (conv_...; default: the check-in's)")
    p.add_argument("--scenario", required=True, help="scenario name; fills the pending row with that name")
    p.add_argument("--backend", choices=BACKENDS, help="render-live or tunnel (default: from the backend URL)")
    p.add_argument("--api", help="backend base URL (default: LIVE_API, then PUBLIC_BASE_URL)")
    p.add_argument("--red-flag-expected", choices=("yes", "no"),
                   help="only for a scenario with no planned row: whether a red flag is expected")
    p.add_argument("--append", action="store_true",
                   help="log a repeat call for an already logged scenario as an extra row")
    p.add_argument("--skip-link-check", action="store_true",
                   help="log even if nothing confirms the conversation belongs to the check-in")
    p.add_argument("--dry-run", action="store_true", help="print the row; do not write the file")
    p.add_argument("--file", type=Path, default=VOICE_CHECKS, help=argparse.SUPPRESS)
    p.add_argument("--snapshot", type=Path, default=SNAPSHOT, help=argparse.SUPPRESS)
    p.add_argument("--conversation-file", help="read the conversation from this JSON file (offline)")
    p.add_argument("--checkin-file", help="read GET /api/checkins/{id} output from this JSON file (offline)")
    return p.parse_args(argv)


def _plan_line(expected: dict[str, Any]) -> str:
    flags = ",".join(expected.get("red_flag_ids") or []) or "-"
    return (f"{expected.get('term')} grade {expected.get('grade')} {expected.get('rule_id')}, "
            f"paged {'yes' if expected.get('paged') else 'no'} [{flags}]")


def compare_with_plan(row: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Differences between a logged row and its plan (printed; the row is logged as measured either way)."""
    diffs = []
    for key in ("grade", "rule_id", "paged"):
        if key in expected and row.get(key) != expected[key]:
            diffs.append(f"{key}: planned {expected[key]!r}, measured {row.get(key)!r}")
    missing = [i for i in expected.get("red_flag_ids") or [] if i not in (row.get("red_flag_ids") or [])]
    if missing:
        diffs.append(f"red_flag_ids: planned {missing} not paged")
    return diffs


def log_call(args: argparse.Namespace) -> dict[str, Any]:
    doc = read_json(args.file)
    if not isinstance(doc, dict) or not isinstance(doc.get("calls"), list):
        raise VoiceCheckError(f"{args.file} has no `calls` list (restore it from git)")
    calls: list[dict[str, Any]] = doc["calls"]

    detail = read_checkin(args)
    checkin = detail.get("checkin") or {}
    conversation_id = args.conversation_id or checkin.get("el_conversation_id")
    if not conversation_id:
        raise VoiceCheckError("the check-in has no el_conversation_id yet; pass --conversation-id")
    conv_short = short_id(conversation_id)
    index, plan = find_target(calls, args.scenario, conv_short, args.append)

    conversation = read_conversation(args, conversation_id)
    problems = ex.check_link(conversation, checkin, conversation_id, args.checkin_id)
    if problems and not args.skip_link_check:
        raise VoiceCheckError("the conversation and the check-in do not match:\n  - " + "\n  - ".join(problems)
                              + "\n(pass --skip-link-check only if you are sure they are the same call)")

    expected = (plan or {}).get("expected") if isinstance((plan or {}).get("expected"), dict) else None
    variant = checkin.get("agent_variant")
    if plan is not None:
        if plan.get("variant") and variant != plan["variant"]:
            raise VoiceCheckError(f"scenario {args.scenario!r} is planned for {plan['variant']}, but the check-in "
                                  f"ran {variant}: wrong --scenario or wrong call")
        if expected and expected.get("patient_id") and checkin.get("patient_id") != expected["patient_id"]:
            raise VoiceCheckError(f"scenario {args.scenario!r} is planned for {expected['patient_id']}, but the "
                                  f"check-in is for {checkin.get('patient_id')}: wrong --scenario or wrong call")
        red_flag_expected = plan.get("red_flag_expected")
        if args.red_flag_expected is not None and (args.red_flag_expected == "yes") != red_flag_expected:
            raise VoiceCheckError(f"--red-flag-expected {args.red_flag_expected} contradicts the planned row")
    else:
        if args.red_flag_expected is None:
            raise VoiceCheckError(f"no planned row for scenario {args.scenario!r}: pass --red-flag-expected yes|no")
        red_flag_expected = args.red_flag_expected == "yes"

    measured, notes, warnings = measure(conversation, detail, term=(expected or {}).get("term"))
    row = ordered_row({
        "variant": variant,
        "conversation_id": conv_short,
        "checkin_id": short_id(args.checkin_id),
        "scenario": args.scenario,
        "status": LOGGED,
        "red_flag_expected": red_flag_expected,
        **measured,
        **({"expected": expected} if expected else {}),
    })

    snap_suffix = snapshot_suffix(str(variant), args.snapshot)
    agent_id = conversation.get("agent_id")
    if isinstance(agent_id, str) and snap_suffix and not agent_id.endswith(snap_suffix):
        warnings.append(f"the call ran agent ...{agent_id[-ID_SUFFIX_CHARS:]}, but agent/deployed_snapshot.json "
                        f"records ...{snap_suffix} for {variant}: run `make sync-agent ARGS=--snapshot`")
    llm = snapshot_llm(args.snapshot)
    others = [c for i, c in enumerate(calls) if i != index and isinstance(c, dict) and c.get("status") == LOGGED]
    if others and doc.get("agent_llm") not in (None, llm):
        warnings.append(f"agent_llm changes from {doc.get('agent_llm')} to {llm} while other calls are logged: "
                        "the logged calls ran different models")

    backend = args.backend or infer_backend(None if args.checkin_file else (args.api or ex.env("LIVE_API")
                                                                           or ex.env("PUBLIC_BASE_URL")))
    if backend is None:
        raise VoiceCheckError("cannot tell the backend from its URL: pass --backend render-live or --backend tunnel")
    if others and doc.get("backend") not in (None, PENDING, backend):
        raise VoiceCheckError(f"voice_checks.json records backend {doc.get('backend')!r} for the logged calls; "
                              f"this call ran on {backend!r}. Log all calls against one backend")

    if index is None:
        action = "added as a new row"
        calls.append(row)
    else:
        action = "fills its pending row" if calls[index].get("status") == PENDING else "updates its logged row"
        calls[index] = row
    starts = [c["started_at"] for c in calls if isinstance(c, dict) and c.get("status") == LOGGED
              and isinstance(c.get("started_at"), str)]
    header = {"run_at": min(starts) if starts else None, "backend": backend, "agent_llm": llm}
    out = {k: v for k, v in doc.items() if k not in ("calls", *header)}
    out = {**({"_about": out.pop("_about")} if "_about" in out else {}), **header, **out, "calls": calls}

    print(f"  {args.scenario}: {variant}, conversation {conv_short}, check-in {short_id(args.checkin_id)}: {action}")
    for n in notes:
        print(f"  {n}")
    print(f"  measured: disclosure_first_turn {row['disclosure_first_turn']}, paged {row['paged']}"
          f"{' (' + str(row['page_level']) + ' ' + ','.join(row['red_flag_ids']) + ')' if row['paged'] else ''}, "
          f"utterance_to_page_s {row['utterance_to_page_s']}, page_to_ack_s {row['page_to_ack_s']}, "
          f"{row['term']} grade {row['grade']} {row['rule_id']}")
    if expected:
        diffs = compare_with_plan(row, expected)
        print(f"  plan: {_plan_line(expected)} -> "
              + ("measured as planned" if not diffs else "DIFFERS from the plan (logged as measured): "
                 + "; ".join(diffs)))
    for p in problems:
        print(f"  warning (--skip-link-check): {p}")
    for w in warnings:
        print(f"  warning: {w}")
    if args.dry_run:
        print(json.dumps(row, ensure_ascii=False, indent=2))
        print("  dry run: nothing written")
    else:
        args.file.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        n_logged = sum(1 for c in calls if isinstance(c, dict) and c.get("status") == LOGGED)
        print(f"  wrote {args.file}: {n_logged} logged, {len(calls) - n_logged} pending or other "
              f"(backend {backend}, agent_llm {llm})")
    return row


def main(argv: list[str] | None = None) -> int:
    load_env()
    args = parse_args(argv)
    try:
        log_call(args)
    except (VoiceCheckError, ex.ExportError) as e:
        print(f"voice_check: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
