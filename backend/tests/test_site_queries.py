"""B18 (docs/03 §5.4, §5.6, §5.7): the site query flow, against the B16b fixtures (`site_signal_fixtures`).

REQ-027 human-approved, audited site queries: a query reaches the mock site inbox only after CRA approval; draft,
edit, approve, answer and close each write exactly one AuditEvent with the §5.7 action and before/after; the text
comes from data/site_queries.json and carries subject IDs only (no patient name, no banned phrase).
"""

import re
from typing import Any

import pytest
from sqlmodel import select

from app import content
from app.models import AuditEvent, Patient, SiteQuery
from app.services import site_queries
from tests.conftest import COORD, INVESTIGATOR

pytestmark = pytest.mark.req("REQ-027")

CRA = {"X-BV-User": "Sam Rivera", "X-BV-Role": "cra"}
SPONSOR = {"X-BV-User": "Sponsor reviewer", "X-BV-Role": "sponsor"}
TEMPLATE = "SQ_UNMATCHED_EPISODES"
ACTIONS = ["site_query.drafted", "site_query.edited", "site_query.approved", "site_query.answered",
           "site_query.closed"]


def error_code(r) -> str:  # noqa: ANN001
    return r.json()["error"]["code"]


def draft(client, site_id: str = "112", episode_ids: list[str] | None = None, **extra: Any):  # noqa: ANN001, ANN201
    body = {"site_id": site_id, "episode_ids": episode_ids or ["ep_112_23", "ep_112_17"], "template_id": TEMPLATE,
            **extra}
    return client.post("/api/site-queries", json=body, headers=CRA)


def sent_query(client) -> str:  # noqa: ANN001
    r = draft(client)
    assert r.status_code == 201, r.text
    qid = r.json()["id"]
    assert client.post(f"/api/site-queries/{qid}/approve", json={}, headers=CRA).status_code == 200
    return qid


def audit_rows(session, query_id: str) -> list[AuditEvent]:  # noqa: ANN001
    session.expire_all()
    return list(session.exec(select(AuditEvent).where(AuditEvent.entity_id == query_id)
                             .order_by(AuditEvent.seq)).all())  # type: ignore[arg-type]


# ---- the full flow and its audit trail ---------------------------------------------------------------------


def test_full_flow_writes_exactly_the_five_audit_actions(client, session, site_signal_fixtures) -> None:
    r = draft(client)
    assert r.status_code == 201, r.text
    q = r.json()
    qid = q["id"]
    assert re.fullmatch(r"sq_[A-Z2-7]{10}", qid)
    assert q["status"] == "draft" and q["edited"] is False and q["created_by"] == "Sam Rivera"
    assert q["signal_run_id"] == "sr_committed" and q["data_origin"] == "SIMULATED"
    assert q["episode_ids"] == ["ep_112_23", "ep_112_17"] and q["subject_ids"] == ["112-014", "112-020"]
    original = q["body_en"]

    edited = "Site 112: please review the source documents for 112-014 and 112-020 and tell us what you find."
    r = client.patch(f"/api/site-queries/{qid}", json={"body_en": edited, "note": "Shortened"}, headers=CRA)
    assert r.status_code == 200, r.text
    assert r.json()["edited"] is True and r.json()["body_en"] == edited

    r = client.post(f"/api/site-queries/{qid}/approve", json={}, headers=CRA)
    assert r.status_code == 200, r.text
    approved = r.json()
    assert approved["status"] == "sent" and approved["approved_by"] == "Sam Rivera" and approved["approved_at"]

    r = client.post(f"/api/site-queries/{qid}/respond",
                    json={"response_code": "recorded_as_medical_history", "note": "Baseline at screening"}, headers=COORD)
    assert r.status_code == 200, r.text
    answered = r.json()
    assert answered["status"] == "answered" and answered["responded_by"] == "Jess Kim"
    assert answered["response_label_en"] == next(
        c["label_en"] for c in content.site_queries()["response_codes"] if c["code"] == "recorded_as_medical_history")
    assert answered["response_note"] == "Baseline at screening"

    r = client.post(f"/api/site-queries/{qid}/close", json={"note": "Explained; no entry needed"}, headers=CRA)
    assert r.status_code == 200, r.text
    closed = r.json()
    assert closed["status"] == "closed" and closed["closed_by"] == "Sam Rivera"
    assert closed["closure_note"] == "Explained; no entry needed"

    rows = audit_rows(session, qid)
    assert [a.action for a in rows] == ACTIONS
    assert all(a.entity_type == "SiteQuery" for a in rows)
    assert [(a.actor, a.role) for a in rows] == [("Sam Rivera", "cra")] * 3 + [("Jess Kim", "coordinator"),
                                                                               ("Sam Rivera", "cra")]
    drafted, edit, approve, answer, close = rows
    assert drafted.before is None
    assert drafted.after == {"site_id": "112", "signal_run_id": "sr_committed", "template_id": TEMPLATE,
                             "episode_ids": ["ep_112_23", "ep_112_17"], "status": "draft"}
    assert (edit.before, edit.after, edit.note) == ({"body_en": original}, {"body_en": edited}, "Shortened")
    assert approve.before == {"status": "draft"} and approve.after["status"] == "sent"
    assert approve.after["approved_at"].startswith(approved["approved_at"][:19])
    assert (answer.before, answer.after, answer.note) == (
        {"status": "sent"}, {"status": "answered", "response_code": "recorded_as_medical_history"},
        "Baseline at screening")
    assert (close.before, close.after, close.note) == ({"status": "answered"}, {"status": "closed"},
                                                       "Explained; no entry needed")
    assert client.get("/api/audit/verify").json()["ok"] is True

    detail = client.get(f"/api/site-queries/{qid}", headers=CRA).json()
    assert [a["action"] for a in detail["audit"]] == ACTIONS


