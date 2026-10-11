"""B15: replay speed, scenario provenance, health.site_signal and the voice-checks route (docs/03 §6.2, §6.7, §6.11)."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import select

from app.config import DEFAULT_MONITORING_OUT, ROOT, SCENARIOS_DIR, Settings, get_settings
from app.models import CheckIn, DraftEntry
from app.routers import api
from app.services import replay
from tests.conftest import COORD

ROSA = "rosa_es_urgent"
ROSA_DURATION_S = max(e.get("t", 0) for e in json.loads((SCENARIOS_DIR / f"{ROSA}.json").read_text(encoding="utf-8"))["events"])
SCENARIO_KEYS = {"id", "title", "duration_s", "patient_id", "recorded", "recorded_at", "label", "audio_url"}
UNAVAILABLE = {"available": False, "sap_tag_commit": None, "generated_at": None, "data_origin": "SIMULATED"}
ROLES = ["coordinator", "investigator", "sponsor", "cra"]


class InlineThread:
    """Stands in for threading.Thread inside app.services.replay only: runs the replay in the request."""

    def __init__(self, target, args=(), **_):  # noqa: ANN001
        self.target, self.args = target, args

    def start(self) -> None:
        self.target(*self.args)


class FakeClock:
    """Virtual time for app.services.replay: sleep() advances monotonic(), so a replay takes no wall time."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def setenv(monkeypatch):
    """Set (or, with None, remove) environment variables and rebuild Settings; restored after the test."""

    def _set(**values: str | None) -> None:
        for key, value in values.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


@pytest.fixture
def captured_speeds(monkeypatch) -> list[float]:
    """Record the multiplier each replay starts with, without playing it."""
    speeds: list[float] = []
    monkeypatch.setattr(replay, "_run", lambda checkin_id, sc, speed: speeds.append(speed))
    monkeypatch.setattr(replay, "threading", SimpleNamespace(Thread=InlineThread))
    return speeds


@pytest.fixture
def virtual_clock(monkeypatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(replay, "time", clock)
    monkeypatch.setattr(replay, "threading", SimpleNamespace(Thread=InlineThread))
    return clock


def replay_checkins(session) -> int:
    return len(session.exec(select(CheckIn.id).where(CheckIn.channel == "replay")).all())


# ---- replay speed (docs/03 §6.2) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("requested", "env", "demo", "expected"),
    [
        (4, "1", True, 4.0),  # the ?speed= value wins over REPLAY_SPEED
        (1, "4", True, 1.0),
        (None, "4", True, 4.0),  # then REPLAY_SPEED
        (None, "4", False, 4.0),
        (None, "", True, 2.0),  # then 2 in demo mode
        (None, "", False, 1.0),  # direct service calls outside demo mode play in real time
        (None, "abc", True, 2.0),  # an invalid REPLAY_SPEED is ignored, never fatal
        (None, "0", True, 2.0),
        (None, "-2", True, 2.0),
        (None, "nan", True, 2.0),
    ],
)
def test_speed_precedence(setenv, requested, env, demo, expected) -> None:
    setenv(REPLAY_SPEED=env, DEMO_MODE="1" if demo else "0")
    assert replay.resolve_speed(requested) == expected


@pytest.mark.parametrize(
    ("query", "env", "expected"),
    [("?speed=1", "4", 1.0), ("?speed=2", "", 2.0), ("?speed=4", "", 4.0), ("", "4", 4.0), ("", "", 2.0)],
)
def test_replay_route_speed(demo_mode, setenv, client, captured_speeds, query, env, expected) -> None:
    setenv(REPLAY_SPEED=env)
    r = client.post(f"/api/demo/replay/{ROSA}{query}")
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"checkin_id"} and r.json()["checkin_id"].startswith("ci_")
    assert captured_speeds == [expected]


@pytest.mark.parametrize("value", ["3", "0", "-1", "0.5", "8", "abc", "", "true"])
def test_replay_rejects_other_speeds(demo_mode, client, session, captured_speeds, value) -> None:
    before = replay_checkins(session)
    r = client.post(f"/api/demo/replay/{ROSA}", params={"speed": value})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert captured_speeds == [] and replay_checkins(session) == before  # nothing started


