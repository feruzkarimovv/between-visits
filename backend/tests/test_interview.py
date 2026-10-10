"""Interview engine paths: emergency close, raise and re-page, caregiver, consent, advice deferral, corrections."""

import pytest
from sqlmodel import select

from app import content
from app.models import CheckIn, DraftEntry, Escalation
from app.routers.agent_tools import call_tool_inprocess


def checkin_for(session, patient_id: str) -> CheckIn:
    return session.exec(select(CheckIn).where(CheckIn.patient_id == patient_id)).one()


def tool(session, name: str, cid: str, **body) -> dict:
    return call_tool_inprocess(name, {"checkin_id": cid, **body}, session).model_dump()


def to_symptoms(session, cid: str) -> dict:
    tool(session, "record_answer", cid, item_code="IDENTITY", option_code="yes", verbatim_quote="yes")
    return tool(session, "record_answer", cid, item_code="CALL_CONSENT", option_code="yes", verbatim_quote="sure")


def escs(session, cid: str) -> list[Escalation]:
    session.expire_all()
    return list(session.exec(select(Escalation).where(Escalation.checkin_id == cid)).all())


V_EN = {"study_team_name": "the Hillside research team", "patient_first_name": "James", "caregiver_name": "a caregiver"}


@pytest.mark.req("REQ-005")
def test_chest_pain_is_emergency_and_closes(session, fake_pager):
    cid = checkin_for(session, "pat_james").id
    to_symptoms(session, cid)
    r = tool(session, "report_red_flag", cid, red_flag_id="RF_CHEST_PAIN", verbatim_quote="my chest hurts")
    assert r["next"]["action"] == "close"
    assert r["next"]["say"] == f"{content.script('emergency_line', 'en')} {content.script('closing_after_escalation', 'en', **V_EN)}"
    assert len(fake_pager.sent) == 1 and fake_pager.sent[0].level == "emergency"
    assert "EMERGENCY" in fake_pager.sent[0].title


@pytest.mark.req("REQ-005")
def test_urgent_then_heart_adds_then_chest_raises(session, fake_pager):
    cid = checkin_for(session, "pat_james").id
    to_symptoms(session, cid)
    tool(session, "record_answer", cid, item_code="DIARRHEA_FREQ", option_code="never", verbatim_quote="never")
    tool(session, "record_answer", cid, item_code="NAUSEA_FREQ", option_code="never", verbatim_quote="no")
    tool(session, "record_answer", cid, item_code="VOMITING_FREQ", option_code="never", verbatim_quote="no")
    r = tool(session, "record_answer", cid, item_code="FEVER_CHILLS", option_code="yes", verbatim_quote="yes chills")
    assert r["next"]["item_code"] == "TEMP_HIGHEST"
    r = tool(session, "record_answer", cid, item_code="TEMP_HIGHEST", numeric_value=101.5, unit="fahrenheit", verbatim_quote="101.5")
    assert r["escalated"] and r["next"]["item_code"] == "MEDS_NEW"
    assert len(fake_pager.sent) == 1
    r = tool(session, "report_red_flag", cid, red_flag_id="RF_HEART", verbatim_quote="my heart is racing")
    assert r["next"]["say"].startswith(content.script("added_to_page", "en"))
    assert len(fake_pager.sent) == 1 and len(escs(session, cid)) == 1
    r = tool(session, "report_red_flag", cid, red_flag_id="RF_CHEST_PAIN", verbatim_quote="and chest pressure")
    assert r["next"]["action"] == "close"
    assert len(fake_pager.sent) == 2 and fake_pager.sent[1].level == "emergency"
    e = escs(session, cid)
    assert len(e) == 1 and e[0].level == "emergency" and e[0].status == "open"
    assert e[0].red_flag_ids == ["RF_FEVER", "RF_HEART", "RF_CHEST_PAIN"]


def test_self_harm_uses_crisis_line(session, fake_pager):
    cid = checkin_for(session, "pat_ana").id
    to_symptoms(session, cid)
    r = tool(session, "report_red_flag", cid, red_flag_id="RF_SELF_HARM", verbatim_quote="ya no quiero vivir")
    assert r["next"]["action"] == "close"
    assert r["next"]["say"].startswith(content.script("crisis_line", "es"))


def test_wrong_person_closes_without_health_info(session, fake_pager):
    cid = checkin_for(session, "pat_james").id
    r = tool(session, "record_answer", cid, item_code="IDENTITY", option_code="no", verbatim_quote="wrong number")
    assert r["next"] == {"action": "close", "item_code": None, "say": content.script("wrong_person_close", "en")}