def test_wrong_state_is_409_and_writes_nothing(client, session, site_signal_fixtures) -> None:
    qid = draft(client).json()["id"]
    assert error_code(client.post(f"/api/site-queries/{qid}/respond", json={"response_code": "other"},
                                  headers=COORD)) == "site_query_not_found"  # a draft is hidden from the coordinator
    assert error_code(client.post(f"/api/site-queries/{qid}/close", json={}, headers=CRA)) == "not_answered"
    assert client.post(f"/api/site-queries/{qid}/approve", headers=CRA).status_code == 200  # no body is fine
    r = client.post(f"/api/site-queries/{qid}/approve", json={}, headers=CRA)
    assert (r.status_code, error_code(r)) == (409, "not_draft")
    r = client.patch(f"/api/site-queries/{qid}", json={"body_en": "Changed after sending"}, headers=CRA)
    assert (r.status_code, error_code(r)) == (409, "not_draft")
    r = client.post(f"/api/site-queries/{qid}/close", json={}, headers=CRA)
    assert (r.status_code, error_code(r)) == (409, "not_answered")
    r = client.post(f"/api/site-queries/{qid}/respond", json={"response_code": "maybe"}, headers=COORD)
    assert (r.status_code, error_code(r)) == (422, "invalid_response_code")
    assert client.post(f"/api/site-queries/{qid}/respond", json={"response_code": "other"},
                       headers=COORD).status_code == 200
    r = client.post(f"/api/site-queries/{qid}/respond", json={"response_code": "other"}, headers=COORD)
    assert (r.status_code, error_code(r)) == (409, "not_sent")
    assert client.post(f"/api/site-queries/{qid}/close", headers=CRA).status_code == 200
    assert [a.action for a in audit_rows(session, qid)] == ["site_query.drafted", "site_query.approved",
                                                            "site_query.answered", "site_query.closed"]
    r = client.get("/api/site-queries/sq_AAAAAAAAAA", headers=CRA)
    assert (r.status_code, error_code(r)) == (404, "site_query_not_found")


# ---- the mock site inbox (coordinator) ----------------------------------------------------------------------


def test_coordinator_inbox_excludes_drafts_and_includes_sent_queries(client, site_signal_fixtures) -> None:
    draft_id = draft(client).json()["id"]
    sent_id = sent_query(client)

    inbox = client.get("/api/site-queries", headers=COORD).json()
    assert [q["id"] for q in inbox] == [sent_id]
    assert inbox[0]["site_id"] == "112" and inbox[0]["status"] == "sent"
    assert [q["id"] for q in client.get("/api/site-queries", params={"site_id": "112"}, headers=COORD).json()] == [
        sent_id]
    assert client.get("/api/site-queries", params={"site_id": "107"}, headers=COORD).json() == []
    assert client.get("/api/site-queries", params={"status": "draft"}, headers=COORD).json() == []
    assert [q["id"] for q in client.get("/api/site-queries", params={"status": "draft,sent"},
                                        headers=COORD).json()] == [sent_id]
    assert client.get("/api/site-queries", headers={"X-BV-User": "Jess Kim"}).json() == inbox  # missing role

    r = client.get(f"/api/site-queries/{draft_id}", headers=COORD)
    assert (r.status_code, error_code(r)) == (404, "site_query_not_found")

    for who in (CRA, SPONSOR):
        assert {q["id"] for q in client.get("/api/site-queries", headers=who).json()} == {draft_id, sent_id}
        assert [q["id"] for q in client.get("/api/site-queries", params={"status": "draft"}, headers=who).json()] == [
            draft_id]
        assert client.get(f"/api/site-queries/{draft_id}", headers=who).status_code == 200
    r = client.get("/api/site-queries", params={"status": "open"}, headers=CRA)
    assert (r.status_code, error_code(r)) == (422, "validation_error")
    assert client.get("/api/site-queries", headers=INVESTIGATOR).status_code == 403


