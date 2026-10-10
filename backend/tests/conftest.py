"""Shared fixtures: in-memory DB seeded from data/, fake pager, fake Gemini, fake ElevenLabs. No network."""

import os

os.environ.update(
    {
        "DATABASE_URL": "sqlite://",
        "TOOL_SHARED_SECRET": "test-secret",
        "DEMO_MODE": "0",
        "APP_ENV": "dev",
        "GEMINI_API_KEY": "",
        "ELEVENLABS_API_KEY": "",
        "ELEVENLABS_WEBHOOK_SECRET": "whsec-test",
        "PAGER_CHANNEL": "console",
        "ACK_TIMEOUT_SECONDS": "90",
        "PUBLIC_BASE_URL": "https://bv-test.example",
        "TWILIO_AUTH_TOKEN": "twilio-test-token",
        "TWILIO_FROM_NUMBER": "+15555550100",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import configure_engine, create_all, get_engine  # noqa: E402
from app.services import gemini, pager  # noqa: E402

get_settings.cache_clear()

SECRET = {"X-BV-Tool-Secret": "test-secret"}
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
