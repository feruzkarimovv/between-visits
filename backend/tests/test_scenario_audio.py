"""WS1 V11: the scenario audio route (docs/03 §6.2) and replay fidelity of an exported recorded scenario."""

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from sqlmodel import select

from app.config import ROOT, SCENARIOS_DIR
from app.errors import ApiError
from app.models import CheckIn, Escalation
from app.routers.webhooks import sign_elevenlabs
from app.services import escalation, replay
from tests.conftest import COORD, SECRET

ROLES = ["coordinator", "investigator", "sponsor", "cra"]
MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(range(256)) * 4  # not real audio; the route serves bytes as they are
FIXTURE = ROOT / "scenarios" / "fixtures" / "post_call_rosa.json"


def _scenario(sid: str, **extra: object) -> dict:
    return {"id": sid, "title": sid, "patient_id": "pat_rosa", "day_after_dose": 3,
            "events": [{"t": 0.0, "type": "call_started"}, {"t": 12.0, "type": "call_ended"}], **extra}


@pytest.fixture
def scenarios_dir(monkeypatch, tmp_path: Path) -> Path:
    """A private scenarios/ directory: rec_audio (recorded, with mp3), rec_silent (recorded, no mp3)."""
    monkeypatch.setattr(replay, "SCENARIOS_DIR", tmp_path)
    (tmp_path / "rec_audio.json").write_text(json.dumps(_scenario("rec_audio", recorded=True, recorded_at="2026-10-11")))
    (tmp_path / "rec_silent.json").write_text(json.dumps(_scenario("rec_silent", recorded=True, recorded_at="2026-10-11")))
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "rec_audio.mp3").write_bytes(MP3)
    (tmp_path / "audio" / "orphan.mp3").write_bytes(MP3)  # audio without a scenario file
    return tmp_path


def error_code(r) -> str:  # noqa: ANN001
    return r.json()["error"]["code"]


# ---- GET /api/demo/scenarios/{scenario_id}/audio (docs/03 §6.2) ---------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_audio_served_as_mpeg_to_any_role(demo_mode, client, scenarios_dir, role: str) -> None:
    r = client.get("/api/demo/scenarios/rec_audio/audio", headers={**COORD, "X-BV-Role": role})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content == MP3