def test_coordinator_sees_answered_and_closed_at_every_site(client, site_signal_fixtures) -> None:
    answered = sent_query(client)
    assert client.post(f"/api/site-queries/{answered}/respond", json={"response_code": "entered_now"},
                       headers=COORD).status_code == 200
    r = draft(client, site_id="107", episode_ids=["ep_107_11"])
    closed = r.json()["id"]
    for path, body, who in ((f"/api/site-queries/{closed}/approve", {}, CRA),
                            (f"/api/site-queries/{closed}/respond", {"response_code": "other", "note": "x"}, COORD),
                            (f"/api/site-queries/{closed}/close", {}, CRA)):
        assert client.post(path, json=body, headers=who).status_code == 200
    inbox = {q["id"]: (q["site_id"], q["status"]) for q in client.get("/api/site-queries", headers=COORD).json()}
    assert inbox == {answered: ("112", "answered"), closed: ("107", "closed")}


def test_coordinator_detail_has_no_patient_quotes(client, site_signal_fixtures) -> None:
    qid = sent_query(client)
    coord = client.get(f"/api/site-queries/{qid}", headers=COORD).json()
    cra = client.get(f"/api/site-queries/{qid}", headers=CRA).json()
    assert [e["episode_id"] for e in coord["episodes"]] == ["ep_112_23", "ep_112_17"]
    assert all(e["evidence"] is None for e in coord["episodes"])
    assert all(e["evidence"]["quote"] and e["evidence"]["source"] == "synthetic" for e in cra["episodes"])
    assert all(e["data_origin"] == "SIMULATED" for e in cra["episodes"])
    assert [a["action"] for a in coord["audit"]] == ["site_query.drafted", "site_query.approved"]


# ---- eligibility -----------------------------------------------------------------------------------------


def test_low_coverage_site_unmatched_is_citable_and_pending_is_not(client, site_signal_fixtures) -> None:
    """Site 103 is not computed for low_coverage; its unmatched episode can be cited, its pending one cannot."""
    sites = {s["site_id"]: s for s in client.get("/api/sites", headers=CRA).json()["sites"]}
    assert (sites["103"]["tier"], sites["103"]["not_computed_reason"]) == ("not_computed", "low_coverage")
    r = draft(client, site_id="103", episode_ids=["ep_103_04"])
    assert r.status_code == 201, r.text
    assert r.json()["subject_ids"] == ["103-005"]
    r = draft(client, site_id="103", episode_ids=["ep_103_06"])
    assert (r.status_code, error_code(r)) == (422, "episode_not_eligible")
    assert "ep_103_06" in r.json()["error"]["message"] and "pending" in r.json()["error"]["message"]


@pytest.mark.parametrize(("site_id", "episode_ids", "status", "code"), [
    ("112", ["ep_112_05"], 422, "episode_not_eligible"),  # matched
    ("112", ["ep_112_18"], 422, "episode_not_eligible"),  # paged
    ("112", ["ep_112_30"], 422, "episode_not_eligible"),  # pending
    ("112", ["ep_112_17", "ep_107_11"], 422, "episode_not_eligible"),  # unmatched, but at another site
    ("112", ["ep_112_99"], 404, "episode_not_found"),
    ("999", ["ep_112_17"], 404, "site_not_found"),
    ("112", [], 422, "validation_error"),
])
def test_ineligible_requests(client, session, site_signal_fixtures, site_id, episode_ids, status, code) -> None:
    r = client.post("/api/site-queries", json={"site_id": site_id, "episode_ids": episode_ids, "template_id": TEMPLATE},
                    headers=CRA)
    assert (r.status_code, error_code(r)) == (status, code), r.text
    assert session.exec(select(SiteQuery)).all() == []
    assert session.exec(select(AuditEvent).where(AuditEvent.entity_type == "SiteQuery")).all() == []


