#!/usr/bin/env python3
"""Offline check: is the deployed ElevenLabs agent config (agent/deployed_snapshot.json) the one in git?

Run from the repo root (CI runs it after the agent-sync offline tests):

    python3 agent/check_config_hash.py [--snapshot PATH] [--latest PATH]

Stdlib only: no network, no API key, no .env. It renders the four variants and the five tools exactly like
`agent/sync_agent.py --dry-run` does in a clean checkout (the ELEVENLABS_LLM and ELEVENLABS_TTS_MODEL_*
overrides are ignored, so a local run gives the same answer as CI), hashes them with the normalization that
`sync_agent.py --snapshot` applies to the read-back (`sync_agent.config_fingerprint`), and checks:

  1. every variant in agent/variants.json is in the snapshot, with the same prompt_sha256, tools_sha256,
     config_sha256, llm, backup_llms and tts_model as the rendering, and an agent ID suffix of at most
     4 characters;
  2. the deployed llm equals the evaluated model (eval/results/latest.json `model.agent`), or the snapshot
     carries an `llm_note` that says why it differs (WS1 V9).

Exit 0 when everything matches; 1 otherwise, with a readable list of the differences (also when there is
no snapshot yet).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_agent as sa  # noqa: E402

NO_SNAPSHOT = "no deployed snapshot yet: run make sync-agent ARGS=--snapshot"
OVERRIDE_ENV = ("ELEVENLABS_LLM", "ELEVENLABS_TTS_MODEL_EN", "ELEVENLABS_TTS_MODEL_ES")
HASH_FIELDS = ("prompt_sha256", "tools_sha256", "config_sha256")
VALUE_FIELDS = ("llm", "backup_llms", "tts_model")
FIX = (
    "If the repo is right: make sync-agent, then make sync-agent ARGS=--snapshot, and commit "
    "agent/deployed_snapshot.json."
)


def rendered_fingerprints(sources: sa.Sources) -> dict[str, dict[str, Any]]:
    """config_fingerprint() of the --dry-run rendering of every variant, without env overrides."""
    saved = {k: os.environ.pop(k) for k in OVERRIDE_ENV if k in os.environ}
    try:
        _, tools, agents = sa.render_dry_run(sources, list(sources.variants["variants"]))
    finally:
        os.environ.update(saved)
    return {variant: sa.config_fingerprint(cfg, tools) for variant, cfg in agents.items()}


def _short(value: Any) -> str:
    if isinstance(value, str) and len(value) == 64:
        return value[:12] + "..."
    return json.dumps(value, ensure_ascii=False)


def compare(
    snapshot: dict[str, Any], rendered: dict[str, dict[str, Any]], evaluated: str | None
) -> tuple[list[str], list[str]]:
    """Returns (report rows, problems). No problems = the deployed config matches git."""
    rows: list[str] = []
    problems: list[str] = []
    deployed = snapshot.get("variants")
    if not isinstance(deployed, dict):
        return rows, ["snapshot has no `variants` object"]
    for variant in sorted(set(deployed) - set(rendered)):
        problems.append(f"{variant}: in the snapshot but not in agent/variants.json")
    rows.append(f"  {'variant':<14} {'agent':<8} {'llm':<20} prompt  tools   config")
    for variant, want in rendered.items():
        got = deployed.get(variant)
        if not isinstance(got, dict):
            problems.append(f"{variant}: missing from the snapshot")
            rows.append(f"  {variant:<14} {'-':<8} {'-':<20} -       -       -")
            continue
        suffix = str(got.get("agent_id_suffix", ""))
        if not suffix or len(suffix) > sa.AGENT_ID_SUFFIX_CHARS:
            problems.append(
                f"{variant}: agent_id_suffix must be the last {sa.AGENT_ID_SUFFIX_CHARS} characters only"
            )
            suffix = "?"
        status = []
        for field in HASH_FIELDS:
            same = got.get(field) == want[field]
            status.append("ok" if same else "DIFF")
            if not same:
                problems.append(
                    f"{variant}: {field} differs: rendered {_short(want[field])}, "
                    f"deployed {_short(got.get(field))}"
                )
        for field in VALUE_FIELDS:
            if got.get(field) != want[field]:
                problems.append(
                    f"{variant}: {field} differs: rendered {_short(want[field])}, "
                    f"deployed {_short(got.get(field))}"
                )
        rows.append(
            f"  {variant:<14} ...{suffix:<5} {str(got.get('llm')):<20} {status[0]:<7} {status[1]:<7} {status[2]}"
        )
    problems += llm_problems(snapshot, evaluated)
    return rows, problems


def llm_problems(snapshot: dict[str, Any], evaluated: str | None) -> list[str]:
    """The deployed llm must be the evaluated model unless an llm_note explains the difference."""
    variants = snapshot.get("variants") if isinstance(snapshot.get("variants"), dict) else {}
    out = []
    for variant, entry in variants.items():
        entry = entry if isinstance(entry, dict) else {}
        llm = entry.get("llm")
        if evaluated and llm == evaluated:
            continue
        if snapshot.get("llm_note") or entry.get("llm_note"):
            continue
        if not evaluated:
            out.append(
                f"{variant}: no evaluated model in eval/results/latest.json (model.agent) to compare the "
                f"deployed llm {llm!r} with, and no llm_note"
            )
        else:
            out.append(
                f"{variant}: deployed llm {llm!r} is not the evaluated model {evaluated!r} "
                "(eval/results/latest.json model.agent) and the snapshot has no llm_note"
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument(
        "--snapshot", type=Path, default=sa.SNAPSHOT_PATH, help="default: agent/deployed_snapshot.json"
    )
    parser.add_argument(
        "--latest", type=Path, default=sa.LATEST_EVAL_PATH, help="default: eval/results/latest.json"
    )
    args = parser.parse_args(argv)

    if not args.snapshot.exists():
        print(NO_SNAPSHOT)
        return 1
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise ValueError("not a JSON object")
    except ValueError as e:
        print(f"FAIL: {args.snapshot.name} is not a valid snapshot ({e}). {FIX}")
        return 1
    ignored = [k for k in OVERRIDE_ENV if os.environ.get(k)]
    try:
        rendered = rendered_fingerprints(sa.Sources())
    except sa.SyncError as e:
        print(f"FAIL: cannot render the agent config: {e}")
        return 1
    evaluated = sa.evaluated_agent_llm(args.latest)
    rows, problems = compare(snapshot, rendered, evaluated)

    print(f"Deployed agent config vs git ({args.snapshot.name}, captured {snapshot.get('captured_at', '?')})")
    if ignored:
        print(f"  note: ignoring {', '.join(ignored)} from the environment (the check uses the committed config)")
    print("\n".join(rows))
    entries = snapshot.get("variants") if isinstance(snapshot.get("variants"), dict) else {}
    deployed_llms = sorted({str(e.get("llm")) for e in entries.values() if isinstance(e, dict)})
    print(f"  evaluated model (latest.json model.agent): {evaluated}; deployed: {', '.join(deployed_llms) or '-'}")
    if snapshot.get("llm_note"):
        print(f"  llm_note: {snapshot['llm_note']}")
    if problems:
        print(f"\nFAIL: {len(problems)} difference(s) between the deployed agents and the repo:")
        for p in problems:
            print(f"  - {p}")
        print(FIX)
        return 1
    print(f"\nOK: the deployed config of all {len(rendered)} variants matches the repo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
