"""B8: review actions are audited, investigator gate, 24-hour clock, sponsor inbox, exports; B9 replay; inbound."""

import csv
import io
from datetime import timedelta

import pytest
from sqlmodel import select

from app.models import AuditEvent, CheckIn, DraftEntry
from app.services import replay
from app.services.export import AE_COLUMNS, CM_COLUMNS
from tests.conftest import COORD, INVESTIGATOR, SECRET


def run_rosa(session) -> str:
    return replay.start(session, "rosa_es_urgent", speed=10_000, run_async=False)


@pytest.mark.req("REQ-015")
def test_replay_runs_full_story(client, session, fake_pager):
    cid = run_rosa(session)
    d = client.get(f"/api/checkins/{cid}").json()
    assert d["checkin"]["status"] == "completed" and d["checkin"]["channel"] == "replay"
    assert any(f["term"] == "Diarrhea" and f["provisional_grade"] == 3 for f in d["findings"])
    esc = d["escalations"][0]
    assert esc["level"] == "urgent" and esc["status"] == "acknowledged"
    assert esc["red_flag_ids"] == ["RF_DIARRHEA_SEVERE", "RF_DEHYDRATION"]
    kinds = sorted((x["kind"], x["payload"].get("term") or x["payload"].get("medication_name")) for x in d["drafts"])
    assert kinds == [("AE", "Diarrhea"), ("AE", "Dizziness"), ("CM", "loperamide (Imodium)")]
    assert len(d["transcript"]) > 10
    assert len(fake_pager.sent) == 1


@pytest.mark.req("REQ-010")
@pytest.mark.req("REQ-011")
def test_review_to_sponsor(client, session, fake_pager):
    cid = run_rosa(session)
    drafts = client.get("/api/drafts", params={"checkin_id": cid}).json()
    assert all(d["status"] == "draft" for d in drafts)  # nothing final without a human
    ae = next(d for d in drafts if d["payload"].get("term") == "Diarrhea")
    n0 = len(session.exec(select(AuditEvent)).all())

    r = client.patch(f"/api/drafts/{ae['id']}", json={"payload": {"onset_date": "2026-10-08"}, "note": "per nurse call"}, headers=COORD)
    assert r.status_code == 200 and r.json()["payload"]["onset_date"] == "2026-10-08"
    # investigator actions need a confirmed AE and the investigator role
    assert client.post(f"/api/drafts/{ae['id']}/investigator", json={"is_serious": True, "seriousness_criteria": ["hospitalization"],
                       "relatedness": "possibly_related"}, headers=INVESTIGATOR).status_code == 409
    assert client.post(f"/api/drafts/{ae['id']}/confirm", json={}, headers=COORD).json()["status"] == "confirmed"
    assert client.post(f"/api/drafts/{ae['id']}/investigator", json={"is_serious": True, "seriousness_criteria": ["hospitalization"],
                       "relatedness": "possibly_related"}, headers=COORD).status_code == 409
    r = client.post(f"/api/drafts/{ae['id']}/investigator", json={"is_serious": True, "seriousness_criteria": ["hospitalization"],
                    "relatedness": "possibly_related", "sign": True}, headers=INVESTIGATOR)
    assert r.status_code == 200
    sae = r.json()["sae_report"]
    from datetime import datetime

    aware, due = (datetime.fromisoformat(sae[k].replace("Z", "+00:00")) for k in ("aware_at", "due_at"))
    assert due - aware == timedelta(hours=24)  # REQ-011
    full = client.get(f"/api/sae/{sae['id']}").json()
    assert full["narrative_ai_draft"] and full["payload"]["patient"]["subject_id"] == "101-007"
    assert "anti-PD-1" in full["payload"]["suspect_product"]["description"]

    assert client.post(f"/api/sae/{sae['id']}/send", headers=COORD).status_code == 409  # must be signed first
    assert client.post(f"/api/sae/{sae['id']}/sign", headers=COORD).status_code == 409
    assert client.post(f"/api/sae/{sae['id']}/sign", headers=INVESTIGATOR).json()["status"] == "signed"
    assert client.post(f"/api/sae/{sae['id']}/send", headers=COORD).json()["status"] == "sent"
    inbox = client.get("/api/sponsor/inbox").json()
    assert len(inbox) == 1 and inbox[0]["on_time"] and all(inbox[0]["valid_case_checks"].values())

    cm = next(d for d in drafts if d["kind"] == "CM")
    assert client.post(f"/api/drafts/{cm['id']}/reject", json={"reason": ""}, headers=COORD).status_code == 422
    assert client.post(f"/api/drafts/{cm['id']}/confirm", json={}, headers=COORD).status_code == 200

    actions = [a.action for a in session.exec(select(AuditEvent)).all()][n0:]
    for needed in ("draft.edited", "draft.confirmed", "draft.investigator_assessed", "sae.created", "sae.signed", "sae.sent"):
        assert needed in actions
    human = [a for a in session.exec(select(AuditEvent)).all()[n0:] if a.action.startswith(("draft.", "sae."))]
    assert {a.actor for a in human} <= {"Jess Kim", "Dr. Patel"}

    ae_csv = client.get("/api/export/ae.csv").text
    rows = list(csv.reader(io.StringIO(ae_csv.split("\n", 1)[1])))
    assert rows[0] == AE_COLUMNS and rows[1][AE_COLUMNS.index("AETOXGR")] == "3"
    assert rows[1][AE_COLUMNS.index("AESHOSP")] == "Y" and rows[1][AE_COLUMNS.index("AEDECOD")] == ""
    cm_rows = list(csv.reader(io.StringIO(client.get("/api/export/cm.csv").text.split("\n", 1)[1])))
    assert cm_rows[0] == CM_COLUMNS and len(cm_rows) == 2