@pytest.mark.req("REQ-017")
@pytest.mark.parametrize("value", ["4", "3"])
def test_replay_speed_is_demo_only(client, captured_speeds, value) -> None:
    """Outside demo mode the route stays hidden: 404 demo_disabled, checked before the speed is validated."""
    r = client.post(f"/api/demo/replay/{ROSA}", params={"speed": value})
    assert r.status_code == 404 and r.json()["error"]["code"] == "demo_disabled"
    assert captured_speeds == []


@pytest.mark.req("REQ-015")
def test_replay_at_4x_takes_a_quarter_of_real_time(demo_mode, client, session, virtual_clock, fake_pager) -> None:
    """The full Rosa story through the real handlers: 4x ends at a quarter of the 1x time, drafts ready."""
    elapsed: dict[int, float] = {}
    for speed in (4, 1):
        virtual_clock.now = 0.0
        r = client.post(f"/api/demo/replay/{ROSA}", params={"speed": speed})
        assert r.status_code == 200, r.text
        cid = r.json()["checkin_id"]
        elapsed[speed] = virtual_clock.now
        detail = client.get(f"/api/checkins/{cid}").json()
        assert detail["checkin"]["status"] == "completed"
        kinds = sorted(d["kind"] for d in client.get("/api/drafts", params={"checkin_id": cid}).json())
        assert kinds == ["AE", "AE", "CM"]
    assert elapsed[1] == pytest.approx(ROSA_DURATION_S)
    assert elapsed[4] == pytest.approx(ROSA_DURATION_S / 4)
    assert elapsed[4] <= 45  # drafts appear within about 45 s at 4x
    assert len(session.exec(select(DraftEntry)).all()) >= 6
    assert len(fake_pager.sent) == 2  # one urgent page per replay


# ---- scenario provenance (docs/03 §6.2) ----------------------------------------------------------------------


def test_scenarios_carry_provenance(demo_mode, client) -> None:
    r = client.get("/api/demo/scenarios")
    assert r.status_code == 200
    items = r.json()
    assert items and all(set(it) == SCENARIO_KEYS for it in items)
    rosa = next(it for it in items if it["id"] == ROSA)
    has_audio = (SCENARIOS_DIR / "audio" / f"{ROSA}.mp3").is_file()  # gitignored; present only on a demo laptop
    assert rosa["recorded"] is False and rosa["recorded_at"] is None and rosa["label"] == "Scripted"
    assert rosa["audio_url"] == (f"/api/demo/scenarios/{ROSA}/audio" if has_audio else None)
    assert rosa["duration_s"] == ROSA_DURATION_S and rosa["patient_id"] == "pat_rosa"


def _scenario(sid: str, **extra: object) -> dict:
    return {"id": sid, "title": sid, "patient_id": "pat_rosa", "day_after_dose": 3,
            "events": [{"t": 0.0, "type": "call_started"}, {"t": 12.0, "type": "call_ended"}], **extra}


def test_recorded_scenarios_and_audio_url(demo_mode, client, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(replay, "SCENARIOS_DIR", tmp_path)
    files = {
        "rec_en_g2": _scenario("rec_en_g2", recorded=True, recorded_at="2026-10-11", label="Recorded real call (custom)"),
        "rec_es_flag": _scenario("rec_es_flag", recorded=True, recorded_at="not a date"),
        "scripted_claim": _scenario("scripted_claim", recorded=False, recorded_at="2026-10-11",
                                    label="Recorded real call; synthetic patient played by a teammate"),
        "scripted_plain": _scenario("scripted_plain"),
    }
    for name, doc in files.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
    (tmp_path / "not_a_scenario.json").write_text(json.dumps({"id": "x"}), encoding="utf-8")
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "rec_en_g2.mp3").write_bytes(b"ID3")
    (tmp_path / "audio" / "scripted_plain.mp3").write_bytes(b"ID3")

    items = {it["id"]: it for it in client.get("/api/demo/scenarios").json()}
    assert set(items) == set(files)
    assert items["rec_en_g2"] == {
        "id": "rec_en_g2", "title": "rec_en_g2", "duration_s": 12.0, "patient_id": "pat_rosa", "recorded": True,
        "recorded_at": "2026-10-11", "label": "Recorded real call (custom)",
        "audio_url": "/api/demo/scenarios/rec_en_g2/audio",
    }
    flag = items["rec_es_flag"]
    assert flag["recorded"] is True and flag["recorded_at"] is None and flag["audio_url"] is None
    assert flag["label"] == replay.RECORDED_LABEL == "Recorded real call; synthetic patient played by a teammate"
    claim = items["scripted_claim"]  # never presented as a real call unless marked recorded
    assert claim["recorded"] is False and claim["label"] == "Scripted" and claim["recorded_at"] is None
    assert items["scripted_plain"]["label"] == "Scripted"
    assert items["scripted_plain"]["audio_url"] == "/api/demo/scenarios/scripted_plain/audio"


