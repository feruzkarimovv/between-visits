"""Claude (Anthropic API) provider for the post-call pipeline and SAE narratives.

Same contract as the Gemini provider in app/services/gemini.py: structured output validated against a Pydantic
model whose enums come from data/ (terms, red-flag IDs). Claude never grades and never decides escalation; the
safety net only lists red-flag IDs it sees mentioned and the backend escalates every one.

Uses the beta `messages.parse` helper with server-side refusal fallbacks ("default" routing): if a safety
classifier declines (possible on self-harm or symptom content), the API re-runs the request on a fallback model.
A final refusal raises, and every caller fails safe (a human is paged).
"""

import json
import logging
from functools import lru_cache
from typing import Any

import anthropic
from pydantic import BaseModel

from app import content
from app.config import get_settings
from app.services import gemini

log = logging.getLogger("bv.claude")

FALLBACK_BETA = "server-side-fallback-2026-07-01"


@lru_cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key or None, max_retries=3)


def _parse(model: str, effort: str, system: str, prompt: str, schema: type[BaseModel]) -> Any:
    resp = _client().beta.messages.parse(
        model=model,
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": effort},
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"claude refused ({getattr(resp.stop_details, 'category', None)})")
    if resp.parsed_output is None:
        raise RuntimeError(f"claude output did not validate (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def _text(model: str, effort: str, system: str, prompt: str) -> str:
    resp = _client().beta.messages.create(
        model=model,
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": effort},
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"claude refused ({getattr(resp.stop_details, 'category', None)})")
    return "".join(b.text for b in resp.content if b.type == "text").strip()


SYSTEM = (
    "You process transcripts of automated symptom check-in calls with clinical-trial patients. You only report "
    "what the patient or caregiver said, with exact quotes. You never diagnose, judge severity, grade, or advise."
)


def extract(turns: list[dict[str, Any]], lang: str) -> dict[str, Any]:
    _, Extraction = gemini._extraction_models()
    terms = ", ".join(e.value for e in gemini.term_enum())  # type: ignore[attr-defined]
    prompt = (
        "List ONLY what the patient/caregiver (USER turns) said. Do not infer.\n"
        f"- symptoms: every symptom the person said they have or had (not ones they denied). term must be one of: {terms}. "
        "verbatim_en: short English paraphrase of exactly what they said.\n"
        "- medications: any medicine, pharmacy product or vitamin they started, stopped or changed. name: the generic "
        "name followed by the brand they said in parentheses, e.g. 'loperamide (Imodium)'; if you don't know the generic, "
        "the name as said.\n"
        "- questions: any question they asked that needs a nurse (medical questions), in English.\n"
        "- care_visits: any ER, urgent care, hospital or other doctor visit.\n"
        "turn_index is the [number] of the USER turn; quote is the exact words from that turn in the original language.\n"
        f"Call language: {lang}.\n\n<transcript>\n{gemini._numbered(turns)}\n</transcript>"
    )
    s = get_settings()
    return _parse(s.claude_model_fast, "medium", SYSTEM, prompt, Extraction).model_dump(mode="json")


def safety_net(turns: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    SafetyNet = gemini._safety_models()
    flags = "\n".join(
        f"- {r['id']}: {r['agent_description']} (examples: {'; '.join(r.get('examples_en', []) + r.get('examples_es', []))})"
        for r in content.red_flags()
    )
    prompt = (
        "Safety review. List every red flag below that the patient or caregiver (USER turns) mentioned as happening "
        "to the patient, even in passing, even if they downplayed it ('it's probably nothing'). Do not list flags "
        "they clearly denied. When unsure, include it: a false alarm is acceptable, a miss is not.\n"
        f"<red_flags>\n{flags}\n</red_flags>\n"
        "turn_index is the [number] of the USER turn; quote is their exact words.\n"
        f"Call language: {lang}.\n\n<transcript>\n{gemini._numbered(turns)}\n</transcript>"
    )
    s = get_settings()
    return _parse(s.claude_model_long, "high", SYSTEM, prompt, SafetyNet).model_dump(mode="json")["hits"]


def translate(texts: list[str], src_lang: str) -> list[str]:
    prompt = (
        f"Translate each patient quote from {content.language_name(src_lang)} to plain English, literally, keeping "
        "hesitations and numbers. Return one item per input with the same i.\n\n"
        + "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))
    )
    s = get_settings()
    parsed = _parse(s.claude_model_fast, "low", "You translate patient quotes for clinical staff, literally.", prompt,
                    gemini.Translations)
    by_i = {it.i: it.en for it in parsed.items}
    return [by_i.get(i, "") for i in range(len(texts))]


def draft_narrative(payload: dict[str, Any], quotes: list[str]) -> str:
    prompt = (
        "Draft a short, factual serious adverse event narrative (CIOMS style, 4-6 sentences, English) for an "
        "investigator to edit. Use ONLY the facts in the report JSON and the quotes. Do not add diagnoses, treatments, "
        "causality opinions beyond the investigator's assessment, or any medical advice. Refer to the study drug "
        "only as written in suspect_product. Say 'provisional CTCAE grade'. Reply with the narrative only.\n\n"
        f"<report>\n{json.dumps(payload, ensure_ascii=False)}\n</report>\n<quotes>\n"
        + "\n".join(f"- {q}" for q in quotes) + "\n</quotes>"
    )
    s = get_settings()
    return _text(s.claude_model_long, "medium", "You draft pharmacovigilance narratives from given facts only.", prompt)