def test_dashboard_reads(client, session, fake_pager):
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/api/study").json()["nct_id"] == "NCT02760498"
    plan = client.get("/api/plan/active").json()
    assert all(i["text"]["en"] and i["text"]["es"] for i in plan["items"] if i["kind"] != "flow" or i["item_code"] not in ("IDENTITY", "CALL_CONSENT"))
    pats = client.get("/api/patients").json()
    assert len(pats) == 6 and all(p["next_due"] for p in pats)
    today = client.get("/api/checkins").json()
    assert len(today) == 6
    assert client.get("/api/patients/pat_rosa").json()["subject_id"] == "101-007"
    assert client.get("/api/checkins/nope").json()["error"]["code"] == "checkin_not_found"
    assert client.get("/api/demo/scenarios").json()[0]["id"] == "rosa_es_urgent"
    assert client.get("/openapi.json").status_code == 200


def test_phone_checkin_without_keys_is_503(client):
    r = client.post("/api/patients/pat_james/checkins", json={"channel": "phone"}, headers=COORD)
    assert r.status_code == 503 and r.json()["error"]["code"] == "telephony_unavailable"


def test_web_checkin_with_fake_elevenlabs(client, session, tmp_path, monkeypatch):
    from app.services import elevenlabs

    class Fake:
        def outbound_call(self, agent_id, to_number, user_id, dynamic_variables):
            return elevenlabs.CallStarted("conv_out", "CA1")

        def web_token(self, agent_id):
            return elevenlabs.WebToken("tok", "conv_web")

    monkeypatch.setattr(elevenlabs, "load_lock", lambda: {v: f"agent_{v}" for v in ("en-standard", "es-extra_time")})
    elevenlabs.set_client(Fake())
    try:
        r = client.post("/api/patients/pat_rosa/checkins", json={"channel": "web"}, headers=COORD)
        assert r.status_code == 201, r.text
        ws = r.json()["web_session"]
        assert ws["agent_id"] == "agent_es-extra_time" and ws["dynamic_variables"]["language_name"] == "Spanish"
        assert ws["dynamic_variables"]["checkin_id"] == r.json()["checkin"]["id"]
        assert client.post("/api/patients/pat_rosa/checkins", json={"channel": "web"}, headers=COORD).status_code == 409
        r = client.post("/api/patients/pat_james/checkins", json={"channel": "phone"}, headers=COORD)
        assert r.status_code == 201 and r.json()["checkin"]["status"] == "dialing"
    finally:
        elevenlabs.set_client(None)


def test_inbound_init(client, session):
    from app.models import Patient

    p = session.get(Patient, "pat_rosa")
    body = {"caller_id": p.phone_e164, "called_number": "+15555550100", "agent_id": "a", "call_sid": "CA", "conversation_id": "conv_in"}
    r = client.post("/webhooks/elevenlabs/inbound-init", json=body, headers=SECRET)
    j = r.json()
    assert r.status_code == 200 and j["user_id"] == "101-007"
    assert j["dynamic_variables"]["checkin_id"].startswith("ci_")
    assert "Rosa" in j["conversation_config_override"]["agent"]["first_message"]
    session.expire_all()
    c = session.get(CheckIn, j["dynamic_variables"]["checkin_id"])
    assert c.channel == "phone_inbound" and c.el_conversation_id == "conv_in"
    unknown = client.post("/webhooks/elevenlabs/inbound-init", json={**body, "caller_id": "+15555559999"}, headers=SECRET).json()
    assert unknown["dynamic_variables"]["checkin_id"] == "unknown"
    bad = client.post("/webhooks/elevenlabs/inbound-init", json=body)
    assert bad.status_code == 200 and bad.json()["dynamic_variables"]["checkin_id"] == "unknown"


_ = DraftEntry
