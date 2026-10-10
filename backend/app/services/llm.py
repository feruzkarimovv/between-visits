"""Picks the LLM provider for the post-call pipeline and narratives: Claude, Gemini, or the deterministic fake.

LLM_PROVIDER=auto (default) uses Claude when ANTHROPIC_API_KEY is set, else Gemini when GEMINI_API_KEY is set,
else the fake. DEMO_MODE=1 and tests always use the fake. The voice agent's LLM is separate (set in ElevenLabs
by agent/sync_agent.py) and is not affected by this setting.
"""

from typing import Any

from app.config import get_settings
from app.services import claude, gemini


def provider() -> str:
    s = get_settings()
    if s.demo_mode or gemini._force_fake:
        return "fake"
    choice = (s.llm_provider or "auto").lower()
    if choice == "auto":
        if s.anthropic_api_key:
            return "anthropic"
        if s.gemini_api_key:
            return "gemini"
        return "fake"
    if choice == "anthropic" and not s.anthropic_api_key:
        return "fake"
    if choice == "gemini" and not s.gemini_api_key:
        return "fake"
    return choice


def extract(turns: list[dict[str, Any]], lang: str) -> dict[str, Any]:
    p = provider()
    if p == "anthropic":
        return claude.extract(turns, lang)
    if p == "gemini":
        return gemini.extract(turns, lang)
    return gemini.fake_extract(turns)


def safety_net(turns: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    p = provider()
    if p == "anthropic":
        return claude.safety_net(turns, lang)
    if p == "gemini":
        return gemini.safety_net(turns, lang)
    return gemini.fake_safety_net(turns)


def translate(texts: list[str], src_lang: str) -> list[str]:
    if not texts:
        return []
    p = provider()
    if p == "anthropic":
        return claude.translate(texts, src_lang)
    if p == "gemini":
        return gemini.translate(texts, src_lang)
    return [gemini.fake_translate(t) for t in texts]


def draft_narrative(payload: dict[str, Any], quotes: list[str]) -> str:
    p = provider()
    if p == "anthropic":
        return claude.draft_narrative(payload, quotes) or gemini.template_narrative(payload)
    if p == "gemini":
        return gemini.draft_narrative(payload, quotes)
    return gemini.template_narrative(payload)
