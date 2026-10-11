#!/usr/bin/env python3
"""Synthesize the voices of a SCRIPTED replay scenario and re-time it to the audio.

Run from the repo root:

    uv run --project backend python agent/synthesize_scenario.py                  # every scripted scenario below
    uv run --project backend python agent/synthesize_scenario.py rosa_es_urgent   # one scenario
    uv run --project backend python agent/synthesize_scenario.py --dry-run        # characters only, no API calls

For each turn of the scenario transcript (`post_call.transcript`) it asks ElevenLabs text-to-speech for one clip:
the agent's own voice for the patient's language (ELEVENLABS_VOICE_ID_EN / _ES, the voices the live agents use) at
the agent's speed for the patient's pace (agent/variants.json `pace_settings.*.tts_speed`), and a separate voice per
synthetic patient (PATIENT_VOICES). The clips are joined with short pauses into `scenarios/audio/<id>.mp3`, and the
scenario's times are rewritten so the replay matches the audio:
  * every transcript turn starts where its clip starts;
  * a tool call after a patient turn fires 0.3 s after the patient stops speaking;
  * any other event (page acknowledgment) keeps its offset from the turn it follows;
  * call_ended is 0.3 s after the last clip, post_call 2 s later.

Only scripted scenarios (no `recorded: true`) are synthesized: these voices are not real people, so the mp3 is
committed (.gitignore and .dockerignore list each file) and served by the public demo. Recorded calls never are.
Clips are cached in scenarios/audio/.tts-cache/ (gitignored) by voice, model, speed and text, so re-running after a
wording change only pays for the changed turns. Needs ELEVENLABS_API_KEY and ffmpeg.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_agent import API_BASE, load_env  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = ROOT / "scenarios"
AUDIO_DIR = SCENARIOS_DIR / "audio"
CACHE_DIR = AUDIO_DIR / ".tts-cache"
PATIENTS_PATH = ROOT / "data" / "patients.json"
VARIANTS_PATH = ROOT / "agent" / "variants.json"

MODEL_ID = "eleven_multilingual_v2"  # one model for both languages; offline, so latency does not matter
SAMPLE_RATE = 24_000  # pcm_24000: 16-bit little-endian mono
MP3_BITRATE = "64k"
LOUDNORM = "loudnorm=I=-18:TP=-1.5:LRA=7"  # evens out the agent and patient voices
AGENT_VOICE_ENV = {"en": "ELEVENLABS_VOICE_ID_EN", "es": "ELEVENLABS_VOICE_ID_ES"}
AGENT_SETTINGS = {"stability": 0.6, "similarity_boost": 0.8}  # = agent/agent.template.json tts
PATIENT_SETTINGS = {"stability": 0.45, "similarity_boost": 0.8}

# Synthetic patients' voices (ElevenLabs voice library, added to the team account) and how they talk.
# speed: TTS speed (0.7-1.2); think_s: pause before they answer.
PATIENT_VOICES: dict[str, dict[str, Any]] = {
    "pat_rosa": {"voice_id": "CaJslL1xziwefCeTNzHv", "speed": 0.9, "think_s": 1.4},  # Cristina, Latin American
    "pat_walter": {"voice_id": "pqHfZKP75CvOlQylNhV4", "speed": 0.85, "think_s": 1.6},  # Bill, older American
    "pat_ana": {"voice_id": "b2htR0pMe28pYwCY9gnP", "speed": 1.05, "think_s": 0.6},  # Sofia, Colombian
}
# Pause before the agent speaks: the extra-time agents wait longer (agent/variants.json turn settings).
AGENT_PAUSE_S = {"standard": 0.6, "extra_time": 1.1}

TOOL_AFTER_SPEECH_S = 0.3
CALL_END_AFTER_AUDIO_S = 0.3
POST_CALL_AFTER_END_S = 2.0


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"{name} is not set (.env or environment)")
    return value


def patients() -> dict[str, dict[str, Any]]:
    data = json.loads(PATIENTS_PATH.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data["patients"]
    return {p["id"]: p for p in rows}


def agent_speed(pace: str) -> float:
    return float(json.loads(VARIANTS_PATH.read_text(encoding="utf-8"))["pace_settings"][pace]["tts_speed"])


def scripted_ids() -> list[str]:
    out = []
    for p in sorted(SCENARIOS_DIR.glob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and "events" in doc and doc.get("recorded") is not True and doc.get("patient_id") in PATIENT_VOICES:
            out.append(doc.get("id", p.stem))
    return out


def post_call(doc: dict[str, Any]) -> dict[str, Any]:
    pcs = [e for e in doc["events"] if e.get("type") == "post_call"]
    if len(pcs) != 1 or not pcs[0].get("transcript"):
        sys.exit(f"{doc['id']}: needs exactly one post_call event with a transcript")
    return pcs[0]


def tts(voice_id: str, text: str, speed: float, settings: dict[str, float], *, force: bool) -> bytes:
    """One clip as raw PCM (cached by request)."""
    payload = {"text": text, "model_id": MODEL_ID, "voice_settings": {**settings, "speed": speed}}
    key = hashlib.sha256(json.dumps([voice_id, SAMPLE_RATE, payload], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    path = CACHE_DIR / f"{key}.pcm"
    if path.is_file() and not force:
        return path.read_bytes()
    import httpx

    r = httpx.post(f"{API_BASE}/v1/text-to-speech/{voice_id}", params={"output_format": f"pcm_{SAMPLE_RATE}"},
                   headers={"xi-api-key": env("ELEVENLABS_API_KEY")}, json=payload, timeout=120)
    if r.status_code != 200:
        sys.exit(f"text-to-speech failed ({r.status_code}): {r.text[:300]}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return r.content


def silence(seconds: float) -> bytes:
    return b"\x00\x00" * round(seconds * SAMPLE_RATE)


def retime(doc: dict[str, Any], starts: list[float], ends: list[float]) -> None:
    """Rewrite event and transcript times to the new turn starts/ends (see module docstring)."""
    pc = post_call(doc)
    turns = pc["transcript"]
    old = [float(t["t_s"]) for t in turns]
    last = 0.0
    for ev in sorted(doc["events"], key=lambda e: e.get("t", 0)):
        kind = ev.get("type")
        if kind == "call_started":
            ev["t"] = 0.0
            continue
        if kind in ("call_ended", "post_call"):
            continue
        anchor = max((i for i, t in enumerate(old) if t <= ev["t"]), default=0)
        if kind == "tool" and turns[anchor]["role"] == "user":
            t = ends[anchor] + TOOL_AFTER_SPEECH_S
        else:
            t = starts[anchor] + (ev["t"] - old[anchor])
        if anchor + 1 < len(starts):  # stay before the next turn, so a re-run anchors the same way
            t = min(t, starts[anchor + 1] - 0.1)
        last = ev["t"] = round(max(t, last), 1)
    for turn, start in zip(turns, starts, strict=True):
        turn["t_s"] = round(start, 1)
    call_end = round(max(ends[-1] + CALL_END_AFTER_AUDIO_S, last), 1)
    for ev in doc["events"]:
        if ev.get("type") == "call_ended":
            ev["t"] = call_end
    pc["t"] = round(call_end + POST_CALL_AFTER_END_S, 1)
    doc["events"].sort(key=lambda e: e.get("t", 0))


def synthesize(scenario_id: str, *, dry_run: bool, force: bool) -> None:
    path = SCENARIOS_DIR / f"{scenario_id}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("recorded") is True:
        sys.exit(f"{scenario_id}: recorded scenarios are never synthesized")
    patient = patients()[doc["patient_id"]]
    voice = PATIENT_VOICES[doc["patient_id"]]
    lang, pace = patient["language"], patient["pace"]
    turns = post_call(doc)["transcript"]
    chars = sum(len(t["text"]) for t in turns)
    if dry_run:
        print(f"{scenario_id}: {len(turns)} turns, {chars} characters ({lang}, {pace})")
        return

    agent_voice, a_speed = env(AGENT_VOICE_ENV[lang]), agent_speed(pace)
    pcm, starts, ends = bytearray(), [], []
    for i, turn in enumerate(turns):
        if i:
            pcm += silence(voice["think_s"] if turn["role"] == "user" else AGENT_PAUSE_S[pace])
        if turn["role"] == "agent":
            clip = tts(agent_voice, turn["text"], a_speed, AGENT_SETTINGS, force=force)
        else:
            clip = tts(voice["voice_id"], turn["text"], voice["speed"], PATIENT_SETTINGS, force=force)
        starts.append(len(pcm) / 2 / SAMPLE_RATE)
        pcm += clip
        ends.append(len(pcm) / 2 / SAMPLE_RATE)
    pcm += silence(0.5)

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out = AUDIO_DIR / f"{scenario_id}.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "-i", "pipe:0",
                    "-af", LOUDNORM, "-ar", str(SAMPLE_RATE), "-codec:a", "libmp3lame", "-b:a", MP3_BITRATE, str(out)], input=bytes(pcm), check=True)
    retime(doc, starts, ends)
    doc["audio"] = f"scenarios/audio/{scenario_id}.mp3"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{scenario_id}: {len(turns)} turns, {chars} characters, {ends[-1]:.1f} s of audio -> {out.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("ids", nargs="*", help="scenario IDs (default: every scripted scenario with a patient voice)")
    p.add_argument("--dry-run", action="store_true", help="print turns and characters only; no API calls")
    p.add_argument("--force", action="store_true", help="ignore the clip cache")
    args = p.parse_args(argv)
    load_env()
    for sid in args.ids or scripted_ids():
        synthesize(sid, dry_run=args.dry_run, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
