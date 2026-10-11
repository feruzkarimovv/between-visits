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


SPANISH_TEAM_SCRIPTS = ["first_message", "first_message_inbound", "first_message_inbound_unknown", "voicemail"]


@pytest.mark.req("REQ-001")
@pytest.mark.parametrize("key", SPANISH_TEAM_SCRIPTS)
def test_spanish_first_turn_says_del_equipo(key):
    """D8: the Spanish templates say `del {study_team_name}` and study_team_name.es has no leading article,
    so the first turn reads "del equipo", never "de el equipo"."""
    assert "{study_team_name}" in content.scripts_doc()["lines"][key]["es"]
    team = content.study_doc()["study_team_name"]["es"]
    text = content.script(key, "es", study_team_name=team, patient_first_name="Rosa")
    assert "del equipo" in text
    assert "de el " not in text and "del el " not in text


def test_rosa_replay_first_message_is_the_current_script():
    """The recorded Rosa replay and its post-call fixture carry the first message rendered from data/."""
    expected = content.script("first_message", "es", study_team_name=content.study_doc()["study_team_name"]["es"],
                              patient_first_name="Rosa")
    sc = json.loads((ROOT / "scenarios" / "rosa_es_urgent.json").read_text(encoding="utf-8"))
    post_call = next(e for e in sc["events"] if e["type"] == "post_call")
    assert post_call["transcript"][0]["text"] == expected
    fx = json.loads((ROOT / "scenarios" / "fixtures" / "post_call_rosa.json").read_text(encoding="utf-8"))
    assert fx["data"]["transcript"][0]["message"] == expected


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
