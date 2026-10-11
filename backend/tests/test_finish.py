"""Finish a call now (docs/03 §6.12): a replay fast-forwards, an ended live call is read from ElevenLabs."""

import json
from types import SimpleNamespace

from sqlmodel import select

from app.config import SCENARIOS_DIR
from app.models import AuditEvent, CheckIn, DraftEntry
from app.services import call_end, elevenlabs, replay
from tests.conftest import COORD

ROSA = "rosa_es_urgent"
ROSA_END = max(e["t"] for e in json.loads((SCENARIOS_DIR / f"{ROSA}.json").read_text(encoding="utf-8"))["events"])
FIXTURE = json.loads((SCENARIOS_DIR / "fixtures" / "post_call_rosa.json").read_text(encoding="utf-8"))["data"]


class InlineThread:
    def __init__(self, target, args=(), **_):  # noqa: ANN001
        self.target, self.args = target, args

    def start(self) -> None:
        self.target(*self.args)


class FinishAfter:
    """Virtual clock for the replay engine that presses "Finish now" once `after` seconds have passed."""

    def __init__(self, after: float) -> None:
        self.now, self.after = 0.0, after

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        if self.now >= self.after:
            for cid in list(replay._running):
                replay.fast_forward(cid)


def test_replay_finish_now_plays_the_rest_at_once(demo_mode, client, session, monkeypatch, fake_pager) -> None:
    clock = FinishAfter(after=30.0)  # Rosa has given her stool count and been paged by then, nothing else
    monkeypatch.setattr(replay, "time", clock)
    monkeypatch.setattr(replay, "threading", SimpleNamespace(Thread=InlineThread))
    cid = client.post(f"/api/demo/replay/{ROSA}", params={"speed": 1}).json()["checkin_id"]
    assert clock.now < 31 < ROSA_END  # ended early ...
    detail = client.get(f"/api/checkins/{cid}").json()
    assert detail["checkin"]["status"] == "completed"  # ... and everything is there
    assert detail["checkin"]["postcall_status"] == "done"
    assert sorted(d["kind"] for d in client.get("/api/drafts", params={"checkin_id": cid}).json()) == ["AE", "AE", "CM"]
    assert [(e["level"], e["status"]) for e in detail["escalations"]] == [("urgent", "acknowledged")]
    assert not replay.is_running(cid)


def test_finish_endpoint_fast_forwards_a_running_replay(demo_mode, client, session, monkeypatch) -> None:
    c = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_rosa")).first()
    c.channel, c.status = "replay", "in_progress"
    session.add(c)
    session.commit()
    replay._running.add(c.id)
    try:
        r = client.post(f"/api/checkins/{c.id}/finish", headers=COORD)
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "fast_forward" and c.id in replay._fast_forward
    finally:
        replay._running.discard(c.id)
        replay._fast_forward.discard(c.id)
    audit = session.exec(select(AuditEvent).where(AuditEvent.action == "checkin.finished_early")).all()
    assert [a.entity_id for a in audit] == [c.id]


def test_finish_with_nothing_running_is_409(client, session) -> None:
    c = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_rosa")).first()  # scheduled, never called
    r = client.post(f"/api/checkins/{c.id}/finish", headers=COORD)
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_in_call"
    c.channel, c.status = "replay", "in_progress"  # a replay row whose thread is gone (e.g. after a restart)
    session.add(c)
    session.commit()
    assert client.post(f"/api/checkins/{c.id}/finish", headers=COORD).json()["error"]["code"] == "not_in_call"


def test_finish_reads_an_ended_live_call_without_waiting_for_the_webhook(client, session, monkeypatch) -> None:
    c = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_rosa")).first()
    c.channel, c.status, c.el_conversation_id = "web", "in_progress", "conv_live_1"
    session.add(c)
    session.commit()
    reads: list[str] = []

    class Fake:
        def get_conversation(self, conversation_id: str) -> dict:
            reads.append(conversation_id)  # "processing" first: ElevenLabs is still analyzing the call
            status = "processing" if len(reads) == 1 else "done"
            return {**FIXTURE, "conversation_id": "other", "status": status,
                    "conversation_initiation_client_data": {"dynamic_variables": {"checkin_id": c.id}}}

    monkeypatch.setattr(call_end, "threading", SimpleNamespace(Thread=InlineThread))
    monkeypatch.setattr(call_end, "time", SimpleNamespace(sleep=lambda s: None, monotonic=lambda: 0.0))
    elevenlabs.set_client(Fake())
    try:
        r = client.post(f"/api/checkins/{c.id}/finish", headers=COORD)
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "pulling" and reads == ["conv_live_1", "conv_live_1"]
        session.expire_all()
        c = session.get(CheckIn, c.id)
        assert c.postcall_status == "done" and c.status == "completed" and c.transcript
        assert session.exec(select(DraftEntry).where(DraftEntry.checkin_id == c.id)).all()
        # pressing it again, or the webhook arriving later, does not run post-call twice
        assert client.post(f"/api/checkins/{c.id}/finish", headers=COORD).json()["mode"] == "already_done"
    finally:
        elevenlabs.set_client(None)


def test_finish_gives_up_quietly_when_elevenlabs_is_unreachable(session, monkeypatch) -> None:
    class Down:
        def get_conversation(self, conversation_id: str) -> dict:
            raise RuntimeError("ElevenLabs conversation 503")

    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(call_end, "time", SimpleNamespace(sleep=lambda s: setattr(clock, "now", clock.now + s),
                                                          monotonic=lambda: clock.now))
    elevenlabs.set_client(Down())
    try:
        call_end.pull_post_call("ci_missing", "conv_x")  # returns; the post-call webhook stays the path
    finally:
        elevenlabs.set_client(None)
    assert clock.now >= call_end.MAX_WAIT_S
