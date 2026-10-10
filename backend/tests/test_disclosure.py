"""REQ-001 / REQ-002: every first turn (outbound, inbound, both languages) discloses the AI and offers a person."""

import json
import subprocess
import sys

import pytest

from app import content
from app.config import ROOT

DISCLOSE = {"en": ["automated", "AI assistant", "not a person"], "es": ["automática", "inteligencia artificial", "no una persona"]}
OFFER = {"en": "speak with a person at any time", "es": "hablar con una persona en cualquier momento"}
VARS = {"study_team_name": "T", "patient_first_name": "P"}


@pytest.mark.req("REQ-001")
@pytest.mark.req("REQ-002")
@pytest.mark.parametrize("key", ["first_message", "first_message_inbound"])
@pytest.mark.parametrize("lang", ["en", "es"])
def test_first_turn_scripts(key, lang):
    text = content.script(key, lang, **VARS)
    for phrase in DISCLOSE[lang]:
        assert phrase.lower() in text.lower()
    assert OFFER[lang] in text
    # disclosure comes before anything else is asked
    assert text.find(DISCLOSE[lang][1]) < text.find("?")


@pytest.mark.req("REQ-001")
@pytest.mark.req("REQ-002")
def test_agent_variants_use_the_disclosure_first_message():
    """The ElevenLabs agents' first message is generated from data/scripts.json (dry-run, no network)."""
    out = subprocess.run(
        [sys.executable, str(ROOT / "agent" / "sync_agent.py"), "--dry-run"],
        capture_output=True, text=True, cwd=ROOT, env={"PUBLIC_BASE_URL": "https://example.test", "PATH": ""}, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    for lang in ("en", "es"):
        expected = content.script("first_message", lang, study_team_name="{{study_team_name}}",
                                  patient_first_name="{{patient_first_name}}")
        assert json.dumps(expected, ensure_ascii=False)[1:-1] in out.stdout or expected in out.stdout
