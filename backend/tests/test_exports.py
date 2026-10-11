"""B14 / CAPA-001: parseable, consistent exports and a tidy SAE narrative (docs/03 §6.5, REQ-020).

Before the fix, line 1 of ae.csv/cm.csv was a `#` comment that a standard CSV reader took for the header, `AEOUT`
said UNKNOWN while the SAE report said "not recovered", and the narrative showed "..", ".;" and a nested
parenthesis in the drug-class string.
"""

import csv
import io

import pytest

from app.config import get_settings
from app.services import llm, replay
from app.services.export import AE_COLUMNS, CM_COLUMNS, OUT, outcome_of
from app.services.sae import tidy_punctuation
from tests.conftest import COORD, INVESTIGATOR

AE_NOTE = ("CTCAE v5.0; synthetic data; AEDECOD/AEBODSYS coded downstream by licensed sponsor; "
           "ORIGIN is a sponsor-defined column")
CM_NOTE = "synthetic data; CMDECOD empty: WHODrug coding is licensed and done downstream"
SERIOUS = {"is_serious": True, "seriousness_criteria": ["hospitalization"], "relatedness": "possibly_related"}


def _max_paren_depth(text: str) -> int:
    depth = deepest = 0
    for ch in text:
        if ch == "(":
            depth += 1
            deepest = max(deepest, depth)
        elif ch == ")":
            depth = max(depth - 1, 0)
    return deepest


def _assert_tidy(text: str) -> None:
    for bad in ("..", ".;", "(("):
        assert bad not in text, f"{bad!r} in {text!r}"
    assert _max_paren_depth(text) <= 1, f"nested parentheses in {text!r}"


def _rosa_drafts(client, session) -> tuple[str, list[dict]]:
    cid = replay.start(session, "rosa_es_urgent", speed=10_000, run_async=False)
    return cid, client.get("/api/drafts", params={"checkin_id": cid}).json()


def _serious_ae(client, draft_id: str) -> dict:
    """Confirm the AE, assess it serious as the investigator, return the full SAE report."""
    assert client.post(f"/api/drafts/{draft_id}/confirm", json={}, headers=COORD).status_code == 200
    r = client.post(f"/api/drafts/{draft_id}/investigator", json=SERIOUS, headers=INVESTIGATOR)
    assert r.status_code == 200, r.text
    return client.get(f"/api/sae/{r.json()['sae_report']['id']}").json()


@pytest.mark.req("REQ-020")
def test_exports_start_with_header_and_carry_origin(client, session, fake_pager):
    cid, drafts = _rosa_drafts(client, session)
    for d in drafts:  # confirm both AEs and the medication
        assert client.post(f"/api/drafts/{d['id']}/confirm", json={}, headers=COORD).status_code == 200

    r = client.get("/api/export/ae.csv")
    assert r.status_code == 200 and r.headers["x-bv-note"] == AE_NOTE
    assert r.text.splitlines()[0] == ",".join(AE_COLUMNS)
    assert not any(line.startswith("#") for line in r.text.splitlines())
    reader = csv.DictReader(io.StringIO(r.text))
    assert reader.fieldnames == AE_COLUMNS
    assert (reader.fieldnames[0], reader.fieldnames[-1]) == ("STUDYID", "ORIGIN")
    rows = list(reader)
    assert sorted(x["AETERM"] for x in rows) == ["Diarrhea", "Dizziness"]
    assert all(x["ORIGIN"] == "between_visits" for x in rows)
    assert all(x["STUDYID"] == "NCT02760498" and x["AESPID"] == cid for x in rows)

    r = client.get("/api/export/cm.csv")
    assert r.status_code == 200 and r.headers["x-bv-note"] == CM_NOTE
    assert not any(line.startswith("#") for line in r.text.splitlines())
    reader = csv.DictReader(io.StringIO(r.text))
    assert reader.fieldnames == CM_COLUMNS and reader.fieldnames[0] == "STUDYID"
    meds = [d["payload"]["medication_name"] for d in drafts if d["kind"] == "CM"]
    assert len(meds) == 1 and [x["CMTRT"] for x in reader] == meds


@pytest.mark.req("REQ-020")
def test_export_headers_exposed_to_the_dashboard(client):
    origin = get_settings().cors_origin_list[0]
    for path in ("/api/export/ae.csv", "/api/export/cm.csv"):
        r = client.get(path, headers={"Origin": origin})
        exposed = {h.strip().lower() for h in r.headers.get("access-control-expose-headers", "").split(",")}
        assert {"x-bv-note", "content-disposition"} <= exposed, r.headers


@pytest.mark.req("REQ-020")
@pytest.mark.parametrize(
    ("patch", "aeout"),
    [
        pytest.param({}, "NOT RECOVERED/NOT RESOLVED", id="ongoing-no-outcome"),
        pytest.param({"outcome": "recovering"}, "RECOVERING/RESOLVING", id="known-outcome"),
        pytest.param({"outcome": "recovered", "ongoing": True}, "RECOVERED/RESOLVED", id="outcome-beats-ongoing"),
        pytest.param({"ongoing": False}, "UNKNOWN", id="not-ongoing-no-outcome"),
    ],
)
def test_aeout_agrees_with_sae_outcome(client, session, fake_pager, patch, aeout):
    _, drafts = _rosa_drafts(client, session)
    ae = next(d for d in drafts if d["kind"] == "AE" and d["payload"].get("term") == "Diarrhea")
    if patch:
        assert client.patch(f"/api/drafts/{ae['id']}", json={"payload": patch}, headers=COORD).status_code == 200
    sae = _serious_ae(client, ae["id"])

    rows = list(csv.DictReader(io.StringIO(client.get("/api/export/ae.csv").text)))
    row = next(x for x in rows if x["AETERM"] == "Diarrhea")
    assert row["AEOUT"] == aeout
    assert row["AEOUT"] == OUT[sae["payload"]["reaction"]["outcome"]]  # one helper, one answer
    assert row["ORIGIN"] == "between_visits"