@pytest.mark.parametrize("sid", ["../rosa_es_urgent", "a/b", "rosa es", ""])
def test_audio_path_rejects_non_slug_ids(sid: str) -> None:
    assert replay.audio_path(sid) is None and replay.audio_url(sid) is None


# ---- health.site_signal (docs/03 §6.7) -----------------------------------------------------------------------


def _signal_run(**run: object) -> dict:
    return {"_about": "test shape, not a result", "run": {"id": "sr_committed", "data_origin": "SIMULATED", **run},
            "sites": [], "rows": [], "funnel": {}}


def test_health_site_signal_unavailable_without_outputs(setenv, client, tmp_path: Path) -> None:
    setenv(MONITORING_OUT=str(tmp_path / "missing"))
    body = client.get("/api/health").json()
    assert body["site_signal"] == UNAVAILABLE
    setenv(MONITORING_OUT=str(tmp_path))  # the directory exists but holds no signal_run.json
    assert client.get("/api/health").json()["site_signal"] == UNAVAILABLE


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "",
        "[]",
        json.dumps({"run": {"sap_tag_commit": "1a2b3c4"}}),  # no sites/rows
        json.dumps({"run": [], "sites": [], "rows": []}),
        json.dumps(_signal_run(sap_tag_commit=1234567, generated_at="2026-10-11T08:40:00Z")),
    ],
    ids=["not-json", "empty", "list", "no-sites-rows", "run-not-object", "commit-not-string"],
)
def test_health_site_signal_unavailable_when_run_does_not_load(setenv, client, tmp_path: Path, content: str) -> None:
    (tmp_path / "signal_run.json").write_text(content, encoding="utf-8")
    setenv(MONITORING_OUT=str(tmp_path))
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["site_signal"] == UNAVAILABLE


def test_health_site_signal_available_when_run_loads(setenv, client, tmp_path: Path) -> None:
    path = tmp_path / "signal_run.json"
    path.write_text(json.dumps(_signal_run(sap_tag_commit="1a2b3c4", generated_at="2026-10-11T08:40:00Z")), "utf-8")
    setenv(MONITORING_OUT=str(tmp_path))
    assert client.get("/api/health").json()["site_signal"] == {
        "available": True, "sap_tag_commit": "1a2b3c4", "generated_at": "2026-10-11T08:40:00Z",
        "data_origin": "SIMULATED"}

    path.write_text("{truncated", encoding="utf-8")  # a rewrite is picked up (mtime/size cache)
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000_000))
    assert client.get("/api/health").json()["site_signal"] == UNAVAILABLE

    path.unlink()
    assert client.get("/api/health").json()["site_signal"] == UNAVAILABLE


def test_health_site_signal_nulls_pass_through(setenv, client, tmp_path: Path) -> None:
    (tmp_path / "signal_run.json").write_text(json.dumps(_signal_run()), encoding="utf-8")
    setenv(MONITORING_OUT=str(tmp_path))
    assert client.get("/api/health").json()["site_signal"] == {
        "available": True, "sap_tag_commit": None, "generated_at": None, "data_origin": "SIMULATED"}


