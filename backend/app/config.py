"""Settings from the repo-root .env (see .env.example). Every variable in .env.example is read here."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT = BACKEND_DIR.parent
DATA_DIR = ROOT / "data"
SCENARIOS_DIR = ROOT / "scenarios"
AGENT_DIR = ROOT / "agent"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    # core
    app_env: str = "dev"
    demo_mode: bool = False
    public_base_url: str = "http://localhost:8000"
    ngrok_domain: str = ""
    database_url: str = "sqlite:///./backend/data/app.db"
    cors_origins: str = "http://localhost:3000"
    tool_shared_secret: str = "change-me-long-random-string"
    display_tz: str = "America/New_York"
    ack_timeout_seconds: int = 90

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_webhook_secret: str = ""
    elevenlabs_phone_number_id: str = ""
    elevenlabs_llm: str = "gemini-3.5-flash"
    elevenlabs_voice_id_en: str = ""
    elevenlabs_voice_id_es: str = ""

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

    # frontend (read so config is complete; unused by the backend)
    next_public_api_base_url: str = "http://localhost:8000"
    next_public_use_fixtures: str = "0"

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
    def effective_pager_channel(self) -> str:
        if self.demo_mode or (self.pager_channel == "ntfy" and not self.ntfy_topic):
            return "console"
        return self.pager_channel

    @property
    def demo_controls_enabled(self) -> bool:
        return self.demo_mode or self.app_env == "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
