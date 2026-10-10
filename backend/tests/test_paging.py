"""B6: page text, ntfy ack, re-page and backup with a fake clock (REQ-005, REQ-006)."""

from datetime import timedelta

import pytest
from sqlmodel import select

from app.models import CheckIn, Escalation
from app.routers.agent_tools import call_tool_inprocess
from app.services import escalation, pager
from app.timeutil import utcnow


def urgent_escalation(session) -> Escalation:
    cid = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_rosa")).one().id
    for body in (
        {"item_code": "IDENTITY", "option_code": "yes"},
        {"item_code": "CALL_CONSENT", "option_code": "yes"},
        {"item_code": "DIARRHEA_FREQ", "option_code": "often"},
        {"item_code": "DIARRHEA_STOOLS_PER_DAY", "numeric_value": 9, "unit": "per_day"},
    ):
        call_tool_inprocess("record_answer", {"checkin_id": cid, "verbatim_quote": "x", **body}, session)
    session.expire_all()
    return session.exec(select(Escalation).where(Escalation.checkin_id == cid)).one()


@pytest.mark.req("REQ-005")
def test_page_message_has_subject_id_only(session, fake_pager):
    e = urgent_escalation(session)
    assert e.paged_at is not None and e.page_channel == "fake"
    msg = fake_pager.sent[0]
    assert msg.title == "URGENT · Patient 101-007"
    assert "8 stools a day above baseline" in msg.text and "Spanish" in msg.text
    assert "Rosa" not in msg.text + msg.title


@pytest.mark.req("REQ-006")
def test_repage_and_backup(session, fake_pager):
    e = urgent_escalation(session)
    assert len(fake_pager.sent) == 1
    t = utcnow()
    assert escalation.repage_due(session, t + timedelta(seconds=30)) == 0  # before ACK_TIMEOUT (90 s)
    assert escalation.repage_due(session, t + timedelta(seconds=91)) == 1
    assert escalation.repage_due(session, t + timedelta(seconds=150)) == 0
    assert escalation.repage_due(session, t + timedelta(seconds=185)) == 2  # second re-page + backup
    session.expire_all()
    e = session.get(Escalation, e.id)
    assert e.repage_count == 2 and e.backup_paged_at is not None
    assert [m.backup for m in fake_pager.sent] == [False, False, False, True]
    # acknowledged escalations are never re-paged
    escalation.acknowledge(session, e, by="RN", method="dashboard")
    session.commit()
    assert escalation.repage_due(session, t + timedelta(seconds=999)) == 0


@pytest.mark.req("REQ-005")
def test_failed_page_is_retried(session, fake_pager):
    def boom(msg):
        raise RuntimeError("ntfy down")

    pager.set_pager(boom)
    e = urgent_escalation(session)
    assert e.paged_at is None  # escalation exists and stays open even though the page failed
    pager.set_pager(fake_pager)
    assert escalation.repage_due(session, utcnow() + timedelta(seconds=11)) == 1
    session.expire_all()
    assert session.get(Escalation, e.id).paged_at is not None


@pytest.mark.req("REQ-013")
def test_ntfy_ack_requires_token(client, session, fake_pager):
    e = urgent_escalation(session)
    assert client.post(f"/webhooks/ntfy/ack/{e.id}").status_code == 401
    assert client.post(f"/webhooks/ntfy/ack/{e.id}", headers={"Authorization": "Bearer nope"}).status_code == 401
    ok = client.post(f"/webhooks/ntfy/ack/{e.id}", headers={"Authorization": f"Bearer {e.ack_token}"})
    assert ok.status_code == 200 and ok.json() == {"ok": True}
    again = client.post(f"/webhooks/ntfy/ack/{e.id}", headers={"Authorization": f"Bearer {e.ack_token}"})
    assert again.status_code == 200
    session.expire_all()
    e = session.get(Escalation, e.id)
    assert e.status == "acknowledged" and e.ack_method == "push_button"
    detail = client.get(f"/api/checkins/{e.checkin_id}").json()
    assert detail["escalations"][0]["seconds_to_ack"] is not None


def test_twiml_is_absolute_and_escaped():
    msg = pager.PageMessage("esc_X", "urgent", "t", "Patient 1 0 1, 0 0 7 & more", "tok")
    xml = pager.twiml_for(msg)
    assert 'action="https://bv-test.example/webhooks/twilio/page-ack?escalation_id=esc_X"' in xml
    assert "&amp; more" in xml and len(xml) < 4000


def test_twilio_page_ack_requires_signature(client, session, fake_pager):
    from twilio.request_validator import RequestValidator

    e = urgent_escalation(session)
    url = f"https://bv-test.example/webhooks/twilio/page-ack?escalation_id={e.id}"
    params = {"Digits": "1", "CallSid": "CA1"}
    sig = RequestValidator("twilio-test-token").compute_signature(url, params)
    r = client.post(f"/webhooks/twilio/page-ack?escalation_id={e.id}", data=params, headers={"X-Twilio-Signature": sig})
    assert r.status_code == 200 and "Acknowledged" in r.text
    session.expire_all()
    assert session.get(Escalation, e.id).ack_method == "phone_keypress"