def test_monitoring_out_setting(monkeypatch, tmp_path: Path) -> None:
    """MONITORING_OUT (docs/03 §6.9): default <repo>/monitoring/out; relative paths are from the repo root."""
    monkeypatch.delenv("MONITORING_OUT", raising=False)
    assert Settings(_env_file=None).monitoring_out == DEFAULT_MONITORING_OUT == ROOT / "monitoring" / "out"
    assert Settings(_env_file=None, monitoring_out="").monitoring_out == DEFAULT_MONITORING_OUT
    rel = "backend/tests/fixtures/site_signal"
    assert Settings(_env_file=None, monitoring_out=rel).monitoring_out == ROOT / rel
    assert Settings(_env_file=None, monitoring_out=str(tmp_path)).monitoring_out == tmp_path
    monkeypatch.setenv("MONITORING_OUT", rel)
    assert Settings(_env_file=None).monitoring_out == ROOT / rel


# ---- GET /api/eval/voice-checks (docs/03 §6.11) ----------------------------------------------------------------


VOICE_CHECKS = {
    "run_at": "2026-10-11T07:05:00Z", "backend": "render-live", "agent_llm": "test-model",
    "calls": [{"variant": "es-extra_time", "conversation_id": "conv_x1y2", "checkin_id": "ci_TEST", "scenario": "rosa_g3",
               "disclosure_first_turn": True, "red_flag_expected": True, "paged": True, "utterance_to_page_s": None,
               "page_to_ack_s": None, "grade": 3, "rule_id": "CTCAE5_DIARRHEA_G3", "note": "kept as written"}],
    "_about": "test shape, not a result",
}


@pytest.mark.parametrize("role", ROLES)
def test_voice_checks_404_when_absent(client, monkeypatch, tmp_path: Path, role: str) -> None:
    monkeypatch.setattr(api, "ROOT", tmp_path)
    r = client.get("/api/eval/voice-checks", headers={**COORD, "X-BV-Role": role})
    assert r.status_code == 404 and r.json()["error"]["code"] == "no_voice_checks"


@pytest.mark.parametrize("role", ROLES)
def test_voice_checks_served_as_measured(client, monkeypatch, tmp_path: Path, role: str) -> None:
    (tmp_path / "eval" / "results").mkdir(parents=True)
    (tmp_path / "eval" / "results" / "voice_checks.json").write_text(json.dumps(VOICE_CHECKS), encoding="utf-8")
    monkeypatch.setattr(api, "ROOT", tmp_path)
    r = client.get("/api/eval/voice-checks", headers={**COORD, "X-BV-Role": role})
    assert r.status_code == 200
    assert r.json() == {**VOICE_CHECKS, "data_origin": "MEASURED"}  # the file as written, plus the label


def test_voice_checks_label_is_always_measured(client, monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "eval" / "results").mkdir(parents=True)
    doc = {"run_at": "2026-10-11T07:05:00Z", "data_origin": "SIMULATED", "calls": [{"variant": "en-standard"}]}
    (tmp_path / "eval" / "results" / "voice_checks.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(api, "ROOT", tmp_path)
    assert client.get("/api/eval/voice-checks").json() == {**doc, "data_origin": "MEASURED"}


# ---- /openapi.json carries the new shapes ------------------------------------------------------------------------


def test_openapi_documents_b15(client) -> None:
    spec = client.get("/openapi.json").json()
    params = spec["paths"]["/api/demo/replay/{scenario_id}"]["post"]["parameters"]
    speed = next(p for p in params if p["name"] == "speed")
    assert speed["in"] == "query" and not speed.get("required", False)
    assert spec["components"]["schemas"]["ReplaySpeed"]["enum"] == [1, 2, 4]
    scenario = spec["components"]["schemas"]["ScenarioOut"]
    assert {"recorded", "recorded_at", "label", "audio_url"} <= set(scenario["required"])
    health = spec["components"]["schemas"]["Health"]
    assert "site_signal" in health["required"]
    site_signal = spec["components"]["schemas"]["SiteSignalHealth"]
    assert set(site_signal["required"]) == {"available", "sap_tag_commit", "generated_at", "data_origin"}
    assert "/api/eval/voice-checks" in spec["paths"]