@pytest.mark.req("REQ-020")
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param({"outcome": "recovered"}, "recovered", id="recovered"),
        pytest.param({"outcome": "recovering", "ongoing": True}, "recovering", id="known-beats-ongoing"),
        pytest.param({"outcome": "recovered_with_sequelae"}, "recovered_with_sequelae", id="sequelae"),
        pytest.param({"outcome": "fatal"}, "fatal", id="fatal"),
        pytest.param({"outcome": "unknown", "ongoing": True}, "unknown", id="explicit-unknown"),
        pytest.param({"ongoing": True}, "not_recovered", id="ongoing"),
        pytest.param({"ongoing": False}, "unknown", id="not-ongoing"),
        pytest.param({}, "unknown", id="empty"),
        pytest.param(None, "unknown", id="none"),
        pytest.param({"outcome": None, "ongoing": True}, "not_recovered", id="null-outcome-ongoing"),
        pytest.param({"outcome": "better", "ongoing": False}, "unknown", id="unknown-key"),
        pytest.param({"ongoing": "yes"}, "unknown", id="ongoing-not-bool"),
    ],
)
def test_outcome_of(payload, expected):
    assert outcome_of(payload) == expected
    assert OUT[outcome_of(payload)]


@pytest.mark.req("REQ-020")
def test_sae_narrative_punctuation(client, session, fake_pager):
    _, drafts = _rosa_drafts(client, session)
    ae = next(d for d in drafts if d["kind"] == "AE" and d["payload"].get("term") == "Diarrhea")
    assert ".;" in ae["payload"]["verbatim_en"]  # the joined patient quotes that caused the defect
    sae = _serious_ae(client, ae["id"])

    _assert_tidy(sae["narrative_ai_draft"])
    assert "Patient report: Almost all the time, honestly. Like seven or eight times" in sae["narrative_ai_draft"]
    assert "Outcome at time of report: not recovered." in sae["narrative_ai_draft"]
    _assert_tidy(sae["payload"]["reaction"]["description"])
    drug = sae["payload"]["suspect_product"]["description"]
    _assert_tidy(drug)
    assert drug.startswith("Study drug (anti-PD-1") and drug.endswith(")")


@pytest.mark.req("REQ-020")
def test_llm_narrative_is_tidied(client, session, fake_pager, monkeypatch):
    """Whatever drafts the narrative (template, Gemini or Claude), the stored AI draft is tidied."""
    messy = ("Subject 101-007 reported diarrhea.. Study drug (anti-PD-1 monoclonal antibody (immunotherapy)).; "
             "Patient said: like seven or eight times... normally once.")
    monkeypatch.setattr(llm, "draft_narrative", lambda payload, quotes: messy)
    _, drafts = _rosa_drafts(client, session)
    ae = next(d for d in drafts if d["kind"] == "AE" and d["payload"].get("term") == "Diarrhea")
    narrative = _serious_ae(client, ae["id"])["narrative_ai_draft"]
    _assert_tidy(narrative)
    assert narrative == ("Subject 101-007 reported diarrhea. Study drug (anti-PD-1 monoclonal antibody, immunotherapy). "
                         "Patient said: like seven or eight times… normally once.")


@pytest.mark.req("REQ-020")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("once..", "once.", id="double-period"),
        pytest.param("honestly.; Like", "honestly. Like", id="period-semicolon"),
        pytest.param("really?; no", "really? no", id="question-semicolon"),
        pytest.param("eight times... normally", "eight times… normally", id="ellipsis"),
        pytest.param("I go once.... Then", "I go once… Then", id="long-ellipsis"),
        pytest.param("times….", "times…", id="ellipsis-then-period"),
        pytest.param("Study drug (anti-PD-1 monoclonal antibody (immunotherapy))",
                     "Study drug (anti-PD-1 monoclonal antibody, immunotherapy)", id="nested-parens"),
        pytest.param("antidiarrheal (over the counter); grade 3.", "antidiarrheal (over the counter); grade 3.",
                     id="unchanged"),
        pytest.param("CTCAE v5.0 grade 3. R.M.", "CTCAE v5.0 grade 3. R.M.", id="decimals-and-initials"),
        pytest.param("", "", id="empty"),
        pytest.param(None, None, id="none"),
    ],
)
def test_tidy_punctuation(text, expected):
    assert tidy_punctuation(text) == expected


@pytest.mark.req("REQ-020")
def test_draft_origin(client, session, fake_pager):
    cid, drafts = _rosa_drafts(client, session)
    assert drafts and all(d["origin"] == "between_visits" for d in drafts)
    detail = client.get(f"/api/checkins/{cid}").json()
    assert detail["drafts"] and all(d["origin"] == "between_visits" for d in detail["drafts"])
    confirmed = client.post(f"/api/drafts/{drafts[0]['id']}/confirm", json={}, headers=COORD).json()
    assert confirmed["origin"] == "between_visits"
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    draft_schema = schema.get("DraftOut") or schema["DraftOut-Output"]
    assert draft_schema["properties"]["origin"]["const"] == "between_visits"
