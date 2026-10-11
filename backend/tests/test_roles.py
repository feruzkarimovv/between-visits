"""B12 (docs/03 §6.1): role-restricted routes answer any other role with 403 `wrong_role`; the `cra` role.

ROLE_TABLE is the (method, path, role) -> status table for REQ-018. B17-B19 append the Site Signal rows
(cra/sponsor views, CRA-only and coordinator-only query actions) as those routes land.
"""

import pytest
from sqlmodel import select

from app.models import AuditEvent, SAEReport
from app.routers.api import normalize_role, require_role
from app.schemas import ROLES
from app.services import replay

pytestmark = pytest.mark.req("REQ-018")

# Request bodies by (method, path template); routes without a body are absent.
BODIES: dict[tuple[str, str], dict] = {
    ("POST", "/api/drafts/{draft_id}/investigator"): {"is_serious": False, "relatedness": "unlikely_related"},
    ("PATCH", "/api/sae/{sae_id}"): {"narrative_final": "Narrative edited by the investigator."},
}

# (method, path template, X-BV-Role header or None for no header, expected status)
ROLE_TABLE: list[tuple[str, str, str | None, int]] = [
    # investigator only
    ("POST", "/api/drafts/{draft_id}/investigator", "investigator", 200),
    ("POST", "/api/drafts/{draft_id}/investigator", "coordinator", 403),
    ("POST", "/api/drafts/{draft_id}/investigator", "sponsor", 403),
    ("POST", "/api/drafts/{draft_id}/investigator", "cra", 403),
    ("PATCH", "/api/sae/{sae_id}", "investigator", 200),
    ("PATCH", "/api/sae/{sae_id}", "coordinator", 403),
    ("PATCH", "/api/sae/{sae_id}", "sponsor", 403),
    ("PATCH", "/api/sae/{sae_id}", "cra", 403),
    ("POST", "/api/sae/{sae_id}/sign", "investigator", 200),
    ("POST", "/api/sae/{sae_id}/sign", "coordinator", 403),
    ("POST", "/api/sae/{sae_id}/sign", "sponsor", 403),
    ("POST", "/api/sae/{sae_id}/sign", "cra", 403),
    # a missing or unknown role means coordinator; known roles are case-insensitive
    ("POST", "/api/drafts/{draft_id}/investigator", None, 403),
    ("POST", "/api/drafts/{draft_id}/investigator", "admin", 403),
    ("POST", "/api/drafts/{draft_id}/investigator", "Investigator", 200),
    ("POST", "/api/sae/{sae_id}/sign", None, 403),
    ("POST", "/api/sae/{sae_id}/sign", "nurse", 403),
    ("POST", "/api/sae/{sae_id}/sign", "INVESTIGATOR", 200),
    # every other /api route: any role (unchanged)
    ("GET", "/api/sae/{sae_id}", "cra", 200),
    ("GET", "/api/sae/{sae_id}", "sponsor", 200),
    ("GET", "/api/drafts", "cra", 200),
    ("GET", "/api/sponsor/inbox", "cra", 200),
    ("GET", "/api/audit", "cra", 200),
    ("GET", "/api/escalations", "cra", 200),
]


def _headers(role: str | None) -> dict[str, str]:
    h = {"X-BV-User": "Role table"}
    if role is not None:
        h["X-BV-Role"] = role
    return h


@pytest.fixture
def review_state(client, session, fake_pager) -> dict[str, str]:
    """Rosa replay with both AE drafts confirmed; the Diarrhea AE has a serious-event report in draft."""
    cid = replay.start(session, "rosa_es_urgent", speed=10_000, run_async=False)
    drafts = client.get("/api/drafts", params={"checkin_id": cid}).json()
    ae = {d["payload"]["term"]: d["id"] for d in drafts if d["kind"] == "AE"}
    coord = {"X-BV-User": "Jess Kim", "X-BV-Role": "coordinator"}
    for draft_id in ae.values():
        assert client.post(f"/api/drafts/{draft_id}/confirm", json={}, headers=coord).status_code == 200
    r = client.post(f"/api/drafts/{ae['Diarrhea']}/investigator", headers={"X-BV-Role": "investigator"}, json={
        "is_serious": True, "seriousness_criteria": ["hospitalization"], "relatedness": "possibly_related", "sign": False,
    })
    assert r.status_code == 200
    return {"checkin_id": cid, "draft_id": ae["Dizziness"], "sae_id": r.json()["sae_report"]["id"]}


