"""Shared fixtures: in-memory DB seeded from data/, fake pager, fake Gemini, fake ElevenLabs. No network."""

import os

# At least 24 characters: assert_safe_startup() refuses shorter tool secrets outside demo mode (docs/03 §6.3).
TEST_TOOL_SECRET = "test-secret-test-secret-test"

os.environ.update(
    {
        "DATABASE_URL": "sqlite://",
        "TOOL_SHARED_SECRET": TEST_TOOL_SECRET,
        "DEMO_MODE": "0",
        "APP_ENV": "dev",
        "GEMINI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "LLM_PROVIDER": "auto",
        "ELEVENLABS_API_KEY": "",
        "ELEVENLABS_WEBHOOK_SECRET": "whsec-test",
        "PAGER_CHANNEL": "console",
        "ACK_TIMEOUT_SECONDS": "90",
        "PUBLIC_BASE_URL": "https://bv-test.example",
        "TWILIO_AUTH_TOKEN": "twilio-test-token",
        "TWILIO_FROM_NUMBER": "+15555550100",
        # Off unless a test turns it on (test_dashboard_token.py), whatever a local .env says (docs/03 §6.8, §6.9).
        "BV_DASHBOARD_TOKEN": "",
        "AGENTS_LOCK_JSON": "",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import configure_engine, create_all, get_engine  # noqa: E402
from app.services import gemini, pager  # noqa: E402

get_settings.cache_clear()

SECRET = {"X-BV-Tool-Secret": TEST_TOOL_SECRET}
COORD = {"X-BV-User": "Jess Kim", "X-BV-Role": "coordinator"}
INVESTIGATOR = {"X-BV-User": "Dr. Patel", "X-BV-Role": "investigator"}


class FakePager:
    def __init__(self) -> None:
        self.sent: list[pager.PageMessage] = []

    def __call__(self, msg: pager.PageMessage) -> pager.PageResult:
        self.sent.append(msg)
        return pager.PageResult("fake", "RN on call", f"fake-{len(self.sent)}")


@pytest.fixture
def fake_pager():
    fp = FakePager()
    pager.set_pager(fp)
    yield fp
    pager.set_pager(None)


@pytest.fixture
def demo_mode():
    """DEMO_MODE=1 for tests that call /api/demo/* (DEMO_MODE is the only switch, docs/03 §6.2)."""
    before = os.environ.get("DEMO_MODE")
    os.environ["DEMO_MODE"] = "1"
    get_settings.cache_clear()
    yield
    if before is None:
        os.environ.pop("DEMO_MODE", None)
    else:
        os.environ["DEMO_MODE"] = before
    get_settings.cache_clear()


@pytest.fixture
def db(fake_pager):
    configure_engine("sqlite://")
    create_all()
    from app.seed import seed

    gemini.set_fake(True)
    with Session(get_engine()) as s:
        seed(s)
    yield get_engine()
    gemini.set_fake(False)


@pytest.fixture
def session(db):
    with Session(db) as s:
        yield s


@pytest.fixture
def client(db):
    from app.main import create_app

    app = create_app(start_background=False)
    with TestClient(app) as c:
        yield c
