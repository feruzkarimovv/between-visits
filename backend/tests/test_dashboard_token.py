"""R6: optional dashboard token (docs/03 §6.8).

With BV_DASHBOARD_TOKEN set, every /api/* request except GET /api/health needs X-BV-Token, else 401
`invalid_token`; /agent/tools/* and /webhooks/* keep their own checks and never see the token.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from app.config import get_settings
from app.main import create_app, needs_dashboard_token
from app.models import CheckIn
from tests.conftest import COORD, SECRET
from tests.test_paging import urgent_escalation

TOKEN = "dash-test-token-0123456789abcdef"  # test value only; the real one lives in the host's environment
WITH_TOKEN = {**COORD, "X-BV-Token": TOKEN}
ORIGIN = "http://localhost:3000"  # the default CORS_ORIGINS


def set_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    get_settings.cache_clear()


@pytest.fixture
def token_client(db) -> Iterator[TestClient]:
    """An app built with BV_DASHBOARD_TOKEN set (the token is read once, when the app is created)."""
    before = os.environ.get("BV_DASHBOARD_TOKEN")
    set_env("BV_DASHBOARD_TOKEN", TOKEN)
    try:
        with TestClient(create_app(start_background=False)) as c:
            yield c
    finally:
        set_env("BV_DASHBOARD_TOKEN", before)


def assert_invalid_token(r) -> None:
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "invalid_token"
    assert TOKEN not in r.text  # the expected token is never echoed


# ---- which requests are gated --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "gated"),
    [
        ("GET", "/api/health", False),
        ("HEAD", "/api/health", True),
        ("get", "/api/health", False),
        ("POST", "/api/health", True),
        ("GET", "/api/healthz", True),
        ("GET", "/api/health/", True),
        ("GET", "/api", True),
        ("GET", "/api/patients", True),
        ("POST", "/api/drafts/dr_x/confirm", True),
        ("POST", "/api/demo/reset", True),
        ("POST", "/agent/tools/record_answer", False),
        ("POST", "/webhooks/elevenlabs/post-call", False),
        ("POST", "/webhooks/ntfy/ack/esc_x", False),
        ("GET", "/apix", False),
        ("GET", "/openapi.json", False),
    ],
)
def test_needs_dashboard_token(method: str, path: str, gated: bool) -> None:
    assert needs_dashboard_token(method, path) is gated


# ---- token set ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/patients"),
        ("get", "/api/checkins"),
        ("get", "/api/audit/verify"),
        ("get", "/api/no-such-route"),  # 401 before routing: a gated instance does not reveal its routes
        ("post", "/api/demo/reset"),  # 401 before the demo_disabled 404
    ],
)
def test_api_without_token_is_401_invalid_token(token_client: TestClient, method: str, path: str) -> None:
    assert_invalid_token(token_client.request(method.upper(), path, headers=COORD))


@pytest.mark.parametrize("bad", ["", "   ", "wrong-token", TOKEN[:-1], TOKEN + "x", TOKEN.upper()])
def test_wrong_token_is_401(token_client: TestClient, bad: str) -> None:
    assert_invalid_token(token_client.get("/api/patients", headers={**COORD, "X-BV-Token": bad}))


def test_api_with_token_is_200(token_client: TestClient) -> None:
    r = token_client.get("/api/patients", headers=WITH_TOKEN)
    assert r.status_code == 200, r.text
    assert any(p["id"] == "pat_rosa" for p in r.json())
    assert token_client.get("/api/audit/verify", headers=WITH_TOKEN).json()["ok"] is True
    # behind the token the normal errors come back (here: demo routes stay off outside DEMO_MODE)
    r = token_client.post("/api/demo/reset", headers=WITH_TOKEN)
    assert r.status_code == 404 and r.json()["error"]["code"] == "demo_disabled"


def test_health_is_exempt(token_client: TestClient) -> None:
    r = token_client.get("/api/health")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["demo_mode"] is False


def test_agent_tools_are_unaffected(token_client: TestClient, session) -> None:
    cid = session.exec(select(CheckIn).where(CheckIn.patient_id == "pat_rosa")).one().id
    body = {"checkin_id": cid, "item_code": "IDENTITY", "option_code": "yes", "verbatim_quote": "Sí, soy yo."}
    r = token_client.post("/agent/tools/record_answer", json=body, headers=SECRET)  # tool secret, no X-BV-Token
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["next"]["item_code"] == "CALL_CONSENT"
    r = token_client.post("/agent/tools/record_answer", json=body)  # the tool secret is still required
    assert r.status_code == 401 and r.json()["error"]["code"] == "bad_tool_secret"


def test_webhooks_are_unaffected(token_client: TestClient, session, fake_pager) -> None:
    r = token_client.post("/webhooks/elevenlabs/post-call", content=b"{}",
                          headers={"ElevenLabs-Signature": "t=1,v0=bad", "Content-Type": "application/json"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "bad_signature"  # HMAC check, not the token
    e = urgent_escalation(session)
    assert token_client.post(f"/webhooks/ntfy/ack/{e.id}").status_code == 401  # the ack token is still required
    ok = token_client.post(f"/webhooks/ntfy/ack/{e.id}", headers={"Authorization": f"Bearer {e.ack_token}"})
    assert ok.status_code == 200 and ok.json() == {"ok": True}


def test_cors_preflight_and_401_carry_cors_headers(token_client: TestClient) -> None:
    """The browser dashboard can send X-BV-Token cross-origin and can read a 401's error code."""
    pre = token_client.options("/api/patients", headers={
        "Origin": ORIGIN, "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "x-bv-token,x-bv-user,x-bv-role"})
    assert pre.status_code == 200, pre.text
    assert pre.headers["access-control-allow-origin"] == ORIGIN
    assert "x-bv-token" in pre.headers["access-control-allow-headers"].lower()
    r = token_client.get("/api/patients", headers={**COORD, "Origin": ORIGIN})
    assert_invalid_token(r)
    assert r.headers["access-control-allow-origin"] == ORIGIN
    ok = token_client.get("/api/patients", headers={**WITH_TOKEN, "Origin": ORIGIN})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == ORIGIN


# ---- token unset (the default, and demo mode) -----------------------------------------------------------------


def test_no_token_by_default(client: TestClient) -> None:
    assert get_settings().dashboard_token is None
    assert client.get("/api/patients", headers=COORD).status_code == 200


def test_blank_token_means_off(db) -> None:
    before = os.environ.get("BV_DASHBOARD_TOKEN")
    set_env("BV_DASHBOARD_TOKEN", "   ")
    try:
        assert get_settings().dashboard_token is None
        with TestClient(create_app(start_background=False)) as c:
            assert c.get("/api/patients", headers=COORD).status_code == 200
    finally:
        set_env("BV_DASHBOARD_TOKEN", before)
