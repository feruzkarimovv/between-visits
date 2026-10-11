"""R6: the variant → agent_id map comes from agent/agents.lock.json, else from AGENTS_LOCK_JSON (docs/03 §6.9).

Cloud images never contain the gitignored lock file (.dockerignore), so the live host gets the same JSON as an
environment variable. A bad value means "not synced": calls stay off with a reason, and the value is never logged.
"""

import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.services import elevenlabs

VARIANTS = ("en-standard", "en-extra_time", "es-standard", "es-extra_time")
LOCK = {v: f"agent_test_{v}" for v in VARIANTS}  # fake IDs


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[pytest.MonkeyPatch]:
    """No lock file (as in a container image) and AGENTS_LOCK_JSON / ELEVENLABS_API_KEY restored afterwards."""
    monkeypatch.setattr(elevenlabs, "AGENTS_LOCK_PATH", tmp_path / "agents.lock.json")
    saved = {k: os.environ.get(k) for k in ("AGENTS_LOCK_JSON", "ELEVENLABS_API_KEY")}
    yield monkeypatch
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    get_settings.cache_clear()


def set_env(**values: str) -> None:
    os.environ.update(values)
    get_settings.cache_clear()


def test_env_json_is_used_when_the_lock_file_is_absent(env: pytest.MonkeyPatch) -> None:
    assert elevenlabs.load_lock() == {}  # neither source: not synced
    set_env(AGENTS_LOCK_JSON=json.dumps(LOCK))
    assert elevenlabs.load_lock() == LOCK
    assert elevenlabs.agent_id_for("es-extra_time") == "agent_test_es-extra_time"


def test_lock_file_wins_over_env(env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from_file = {"en-standard": "agent_from_file"}
    (tmp_path / "agents.lock.json").write_text(json.dumps(from_file), encoding="utf-8")
    set_env(AGENTS_LOCK_JSON=json.dumps(LOCK))
    assert elevenlabs.load_lock() == from_file


def test_readiness_uses_env_json(env: pytest.MonkeyPatch) -> None:
    set_env(ELEVENLABS_API_KEY="el-test-key", AGENTS_LOCK_JSON="")
    assert "AGENTS_LOCK_JSON" in (elevenlabs.readiness()["web"] or "")
    set_env(AGENTS_LOCK_JSON=json.dumps(LOCK))
    assert elevenlabs.readiness()["web"] is None  # browser calls ready on a cloud host without the lock file


@pytest.mark.parametrize(
    "raw",
    ["{not json agent_secretish", '["agent_secretish"]', '"agent_secretish"', "   "],
    ids=["not-json", "list", "string", "blank"],
)
def test_bad_env_json_means_not_synced_and_is_never_logged(env: pytest.MonkeyPatch, raw: str,
                                                           caplog: pytest.LogCaptureFixture) -> None:
    set_env(AGENTS_LOCK_JSON=raw)
    with caplog.at_level(logging.DEBUG):
        assert elevenlabs.load_lock() == {}
        with pytest.raises(elevenlabs.TelephonyUnavailable):
            elevenlabs.agent_id_for("en-standard")
    assert "agent_secretish" not in caplog.text


def test_non_string_ids_are_dropped(env: pytest.MonkeyPatch) -> None:
    set_env(AGENTS_LOCK_JSON=json.dumps({"en-standard": "agent_ok", "es-standard": "", "en-extra_time": 5}))
    assert elevenlabs.load_lock() == {"en-standard": "agent_ok"}