def test_only_the_committed_run_and_known_templates(client, site_signal_fixtures) -> None:
    r = draft(client, signal_run_id="sr_ABCDEFGHJK")
    assert (r.status_code, error_code(r)) == (422, "run_not_queryable")
    assert draft(client, signal_run_id="sr_committed").status_code == 201
    r = client.post("/api/site-queries", json={"site_id": "112", "episode_ids": ["ep_112_17"],
                                               "template_id": "SQ_NOPE"}, headers=CRA)
    assert (r.status_code, error_code(r)) == (404, "template_not_found")


def test_site_signal_unavailable_is_503(client, site_signal_out, tmp_path) -> None:
    site_signal_out(tmp_path / "missing")
    r = draft(client)
    assert (r.status_code, error_code(r)) == (503, "site_signal_unavailable")


# ---- wording: template only, subject IDs only, no banned phrase -----------------------------------------------


def test_rendered_text_is_the_template_with_ids_only(client, session, site_signal_fixtures) -> None:
    q = draft(client).json()
    t = content.site_queries()["templates"][TEMPLATE]
    body = q["body_en"]
    assert q["title_en"] == t["title_en"]
    assert "{" not in body and "}" not in body
    low = body.lower()
    assert [b for b in content.site_queries()["banned_phrases_en"] if b.lower() in low] == []
    # one episode line per cited episode, ordered by episode date: ep_112_23 (07-21) before ep_112_17 (08-14)
    first = t["episode_line_en"].format(subject_id="112-020", term="Dyspnea", episode_date="2026-07-21", grade=2)
    second = t["episode_line_en"].format(subject_id="112-014", term="Diarrhea", episode_date="2026-08-14", grade=2)
    assert body == t["body_en"].format(site_id="112", episode_lines=f"{first}\n{second}")
    folded = site_queries._fold(body)
    names = {site_queries._fold(n) for p in session.exec(select(Patient)).all() for n in (p.first_name, p.last_name)}
    assert len(names) >= 10
    assert [n for n in names if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", folded)] == []


@pytest.mark.parametrize("text", [
    "Please check the source documents for Rosa.",
    "please check ROSA's notes",
    "Subject 101-007 (Mendez) reported diarrhea.",  # accents folded: matches the seeded last name
])
def test_patch_with_a_patient_name_is_contains_identifier(client, session, site_signal_fixtures, text) -> None:
    qid = draft(client).json()["id"]
    r = client.patch(f"/api/site-queries/{qid}", json={"body_en": text}, headers=CRA)
    assert (r.status_code, error_code(r)) == (422, "contains_identifier")
    assert "Rosa" not in r.json()["error"]["message"] and "Mendez" not in r.json()["error"]["message"]
    session.expire_all()
    assert session.get(SiteQuery, qid).edited is False
    assert [a.action for a in audit_rows(session, qid)] == ["site_query.drafted"]


def test_names_match_whole_words_only(client, session, site_signal_fixtures) -> None:
    names = {n for p in session.exec(select(Patient)).all() for n in (p.first_name, p.last_name)}
    assert "Rosa" in names
    qid = draft(client).json()["id"]
    r = client.patch(f"/api/site-queries/{qid}", json={"body_en": "Rosalind reviewed the rosary notes."},
                     headers=CRA)
    assert r.status_code == 200, r.text


def test_patch_with_a_banned_phrase_or_empty_text(client, session, site_signal_fixtures) -> None:
    qid = draft(client).json()["id"]
    for phrase in content.site_queries()["banned_phrases_en"]:
        r = client.patch(f"/api/site-queries/{qid}", json={"body_en": f"Site 112: {phrase.upper()} here."},
                         headers=CRA)
        assert (r.status_code, error_code(r)) == (422, "banned_phrase"), phrase
    r = client.patch(f"/api/site-queries/{qid}", json={"body_en": "   "}, headers=CRA)
    assert (r.status_code, error_code(r)) == (422, "validation_error")
    assert [a.action for a in audit_rows(session, qid)] == ["site_query.drafted"]


# ---- site views ------------------------------------------------------------------------------------------


def test_sites_show_open_queries_and_the_drill_down_lists_them(client, site_signal_fixtures) -> None:
    draft_id = draft(client).json()["id"]
    sent_id = sent_query(client)
    rows = {s["site_id"]: s["open_queries"] for s in client.get("/api/sites", headers=CRA).json()["sites"]}
    assert rows["112"] == 1 and sum(rows.values()) == 1  # sent or answered; a draft is not open
    queries = client.get("/api/sites/112", headers=CRA).json()["queries"]
    assert {q["id"]: q["status"] for q in queries} == {draft_id: "draft", sent_id: "sent"}
    assert client.get("/api/sites/107", headers=SPONSOR).json()["queries"] == []