@pytest.mark.parametrize(("method", "path", "role", "status"), ROLE_TABLE)
def test_role_table(client, review_state, method, path, role, status):
    body = BODIES.get((method, path))
    r = client.request(method, path.format(**review_state), headers=_headers(role), json=body)
    assert r.status_code == status, r.text
    if status == 403:
        err = r.json()["error"]
        assert err["code"] == "wrong_role"
        allowed = err["message"].removeprefix("Only the ").split(" role can ")[0].split(" or ")
        assert normalize_role(role) not in allowed and set(allowed) <= set(ROLES)


def test_wrong_role_changes_nothing(client, session, review_state):
    """A 403 leaves the report as it was and writes no audit event."""
    sae_id = review_state["sae_id"]
    n0 = len(session.exec(select(AuditEvent)).all())
    for role in ("coordinator", "sponsor", "cra"):
        assert client.post(f"/api/sae/{sae_id}/sign", headers=_headers(role)).status_code == 403
        assert client.patch(f"/api/sae/{sae_id}", headers=_headers(role), json={"narrative_final": "x"}).status_code == 403
    session.expire_all()
    report = session.get(SAEReport, sae_id)
    assert report is not None and report.status == "draft" and report.narrative_final is None
    assert len(session.exec(select(AuditEvent)).all()) == n0


def test_role_is_checked_before_the_entity_and_body(client, review_state):
    """403 for a wrong role even when the entity is missing or the body is invalid; the investigator gets 404/422."""
    missing = "/api/sae/sae_does_not_exist/sign"
    assert client.post(missing, headers=_headers("cra")).json()["error"]["code"] == "wrong_role"
    assert client.post(missing, headers=_headers("investigator")).status_code == 404
    path = f"/api/drafts/{review_state['draft_id']}/investigator"
    assert client.post(path, headers=_headers("coordinator"), json={"is_serious": "maybe"}).status_code == 403
    assert client.post(path, headers=_headers("investigator"), json={"is_serious": "maybe"}).status_code == 422


def test_contract_message_for_signing(client, review_state):
    r = client.post(f"/api/sae/{review_state['sae_id']}/sign", headers=_headers("coordinator"))
    assert r.json() == {"error": {"code": "wrong_role",
                                  "message": "Only the investigator role can sign the serious-event report."}}


@pytest.mark.parametrize(("header", "audit_role"), [
    ("cra", "cra"), ("CRA", "cra"), ("sponsor", "sponsor"), ("coordinator", "coordinator"),
    (None, "coordinator"), ("", "coordinator"), ("admin", "coordinator"),
])
def test_audit_records_the_role(client, session, review_state, header, audit_role):
    """AuditEvent.role takes the normalized X-BV-Role, including cra (any-role route, unchanged by §6.1)."""
    drafts = client.get("/api/drafts", params={"checkin_id": review_state["checkin_id"], "kind": "CM"}).json()
    r = client.patch(f"/api/drafts/{drafts[0]['id']}", headers=_headers(header), json={"payload": {}, "note": "role check"})
    assert r.status_code == 200
    ev = session.exec(select(AuditEvent).where(AuditEvent.action == "draft.edited")).one()
    assert ev.role == audit_role and ev.actor == "Role table"
    listed = client.get("/api/audit", params={"entity_id": drafts[0]["id"]}).json()
    assert [a["role"] for a in listed if a["action"] == "draft.edited"] == [audit_role]


def test_roles_and_normalization():
    assert ROLES == ("coordinator", "investigator", "sponsor", "cra")
    assert [normalize_role(v) for v in ("cra", " Sponsor ", None, "", "nurse", "agent")] == [
        "cra", "sponsor", "coordinator", "coordinator", "coordinator", "coordinator"]


def test_require_role_needs_known_roles():
    with pytest.raises(ValueError):
        require_role()
    with pytest.raises(ValueError):
        require_role("nurse")  # type: ignore[arg-type]
    require_role("cra", "sponsor")  # the Site Signal router reuses the same helper