def test_consent_later_creates_callback(session, fake_pager):
    cid = checkin_for(session, "pat_jorge").id
    tool(session, "record_answer", cid, item_code="IDENTITY", option_code="yes", verbatim_quote="sí")
    r = tool(session, "record_answer", cid, item_code="CALL_CONSENT", option_code="later", verbatim_quote="llámenme más tarde")
    assert r["next"]["action"] == "close" and r["next"]["say"] == content.script("consent_later", "es")
    e = escs(session, cid)
    assert [x.level for x in e] == ["callback"] and not fake_pager.sent


@pytest.mark.req("REQ-007")
def test_medical_question_defers_and_creates_task(session, fake_pager):
    cid = checkin_for(session, "pat_james").id
    r0 = to_symptoms(session, cid)
    r = tool(session, "request_human", cid, reason="medical_question", verbatim_quote="Should I stop my blood pressure pills?")
    assert r["next"]["action"] == "ask"
    assert r["next"]["say"] == f"{content.script('deferral_medical', 'en')} {content.question_say(r0['next']['item_code'], 'en')}"
    tasks = session.exec(select(DraftEntry).where(DraftEntry.checkin_id == cid, DraftEntry.kind == "NURSE_TASK")).all()
    assert tasks[0].payload["category"] == "medical_question"
    assert [x.level for x in escs(session, cid)] == ["callback"]


def test_wants_person_closes(session, fake_pager):
    cid = checkin_for(session, "pat_walter").id
    r = tool(session, "request_human", cid, reason="wants_person", verbatim_quote="get me a person")
    assert r["next"]["action"] == "close" and r["next"]["say"] == content.script("wants_person_close", "en")


def test_caregiver_allowed_and_not_allowed(session, fake_pager):
    walter = checkin_for(session, "pat_walter").id
    r = tool(session, "set_speaker", walter, speaker="caregiver", relation="son")
    assert r["next"]["item_code"] == "CALL_CONSENT"
    assert r["next"]["say"] == content.script("caregiver_allowed", "en", caregiver_name="Mike", patient_first_name="Walter")
    jorge = checkin_for(session, "pat_jorge").id
    r = tool(session, "set_speaker", jorge, speaker="caregiver", relation="wife")
    assert r["next"]["action"] == "close"
    assert r["next"]["say"] == content.script("caregiver_not_allowed", "es", patient_first_name="Jorge")


def test_correction_of_earlier_answer(session, fake_pager):
    cid = checkin_for(session, "pat_james").id
    to_symptoms(session, cid)
    tool(session, "record_answer", cid, item_code="DIARRHEA_FREQ", option_code="sometimes", verbatim_quote="sometimes")
    tool(session, "record_answer", cid, item_code="DIARRHEA_STOOLS_PER_DAY", numeric_value=3, verbatim_quote="three")
    r = tool(session, "record_answer", cid, item_code="STOOL_BLOOD", option_code="no", verbatim_quote="no")
    assert r["next"]["item_code"] == "NAUSEA_FREQ" and not fake_pager.sent
    # correction: actually 9 a day -> urgent, current question (a symptom) is dropped
    r = tool(session, "record_answer", cid, item_code="DIARRHEA_STOOLS_PER_DAY", numeric_value=9, verbatim_quote="actually nine")
    assert r["escalated"] and len(fake_pager.sent) == 1
    assert r["next"]["item_code"] == "MEDS_NEW"


def test_unexpected_item_reasks_current(session, fake_pager):
    cid = checkin_for(session, "pat_james").id
    to_symptoms(session, cid)
    r = tool(session, "record_answer", cid, item_code="FATIGUE_SEV", option_code="mild", verbatim_quote="a bit tired")
    assert r["ok"] is False and r["error"] == "unexpected_item" and r["next"]["item_code"] == "DIARRHEA_FREQ"


@pytest.mark.req("REQ-003")
def test_every_say_is_approved_and_filled(session, fake_pager):
    """Walk a full no-symptom call in both languages; no say may contain an unfilled placeholder."""
    for pid in ("pat_james", "pat_ana"):
        cid = checkin_for(session, pid).id
        r = to_symptoms(session, cid)
        steps = 0
        while r["next"]["action"] == "ask" and steps < 40:
            assert not content.find_unfilled(r["next"]["say"]), r["next"]["say"]
            code = r["next"]["item_code"]
            opts = content.item_options(code)
            opt = next(o for o in ("never", "none", "no") if o in opts) if len(opts) > 1 else None
            r = tool(session, "record_answer", cid, item_code=code, option_code=opt, verbatim_quote="no")
            steps += 1
        assert r["next"]["action"] == "close"
        assert not escs(session, cid) and not fake_pager.sent
