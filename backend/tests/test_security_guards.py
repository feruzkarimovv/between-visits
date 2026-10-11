"""R4 / REQ-017: safe startup (docs/03 §6.3) and demo controls only in demo mode (docs/03 §6.2)."""

import logging
import os
import subprocess
import sys

import pytest

from app.config import BACKEND_DIR, TOOL_SECRET_PLACEHOLDER, Settings, assert_safe_startup, get_settings
from tests.conftest import COORD

LONG_SECRET = "x" * 24  # exactly the minimum length
SHORT_SECRET = "y" * 23
UNSAFE_SECRETS = {"empty": "", "blank": "   ", "placeholder": TOOL_SECRET_PLACEHOLDER, "short": SHORT_SECRET}
DEMO_ROUTES = [
    ("get", "/api/demo/scenarios"),
    ("post", "/api/demo/replay/rosa_es_urgent"),
    ("post", "/api/demo/reset"),
]


def settings(**kw: object) -> Settings:
    """Settings from explicit values only (no .env file), so the test does not depend on a local .env."""
    base: dict[str, object] = {"demo_mode": False, "tool_shared_secret": LONG_SECRET, "pager_channel": "console"}
    return Settings(_env_file=None, **{**base, **kw})


# ---- safe startup ------------------------------------------------------------------------------------------


@pytest.mark.req("REQ-017")
@pytest.mark.parametrize("secret", UNSAFE_SECRETS.values(), ids=UNSAFE_SECRETS.keys())
def test_refuses_unsafe_tool_secret_outside_demo_mode(secret: str) -> None:
    with pytest.raises(SystemExit) as exc:
        assert_safe_startup(settings(tool_shared_secret=secret))
    msg = str(exc.value.code)
    assert msg.startswith("Refusing to start: TOOL_SHARED_SECRET") and "DEMO_MODE=1" in msg
    if secret.strip():
        assert secret not in msg  # the secret is never printed


@pytest.mark.req("REQ-017")
def test_accepts_long_secret_and_demo_mode_accepts_any() -> None:
    assert_safe_startup(settings(tool_shared_secret=LONG_SECRET))
    for secret in UNSAFE_SECRETS.values():
        assert_safe_startup(settings(demo_mode=True, tool_shared_secret=secret))


@pytest.mark.req("REQ-017")
def test_create_app_refuses_default_secret() -> None:
    from app.main import create_app

    before = os.environ["TOOL_SHARED_SECRET"]
    os.environ["TOOL_SHARED_SECRET"] = TOOL_SECRET_PLACEHOLDER
    get_settings.cache_clear()
    try:
        with pytest.raises(SystemExit):
            create_app(start_background=False)
    finally:
        os.environ["TOOL_SHARED_SECRET"] = before
        get_settings.cache_clear()


@pytest.mark.req("REQ-017")
@pytest.mark.parametrize("secret", [TOOL_SECRET_PLACEHOLDER, SHORT_SECRET], ids=["placeholder", "short"])
def test_process_exits_nonzero_with_message(secret: str) -> None:
    """The same import uvicorn performs (`app.main:app`) exits non-zero with a clear message."""
    env = {**os.environ, "DEMO_MODE": "0", "TOOL_SHARED_SECRET": secret, "DATABASE_URL": "sqlite://"}
    r = subprocess.run(
        [sys.executable, "-c", "import app.main"], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60
    )
    assert r.returncode != 0
    assert "Refusing to start: TOOL_SHARED_SECRET" in r.stderr
    assert secret not in r.stderr + r.stdout


@pytest.mark.req("REQ-017")
def test_warns_on_short_ntfy_topic(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="bv"):
        assert_safe_startup(settings(pager_channel="ntfy", ntfy_topic="short-topic"))
    assert any("NTFY_TOPIC" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="bv"):
        assert_safe_startup(settings(pager_channel="ntfy", ntfy_topic="z" * 16))
    assert not any("NTFY_TOPIC" in r.getMessage() for r in caplog.records)


# ---- demo controls only in demo mode ----------------------------------------------------------------------


@pytest.mark.req("REQ-017")
@pytest.mark.parametrize("app_env", ["dev", "prod"])
@pytest.mark.parametrize(("method", "path"), DEMO_ROUTES)
def test_demo_routes_404_unless_demo_mode(client, app_env: str, method: str, path: str) -> None:
    before = os.environ.get("APP_ENV")
    os.environ["APP_ENV"] = app_env
    get_settings.cache_clear()
    try:
        assert get_settings().demo_mode is False
        r = getattr(client, method)(path, headers=COORD)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "demo_disabled"
    finally:
        if before is None:
            os.environ.pop("APP_ENV", None)
        else:
            os.environ["APP_ENV"] = before
        get_settings.cache_clear()


@pytest.mark.req("REQ-017")
def test_demo_routes_open_in_demo_mode(demo_mode, client) -> None:
    assert client.get("/api/health").json()["demo_mode"] is True
    r = client.get("/api/demo/scenarios")
    assert r.status_code == 200 and any(s["id"] == "rosa_es_urgent" for s in r.json())


@pytest.mark.req("REQ-017")
def test_health_reports_demo_mode_off(client) -> None:
    assert client.get("/api/health").json()["demo_mode"] is False
