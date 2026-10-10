"""B4 acceptance: replay Rosa's tool calls over HTTP and check every `say`, the grade, the page and the queue."""

import pytest
from sqlmodel import select

from app import content
from app.models import Answer, CheckIn, Escalation, Finding
from tests.conftest import SECRET

LANG = "es"
VARS = {"study_team_name": "el equipo de investigación de Hillside", "patient_first_name": "Rosa", "caregiver_name": "Lucía"}


def S(key: str) -> str:
    return content.script(key, LANG, **VARS)


def Q(code: str) -> str:
    return content.question_say(code, LANG, "extra_time", **VARS)


@pytest.fixture
def rosa_checkin(session) -> str:
    c = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_rosa")).one()
    return c.id


def call(client, tool: str, body: dict, headers=SECRET) -> dict:
    r = client.post(f"/agent/tools/{tool}", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.req("REQ-003")
@pytest.mark.req("REQ-005")
@pytest.mark.req("REQ-013")
def test_rosa_flow(client, session, fake_pager, rosa_checkin):
    cid = rosa_checkin
    body = lambda **kw: {"checkin_id": cid, "conversation_id": "conv_test_rosa", **kw}  # noqa: E731

    r = call(client, "record_answer", body(item_code="IDENTITY", option_code="yes", verbatim_quote="Sí, soy yo."))
    assert r["next"] == {"action": "ask", "item_code": "CALL_CONSENT", "say": S("consent_question")}

    r = call(client, "record_answer", body(item_code="CALL_CONSENT", option_code="yes", verbatim_quote="Sí, está bien."))
    assert r["next"]["item_code"] == "DIARRHEA_FREQ"
    assert r["next"]["say"] == f"{S('intro_questions')} {Q('DIARRHEA_FREQ')}"

    # invalid option re-asks the same item with approved wording
    r = call(client, "record_answer", body(item_code="DIARRHEA_FREQ", option_code="a_lot", verbatim_quote="Mucho"))
    assert r["ok"] is False and r["error"] == "invalid_option"
    assert r["next"]["item_code"] == "DIARRHEA_FREQ"
    assert r["next"]["say"] == content.script("reask_options", LANG, options=content.options_phrase("DIARRHEA_FREQ", LANG))

    r = call(client, "record_answer", body(item_code="DIARRHEA_FREQ", option_code="almost_always",
                                           verbatim_quote="Casi todo el tiempo, la verdad."))
    assert r["next"] == {"action": "ask", "item_code": "DIARRHEA_STOOLS_PER_DAY", "say": Q("DIARRHEA_STOOLS_PER_DAY")}
    assert not fake_pager.sent

    r = call(client, "record_answer", body(item_code="DIARRHEA_STOOLS_PER_DAY", numeric_value=8, unit="per_day",
                                           verbatim_quote="Como siete u ocho veces... normalmente voy una."))
    # urgent: page went out before the tool returned; queue jumps to MEDS_NEW
    assert r["escalated"] is True
    assert len(fake_pager.sent) == 1
    assert r["next"] == {"action": "ask", "item_code": "MEDS_NEW", "say": f"{S('urgent_line')} {Q('MEDS_NEW')}"}
    msg = fake_pager.sent[0]
    assert "101-007" in msg.title and "Rosa" not in msg.text and "Méndez" not in msg.text
    assert "7 stools a day above baseline" in msg.text and "interpreter" in msg.text

    session.expire_all()
    f = session.exec(select(Finding).where(Finding.checkin_id == cid, Finding.term == "Diarrhea")).one()
    assert (f.provisional_grade, f.rule_id, f.escalation_level) == (3, "CTCAE5_DIARRHEA_G3", "urgent")
    assert f.red_flag_ids == ["RF_DIARRHEA_SEVERE"]

    # a second urgent red flag is added to the same page: no second page
    r = call(client, "report_red_flag", body(red_flag_id="RF_DEHYDRATION", verbatim_quote="y esta mañana me mareé al levantarme."))
    assert r["next"] == {"action": "ask", "item_code": "MEDS_NEW", "say": f"{S('added_to_page')} {Q('MEDS_NEW')}"}
    assert len(fake_pager.sent) == 1
    session.expire_all()
    escs = session.exec(select(Escalation).where(Escalation.checkin_id == cid)).all()
    assert len(escs) == 1 and escs[0].level == "urgent"
    assert escs[0].red_flag_ids == ["RF_DIARRHEA_SEVERE", "RF_DEHYDRATION"]

    r = call(client, "record_answer", body(item_code="MEDS_NEW", option_code="yes", verbatim_quote="Sí, ayer tomé Imodium de la farmacia."))
    assert r["next"] == {"action": "ask", "item_code": "MEDS_DETAIL", "say": Q("MEDS_DETAIL")}
    r = call(client, "record_medication_change", body(description="Imodium (loperamide) from the pharmacy, started yesterday",
                                                       verbatim_quote="El Imodium, lo empecé ayer."))
    assert r["next"] == {"action": "ask", "item_code": "CARE_VISIT", "say": Q("CARE_VISIT")}
    r = call(client, "record_answer", body(item_code="CARE_VISIT", option_code="no", verbatim_quote="No."))
    assert r["next"] == {"action": "ask", "item_code": "ANYTHING_ELSE", "say": Q("ANYTHING_ELSE")}
    r = call(client, "record_answer", body(item_code="ANYTHING_ELSE", option_code="no", verbatim_quote="No, nada más. Gracias."))
    assert r["next"] == {"action": "close", "item_code": None, "say": S("closing_after_escalation")}

    # every say is free of unfilled placeholders, and the live page shows everything
    detail = client.get(f"/api/checkins/{cid}").json()
    assert detail["checkin"]["status"] == "in_progress"
    assert detail["escalations"][0]["status"] == "open"
    assert [d["kind"] for d in detail["drafts"]] == ["CM"]
    assert detail["drafts"][0]["evidence"][0]["quote"] == "El Imodium, lo empecé ayer."
    stools = session.exec(select(Answer).where(Answer.checkin_id == cid, Answer.item_code == "DIARRHEA_STOOLS_PER_DAY")).one()
    assert stools.numeric_value == 8 and stools.quote_lang == "es"


@pytest.mark.req("REQ-013")
def test_missing_or_bad_secret_is_401(client, rosa_checkin):
    b = {"checkin_id": rosa_checkin, "item_code": "IDENTITY", "option_code": "yes", "verbatim_quote": "yes"}
    assert client.post("/agent/tools/record_answer", json=b).status_code == 401
    assert client.post("/agent/tools/record_answer", json=b, headers={"X-BV-Tool-Secret": "nope"}).status_code == 401
    assert client.post("/agent/tools/report_red_flag", json={"red_flag_id": "RF_FEVER"}).status_code == 401


def test_unknown_checkin_closes(client):
    r = call(client, "record_answer", {"checkin_id": "unknown", "item_code": "IDENTITY", "option_code": "yes", "verbatim_quote": "hi"})
    assert r["next"]["action"] == "close" and r["ok"] is False