def test_audio_supports_byte_ranges(demo_mode, client, scenarios_dir) -> None:
    """Browsers seek in an <audio> element with Range requests."""
    r = client.get("/api/demo/scenarios/rec_audio/audio", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206
    assert r.content == MP3[:10]


def test_audio_url_in_the_list_is_the_route(demo_mode, client, scenarios_dir) -> None:
    items = {it["id"]: it for it in client.get("/api/demo/scenarios").json()}
    assert items["rec_audio"]["audio_url"] == "/api/demo/scenarios/rec_audio/audio"
    assert items["rec_silent"]["audio_url"] is None
    assert client.get(items["rec_audio"]["audio_url"]).content == MP3


def test_audio_not_found(demo_mode, client, scenarios_dir) -> None:
    r = client.get("/api/demo/scenarios/rec_silent/audio")
    assert r.status_code == 404 and error_code(r) == "audio_not_found"


@pytest.mark.parametrize("sid", ["no_such_scenario", "orphan", "rosa es", "fixtures"])
def test_scenario_not_found(demo_mode, client, scenarios_dir, sid: str) -> None:
    r = client.get(f"/api/demo/scenarios/{sid}/audio")
    assert r.status_code == 404 and error_code(r) == "scenario_not_found"


@pytest.mark.parametrize("sid", ["../rec_audio", "..", "a/b", "", "rec_audio.json", "audio/rec_audio"])
def test_service_refuses_non_slug_ids(scenarios_dir, sid: str) -> None:
    with pytest.raises(ApiError) as e:
        replay.scenario_audio_file(sid)
    assert e.value.code == "scenario_not_found"


@pytest.mark.req("REQ-017")
@pytest.mark.parametrize("sid", ["rec_audio", "rec_silent", "no_such_scenario"])
def test_audio_is_demo_only(client, scenarios_dir, sid: str) -> None:
    """Outside DEMO_MODE the route is hidden even when the file exists: 404 demo_disabled."""
    r = client.get(f"/api/demo/scenarios/{sid}/audio")
    assert r.status_code == 404 and error_code(r) == "demo_disabled"


def test_audio_is_not_audited(demo_mode, client, scenarios_dir) -> None:
    before = client.get("/api/audit", params={"limit": 200}).json()
    assert client.get("/api/demo/scenarios/rec_audio/audio").status_code == 200
    assert client.get("/api/audit", params={"limit": 200}).json() == before


def test_openapi_documents_the_audio_route(client) -> None:
    op = client.get("/openapi.json").json()["paths"]["/api/demo/scenarios/{scenario_id}/audio"]["get"]
    assert "audio/mpeg" in op["responses"]["200"]["content"]
    assert "404" in op["responses"]


def test_committed_scenarios_never_ship_audio() -> None:
    """Audio is gitignored and never committed (docs/03 §6.2); a scenario file only points at the path."""
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "scenarios/audio/*.mp3" in gitignore
    for path in SCENARIOS_DIR.glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc.get("audio") in (None, f"scenarios/audio/{path.stem}.mp3"), path.name


# ---- export -> replay gives the live call's grades (WS1 V11 acceptance, offline) -----------------------------------


class InlineThread:
    def __init__(self, target, args=(), **_):  # noqa: ANN001
        self.target, self.args = target, args

    def start(self) -> None:
        self.target(*self.args)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def exporter() -> ModuleType:
    """agent/export_scenario.py (stdlib only), imported without leaving agent/ on sys.path."""
    before = list(sys.path)
    sys.path.insert(0, str(ROOT / "agent"))
    try:
        return importlib.import_module("export_scenario")
    finally:
        sys.path[:] = before


def outcome(client, checkin_id: str) -> dict:  # noqa: ANN001
    d = client.get(f"/api/checkins/{checkin_id}").json()
    return {
        "findings": sorted((f["term"], f["provisional_grade"], f["rule_id"], f["escalation_level"],
                            tuple(sorted(f["red_flag_ids"]))) for f in d["findings"]),
        "escalations": sorted((e["level"], tuple(sorted(e["red_flag_ids"])), e["status"]) for e in d["escalations"]),
        "drafts": sorted((x["kind"], x["payload"].get("term") or x["payload"].get("medication_name"),
                          x["payload"].get("provisional_grade")) for x in d["drafts"]),
    }


def test_exported_scenario_replays_like_the_live_call(demo_mode, client, session, fake_pager, monkeypatch,
                                                      tmp_path: Path, exporter: ModuleType) -> None:
    """A call played live through the HTTP tools and the signed post-call webhook, exported with
    agent/export_scenario.py from the conversation and GET /api/checkins/{id}, then replayed through the real handlers:
    same findings (grade, rule_id, escalation level), escalations and drafts. Scripted fixture, tmp dir only."""
    event = json.loads(FIXTURE.read_text(encoding="utf-8"))
    conv = event["data"]
    live = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_rosa")).one()
    live.el_conversation_id = conv["conversation_id"]
    session.add(live)
    session.commit()
    # The live call: every tool call the agent made, over HTTP, then the nurse acknowledges, then the webhook.
    for turn in conv["transcript"]:
        for call in turn.get("tool_calls") or []:
            body = {**json.loads(call["params_as_json"]), "checkin_id": live.id}
            assert client.post(f"/agent/tools/{call['tool_name']}", json=body, headers=SECRET).status_code == 200
    esc = session.exec(select(Escalation).where(Escalation.checkin_id == live.id)).one()
    escalation.acknowledge(session, esc, by="RN on call", method="push_button")
    session.commit()
    raw = json.dumps(event).encode()
    r = client.post("/webhooks/elevenlabs/post-call", content=raw, headers={
        "ElevenLabs-Signature": sign_elevenlabs(raw, "whsec-test"), "Content-Type": "application/json"})
    assert r.status_code == 200
    live_outcome = outcome(client, live.id)
    assert ("Diarrhea", 3, "CTCAE5_DIARRHEA_G3", "urgent", ("RF_DIARRHEA_SEVERE",)) \
        in live_outcome["findings"]

    # Export: the conversation as ElevenLabs returns it, the check-in as the live backend returns it.
    detail = client.get(f"/api/checkins/{live.id}").json()
    acked = [exporter.parse_utc(e["acknowledged_at"]) for e in detail["escalations"] if e["acknowledged_at"]]
    assert len(acked) == 1 and acked[0] is not None
    conv["metadata"]["start_time_unix_secs"] = int(acked[0].timestamp()) - 110  # acknowledged 110 s into the call
    conv["conversation_initiation_client_data"]["dynamic_variables"]["checkin_id"] = live.id
    assert exporter.check_link(conv, detail["checkin"], conv["conversation_id"], live.id) == []
    doc, _ = exporter.build_scenario(conv, detail, scenario_id="rec_fidelity", title="Fidelity check")
    assert exporter.check_whitelist(doc, exporter.tool_arg_whitelist()) == []
    assert any(e["type"] == "page_ack" and 109 <= e["t"] <= 111 for e in doc["events"])
    monkeypatch.setattr(replay, "SCENARIOS_DIR", tmp_path)
    (tmp_path / "rec_fidelity.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    # Replay through the real handlers, at 4x on a virtual clock.
    monkeypatch.setattr(replay, "time", FakeClock())
    monkeypatch.setattr(replay, "threading", SimpleNamespace(Thread=InlineThread))
    listed = {it["id"]: it for it in client.get("/api/demo/scenarios").json()}["rec_fidelity"]
    assert listed["recorded"] is True and listed["label"] == replay.RECORDED_LABEL
    r = client.post("/api/demo/replay/rec_fidelity", params={"speed": 4})
    assert r.status_code == 200, r.text
    replayed = r.json()["checkin_id"]
    assert replayed != live.id
    assert outcome(client, replayed) == live_outcome
    assert all(e["status"] == "acknowledged" for e in client.get(f"/api/checkins/{replayed}").json()["escalations"])
    assert len(fake_pager.sent) == 2  # one urgent page for the live call, one for the replay

