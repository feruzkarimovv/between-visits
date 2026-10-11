"""Settings from the repo-root .env (see .env.example). Every variable in .env.example is read here."""

import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT = BACKEND_DIR.parent
DATA_DIR = ROOT / "data"
SCENARIOS_DIR = ROOT / "scenarios"
AGENT_DIR = ROOT / "agent"
# Written by `make sync-agent` (gitignored). Cloud hosts get the same JSON through AGENTS_LOCK_JSON (docs/03 §6.9).
AGENTS_LOCK_PATH = AGENT_DIR / "agents.lock.json"
# Committed Site Signal outputs (docs/03 §6.9, MONITORING_OUT); written by `make site-signal`.
DEFAULT_MONITORING_OUT = ROOT / "monitoring" / "out"

# The .env.example placeholder for TOOL_SHARED_SECRET; refused outside demo mode (docs/03 §6.3).
TOOL_SECRET_PLACEHOLDER = "change-me-long-random-string"
MIN_TOOL_SECRET_LEN = 24
MIN_NTFY_TOPIC_LEN = 16

log = logging.getLogger("bv")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    # core
    app_env: str = "dev"
    demo_mode: bool = False
    public_base_url: str = "http://localhost:8000"
    ngrok_domain: str = ""
    database_url: str = "sqlite:///./backend/data/app.db"
    cors_origins: str = "http://localhost:3000"
    tool_shared_secret: str = TOOL_SECRET_PLACEHOLDER
    display_tz: str = "America/New_York"
    ack_timeout_seconds: int = 90
    # Optional dashboard token (docs/03 §6.8): when set, every /api/* request except GET /api/health needs
    # X-BV-Token with this value. Set only on the private live instance; it is not authentication.
    bv_dashboard_token: str = ""

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_webhook_secret: str = ""
    elevenlabs_phone_number_id: str = ""
    elevenlabs_llm: str = "claude-sonnet-5-5"  # pinned to the evaluated model (agent/variants.json, V9)
    elevenlabs_voice_id_en: str = ""
    elevenlabs_voice_id_es: str = ""
    # Variant → agent_id map as a JSON string, used only when agent/agents.lock.json is absent (cloud deploys,
    # docs/03 §6.9): the lock file is gitignored and never enters an image.
    agents_lock_json: str = ""

    # Gemini
    gemini_api_key: str = ""
    gemini_model_fast: str = "gemini-3.5-flash-lite"
    gemini_model_long: str = "gemini-3.8-flash"
    gemini_agent_sim_model: str = "gemini-3.5-flash"

    # Claude (Anthropic API): post-call pipeline, SAE narratives, evaluation
    llm_provider: str = "auto"  # auto | anthropic | gemini | fake
    anthropic_api_key: str = ""
    claude_model_fast: str = "claude-opus-5-5"  # extraction, translation
    claude_model_long: str = "claude-opus-5-5"  # safety net, narratives
    claude_model_patient: str = ""  # eval's simulated patient; empty = CLAUDE_MODEL_FAST

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # paging
    pager_channel: str = "ntfy"
    ntfy_server: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_backup_topic: str = ""
    oncall_nurse_name: str = "RN on call"
    oncall_nurse_phone: str = ""
    backup_investigator_name: str = "Dr. on call"
    backup_investigator_phone: str = ""

    # demo replay (docs/03 §6.2): default playback multiplier; the ?speed= parameter overrides it.
    # Unset means 2 in demo mode. An empty, non-numeric or non-positive value is ignored with a warning.
    replay_speed: float | None = None

    # Site Signal (docs/03 §6.9): directory of the committed outputs. Relative paths are from the repo root.
    monitoring_out: Path = DEFAULT_MONITORING_OUT

    # frontend (read so config is complete; unused by the backend)
    next_public_api_base_url: str = "http://localhost:8000"
    next_public_use_fixtures: str = "0"
    next_public_bv_dashboard_token: str = ""

    @field_validator("replay_speed", mode="before")
    @classmethod
    def _replay_speed(cls, value: Any) -> float | None:
        """A bad REPLAY_SPEED never stops the backend from starting: it is ignored (logged) instead."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            speed = float(value)
        except (TypeError, ValueError):
            log.warning("REPLAY_SPEED=%r is not a number; ignored", value)
            return None
        if not (math.isfinite(speed) and speed > 0):
            log.warning("REPLAY_SPEED=%r is not a positive number; ignored", value)
            return None
        return speed

    @field_validator("monitoring_out", mode="before")
    @classmethod
    def _monitoring_out(cls, value: Any) -> Path:
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_MONITORING_OUT
        path = Path(value).expanduser()
        return path if path.is_absolute() else ROOT / path

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_database_url(self) -> str:
        """Relative sqlite paths are resolved against the repo root, so cwd doesn't matter."""
        prefix = "sqlite:///"
        url = self.database_url
        if url.startswith(prefix) and not url.startswith(prefix + "/") and ":memory:" not in url:
            path = (ROOT / url[len(prefix):]).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            return prefix + str(path)
        return url

    @property
    def dashboard_token(self) -> str | None:
        """BV_DASHBOARD_TOKEN without surrounding whitespace, or None when unset: no token check (docs/03 §6.8)."""
        return self.bv_dashboard_token.strip() or None

    @property
    def effective_pager_channel(self) -> str:
        if self.demo_mode or (self.pager_channel == "ntfy" and not self.ntfy_topic):
            return "console"
        return self.pager_channel

    @property
    def demo_controls_enabled(self) -> bool:
        """`/api/demo/*` and the demo-only routes: DEMO_MODE=1 only (APP_ENV does not open them)."""
        return self.demo_mode


@lru_cache
def get_settings() -> Settings:
    return Settings()


def tool_secret_problem(settings: Settings) -> str | None:
    """Why TOOL_SHARED_SECRET is unsafe outside demo mode, or None when it is acceptable."""
    secret = settings.tool_shared_secret
    if not secret.strip():
        return "TOOL_SHARED_SECRET is empty"
    if secret == TOOL_SECRET_PLACEHOLDER:
        return "TOOL_SHARED_SECRET is still the .env.example placeholder"
    if len(secret) < MIN_TOOL_SECRET_LEN:
        return f"TOOL_SHARED_SECRET is shorter than {MIN_TOOL_SECRET_LEN} characters"
    return None


def assert_safe_startup(settings: Settings | None = None) -> None:
    """Refuse to start outside demo mode with a guessable tool secret (docs/03 §6.3).

    DEMO_MODE=1 starts with any secret, because demo mode makes no external calls. Exits the process
    with a non-zero status and a one-line reason; the secret itself is never printed.
    """
    s = settings or get_settings()
    if s.demo_mode:
        return
    problem = tool_secret_problem(s)
    if problem:
        msg = (
            f"Refusing to start: {problem} (DEMO_MODE=0). Generate one with "
            "python3 -c 'import secrets; print(secrets.token_urlsafe(32))' and set TOOL_SHARED_SECRET in .env, "
            "or run with DEMO_MODE=1 (make demo)."
        )
        raise SystemExit(msg)  # printed to stderr; exit status 1
    if s.pager_channel == "ntfy" and len(s.ntfy_topic) < MIN_NTFY_TOPIC_LEN:
        state = (f"is shorter than {MIN_NTFY_TOPIC_LEN} characters" if s.ntfy_topic
                 else "is empty, so pages go to the backend console only")
        log.warning("NTFY_TOPIC %s. Use a long random topic: ntfy topic names act as shared secrets.", state)
