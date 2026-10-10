"""B7 acceptance: signed post-call fixtures → transcript, drafts with evidence, safety-net escalation."""

import json
from pathlib import Path

import pytest
from sqlmodel import select

from app.config import ROOT
from app.models import CheckIn, DraftEntry, Escalation
from app.routers.webhooks import sign_elevenlabs, verify_elevenlabs_signature
from app.services import gemini
from tests.conftest import SECRET

FIX = ROOT / "scenarios" / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def post(client, event: dict, secret: str = "whsec-test"):
    raw = json.dumps(event).encode()
    return client.post("/webhooks/elevenlabs/post-call", content=raw,
                       headers={"ElevenLabs-Signature": sign_elevenlabs(raw, secret), "Content-Type": "application/json"})


def replay_live_tools(client, cid: str, event: dict) -> None:
    """Re-run the live tool calls recorded in the fixture transcript (as the agent did during the call)."""
    for t in event["data"]["transcript"]:
        for tc in t.get("tool_calls") or []:
            body = {**json.loads(tc["params_as_json"]), "checkin_id": cid}
            r = client.post(f"/agent/tools/{tc['tool_name']}", json=body, headers=SECRET)
            assert r.status_code == 200


@pytest.mark.req("REQ-013")
def test_signature_verification():
    raw = b'{"a":1}'
    assert verify_elevenlabs_signature(raw, sign_elevenlabs(raw, "s"), "s")
    assert not verify_elevenlabs_signature(raw, sign_elevenlabs(raw, "other"), "s")
    assert not verify_elevenlabs_signature(raw, sign_elevenlabs(raw, "s", ts=1), "s")  # too old
    assert not verify_elevenlabs_signature(raw, None, "s")


@pytest.mark.req("REQ-013")
def test_bad_signature_401(client):
    assert post(client, load("post_call_rosa.json"), secret="wrong").status_code == 401


@pytest.mark.req("REQ-008")
@pytest.mark.req("REQ-009")
def test_rosa_post_call_creates_drafts(client, session, fake_pager):
    ev = load("post_call_rosa.json")
    rosa = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_rosa")).one()
    rosa.el_conversation_id = ev["data"]["conversation_id"]
    session.add(rosa)
    session.commit()
    sc = json.loads((ROOT / "scenarios" / "rosa_es_urgent.json").read_text(encoding="utf-8"))
    gemini.KNOWN_TRANSLATIONS.update(sc["translations_en"])
    replay_live_tools(client, rosa.id, ev)
    assert len(fake_pager.sent) == 1

    assert post(client, ev).status_code == 200
    assert post(client, ev).status_code == 200  # idempotent by conversation_id

    session.expire_all()
    c = session.get(CheckIn, rosa.id)
    assert c.status == "completed" and c.postcall_status == "done"
    assert len(c.transcript) == sum(1 for t in ev["data"]["transcript"] if t.get("message"))
    ds = session.exec(select(DraftEntry).where(DraftEntry.checkin_id == rosa.id)).all()
    ae = {d.payload["term"]: d for d in ds if d.kind == "AE"}
    cm = [d for d in ds if d.kind == "CM"]
    assert set(ae) == {"Diarrhea", "Dizziness"}
    assert ae["Diarrhea"].payload["provisional_grade"] == 3
    assert ae["Diarrhea"].payload["escalation_id"]
    assert ae["Dizziness"].evidence[0]["source"] == "post_call_extraction"
    assert len(cm) == 1 and "loperamide" in cm[0].payload["medication_name"]
    for d in ds:  # REQ-008: evidence on every draft
        assert d.evidence and all(e["quote"] and e["source"] for e in d.evidence)
    ev0 = ae["Diarrhea"].evidence[-1]
    assert ev0["quote_lang"] == "es" and ev0["t_s"] is not None
    assert ev0["translation_en"] and ev0["translation_label"] == "AI translation, verify"  # REQ-009
    assert ev0["quote"] != ev0["translation_en"]
    assert len(fake_pager.sent) == 1  # nothing missed: no extra page


@pytest.mark.req("REQ-012")
def test_safety_net_catches_missed_chest_pain(client, session, fake_pager):
    ev = load("post_call_missed_red_flag.json")
    c = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_mei")).one()
    c.el_conversation_id = ev["data"]["conversation_id"]
    session.add(c)
    session.commit()
    replay_live_tools(client, c.id, ev)
    assert not fake_pager.sent
    assert post(client, ev).status_code == 200
    session.expire_all()
    escs = session.exec(select(Escalation).where(Escalation.checkin_id == c.id)).all()
    assert len(escs) == 1
    assert escs[0].level == "emergency" and escs[0].reason == "post_call_safety_net"
    assert escs[0].red_flag_ids == ["RF_CHEST_PAIN"]
    assert len(fake_pager.sent) == 1 and fake_pager.sent[0].level == "emergency"
    ae = session.exec(select(DraftEntry).where(DraftEntry.checkin_id == c.id, DraftEntry.kind == "AE")).all()
    assert any(d.payload["term"] == "Chest pain" for d in ae)


def test_call_initiation_failure_sets_no_answer(client, session):
    c = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_james")).one()
    c.el_conversation_id = "conv_fail"
    session.add(c)
    session.commit()
    r = post(client, {"type": "call_initiation_failure", "data": {"conversation_id": "conv_fail", "failure_reason": "no-answer"}})
    assert r.status_code == 200
    session.expire_all()
    assert session.get(CheckIn, c.id).status == "no_answer"


_ = Path


@pytest.mark.req("REQ-012")
def test_browser_call_payload_with_null_fields(client, session, fake_pager):
    """Browser (WebRTC) calls send phone_call: null; a crash here must never be silent."""
    ev = load("post_call_rosa.json")
    ev["data"]["metadata"]["phone_call"] = None
    ev["data"]["analysis"] = None
    ev["data"]["conversation_id"] = "conv_browser"
    c = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_rosa")).one()
    c.el_conversation_id = "conv_browser"
    session.add(c)
    session.commit()
    assert post(client, ev).status_code == 200
    session.expire_all()
    c = session.get(CheckIn, c.id)
    assert c.postcall_status == "done" and c.status == "completed" and c.transcript


def test_postcall_crash_escalates(client, session, fake_pager, monkeypatch):
    from app.services import postcall

    def boom(*a, **k):
        raise RuntimeError("pipeline bug")

    monkeypatch.setattr(postcall, "apply_call_metadata", boom)
    ev = load("post_call_rosa.json")
    c = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_rosa")).one()
    c.el_conversation_id = ev["data"]["conversation_id"]
    session.add(c)
    session.commit()
    assert post(client, ev).status_code == 200
    session.expire_all()
    escs = session.exec(select(Escalation).where(Escalation.checkin_id == c.id)).all()
    assert [e.level for e in escs] == ["urgent"] and escs[0].reason == "post_call_safety_net"
    assert len(fake_pager.sent) == 1 and session.get(CheckIn, c.id).postcall_status == "failed"
