"""Gemini wrappers for the post-call pipeline and SAE narratives, each with a deterministic fake.

Real calls use google-genai structured output (response_schema = Pydantic model) and read `resp.parsed`;
None means the output didn't validate: retry once, then raise (callers fail safe). Enum fields constrain
terms and red-flag IDs to what exists in data/. Gemini never grades and never decides escalation: the
safety net only *lists* red-flag IDs it sees mentioned; the backend escalates every one (false alarms are
acceptable, misses are not).

The fake (DEMO_MODE=1, tests, no GEMINI_API_KEY) is a keyword lexicon over patient turns: good enough to
make the demo and tests deterministic, not a clinical tool.
"""

import enum
import json
import logging
import re
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from app import content
from app.config import get_settings

log = logging.getLogger("bv.gemini")

# ---- schemas ------------------------------------------------------------------------------------------


@lru_cache
def term_enum() -> type[enum.Enum]:
    terms = sorted(set(content.rules_doc()["terms"]) | {t for it in content.items_doc()["items"].values() if (t := it.get("term"))} | {"Chest pain"})
    return enum.Enum("Term", {re.sub(r"\W+", "_", t).upper(): t for t in terms})  # type: ignore[return-value]


@lru_cache
def flag_enum() -> type[enum.Enum]:
    return enum.Enum("RedFlagId", {r["id"]: r["id"] for r in content.red_flags()})  # type: ignore[return-value]


class ExtractedMedication(BaseModel):
    name: str  # as reported, e.g. "loperamide (Imodium)"
    change: str  # started | stopped | changed | unknown
    indication_en: str | None = None
    start_text: str | None = None
    turn_index: int
    quote: str


class ExtractedQuestion(BaseModel):
    text_en: str
    turn_index: int
    quote: str


class ExtractedCareVisit(BaseModel):
    description_en: str
    turn_index: int
    quote: str


def _extraction_models() -> tuple[type[BaseModel], type[BaseModel]]:
    Term = term_enum()

    class ExtractedSymptom(BaseModel):
        term: Term  # type: ignore[valid-type]
        verbatim_en: str
        turn_index: int
        quote: str

    class Extraction(BaseModel):
        symptoms: list[ExtractedSymptom]
        medications: list[ExtractedMedication]
        questions: list[ExtractedQuestion]
        care_visits: list[ExtractedCareVisit]

    return ExtractedSymptom, Extraction


def _safety_models() -> type[BaseModel]:
    Flag = flag_enum()

    class SafetyHit(BaseModel):
        red_flag_id: Flag  # type: ignore[valid-type]
        turn_index: int
        quote: str

    class SafetyNet(BaseModel):
        hits: list[SafetyHit]

    return SafetyNet


class TranslationItem(BaseModel):
    i: int
    en: str


class Translations(BaseModel):
    items: list[TranslationItem]


# ---- public API (dict results so callers don't depend on dynamic models) ------------------------------


def use_fake() -> bool:
    s = get_settings()
    return s.demo_mode or not s.gemini_api_key or _force_fake


_force_fake = False


def set_fake(on: bool) -> None:
    global _force_fake
    _force_fake = on


def _numbered(turns: list[dict[str, Any]]) -> str:
    return "\n".join(f"[{t['i']}] {t['role'].upper()}: {t['text']}" for t in turns if t.get("text"))


def extract(turns: list[dict[str, Any]], lang: str) -> dict[str, Any]:
    if use_fake():
        return fake_extract(turns)
    _, Extraction = _extraction_models()
    terms = ", ".join(e.value for e in term_enum())  # type: ignore[attr-defined]
    prompt = (
        "You read a transcript of an automated symptom check-in call with a clinical-trial patient (or caregiver). "
        "List ONLY what the patient/caregiver (USER turns) said. Do not infer, diagnose or judge severity.\n"
        f"- symptoms: every symptom the person said they have or had (not ones they denied). term must be one of: {terms}. "
        "verbatim_en: short English paraphrase of exactly what they said.\n"
        "- medications: any medicine, pharmacy product or vitamin they started, stopped or changed. name: the generic "
        "name followed by the brand they said in parentheses, e.g. 'loperamide (Imodium)'; if you don't know the generic, "
        "the name as said.\n"
        "- questions: any question they asked that needs a nurse (medical questions), in English.\n"
        "- care_visits: any ER, urgent care, hospital or other doctor visit.\n"
        "turn_index is the [number] of the USER turn; quote is the exact words from that turn in the original language.\n"
        f"Call language: {lang}.\n\nTRANSCRIPT:\n{_numbered(turns)}"
    )
    parsed = _generate(get_settings().gemini_model_fast, prompt, Extraction, thinking=False)
    data = parsed.model_dump(mode="json")
    return data


def safety_net(turns: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    if use_fake():
        return fake_safety_net(turns)
    SafetyNet = _safety_models()
    flags = "\n".join(
        f"- {r['id']}: {r['agent_description']} (examples: {'; '.join(r.get('examples_en', []) + r.get('examples_es', []))})"
        for r in content.red_flags()
    )
    prompt = (
        "Safety review of a clinical-trial check-in call transcript. List every red flag below that the patient or "
        "caregiver (USER turns) mentioned as happening to the patient, even in passing, even if they downplayed it "
        "('it's probably nothing'). Do not list flags they clearly denied. When unsure, include it: a false alarm is "
        "acceptable, a miss is not.\n"
        f"RED FLAGS:\n{flags}\n\nturn_index is the [number] of the USER turn; quote is their exact words.\n"
        f"Call language: {lang}.\n\nTRANSCRIPT:\n{_numbered(turns)}"
    )
    parsed = _generate(get_settings().gemini_model_long, prompt, SafetyNet, thinking=True)
    return parsed.model_dump(mode="json")["hits"]


def translate(texts: list[str], src_lang: str) -> list[str]:
    """Translate patient quotes to English for staff. Clinical questions are never translated at runtime."""
    if not texts:
        return []
    if use_fake():
        return [fake_translate(t) for t in texts]
    prompt = (
        f"Translate each patient quote from {content.language_name(src_lang)} to plain English, literally, keeping "
        "hesitations and numbers. Return one item per input with the same i.\n\n"
        + "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))
    )
    parsed = _generate(get_settings().gemini_model_fast, prompt, Translations, thinking=False)
    by_i = {it.i: it.en for it in parsed.items}  # type: ignore[attr-defined]
    return [by_i.get(i, "") for i in range(len(texts))]


def draft_narrative(payload: dict[str, Any], quotes: list[str]) -> str:
    """AI-drafted SAE narrative from report fields and evidence only (labeled 'AI draft' in the UI)."""
    if use_fake():
        return template_narrative(payload)
    prompt = (
        "Draft a short, factual serious adverse event narrative (CIOMS style, 4-6 sentences, English) for an "
        "investigator to edit. Use ONLY the facts in the JSON and the quotes. Do not add diagnoses, treatments, "
        "causality opinions beyond the investigator's assessment, or any medical advice. Refer to the study drug "
        "only as written in suspect_product. Say 'provisional CTCAE grade'.\n\n"
        f"REPORT:\n{json.dumps(payload, ensure_ascii=False)}\n\nPATIENT QUOTES:\n" + "\n".join(f"- {q}" for q in quotes)
    )
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=get_settings().gemini_api_key)
    resp = client.models.generate_content(
        model=get_settings().gemini_model_long, contents=prompt,
        config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="low")),
    )
    text = (resp.text or "").strip()
    return text or template_narrative(payload)


def _generate(model: str, prompt: str, schema: type[BaseModel], thinking: bool) -> Any:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=get_settings().gemini_api_key)
    cfg: dict[str, Any] = {"response_mime_type": "application/json", "response_schema": schema}
    if thinking:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_level="low")
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=types.GenerateContentConfig(**cfg))
            if resp.parsed is not None:
                return resp.parsed
            last_err = ValueError("structured output did not validate")
        except Exception as e:  # noqa: BLE001
            last_err = e
        log.warning("gemini_retry model=%s attempt=%d error=%r", model, attempt, last_err)
    raise RuntimeError(f"gemini failed: {last_err!r}")


# ---- deterministic fake -------------------------------------------------------------------------------

SYMPTOM_LEXICON: list[tuple[str, str]] = [
    ("Diarrhea", r"diarr?h?ea|diarrea|loose stool|watery stool|evacuaciones sueltas"),
    ("Nausea", r"nause|náusea|sick to my stomach|ganas de vomitar"),
    ("Vomiting", r"vomit|vómit|throw(ing)? up|threw up"),
    ("Fever", r"fever|fiebre|temperature of|temperatura de"),
    ("Chills", r"chills|escalofr"),
    ("Dyspnea", r"short of breath|out of breath|breathless|falta (de )?(el )?aire|me falta el aire"),
    ("Dizziness", r"dizz|lightheaded|mare[oéa]|marea"),
    ("Fatigue", r"tired|fatigue|no energy|cansad|cansancio"),
    ("Rash maculo-papular", r"\brash\b|sarpullido|erupci"),
    ("Confusion", r"confus|confundid|mixing up words"),
    ("Chest pain", r"chest|pecho"),
    ("Cough", r"\bcough|\btos\b"),
]
MED_LEXICON: list[tuple[str, str]] = [
    ("loperamide (Imodium)", r"imodium|loperamid"),
    ("acetaminophen (Tylenol)", r"tylenol|acetaminof|paracetamol"),
    ("amoxicillin", r"amoxicil"),
    ("ibuprofen", r"ibuprofen|advil|motrin"),
    ("antibiotic (name not given)", r"antibiotic|antibiótico"),
]
FLAG_LEXICON: list[tuple[str, str]] = [
    ("RF_CHEST_PAIN", r"chest pain|pressure in my chest|chest (feels )?tight|presi[oó]n en el pecho|dolor (de|en el) pecho|me duele el pecho"),
    ("RF_SELF_HARM", r"don'?t want to live|kill myself|hurt myself|no quiero vivir|quitarme la vida|hacerme daño"),
    ("RF_BREATHING_SEVERE", r"can'?t breathe|barely breathe|no puedo respirar|casi no puedo respirar"),
    ("RF_SEIZURE_FAINT", r"passed out|faint|seizure|desmay|convuls"),
    ("RF_DEHYDRATION", r"dizzy when i st(an|oo)d|lightheaded when i st|mare[eé] al levantar|mareo al levantar|me mareo al ponerme de pie|can'?t keep (water|liquids|fluids|anything) down|no puedo retener"),
    ("RF_NEURO", r"confus|confundid|mixing up words"),
    ("RF_BLEEDING", r"(threw up|vomited|vomiting) blood|vomit[eé] sangre"),
    ("RF_LIVER_KIDNEY", r"yellow (skin|eyes)|eyes (look|are) yellow|ojos amarillos|piel amarilla|casi no orino"),
    ("RF_HEART", r"heart is racing|heart (is )?pounding|late muy r[aá]pido"),
    ("RF_DIARRHEA_SEVERE", r"blood in (my |the )?(stool|toilet)|sangre en (las )?heces"),
    ("RF_BREATHING", r"out of breath (even )?(sitting|at rest|resting)|falta el aire aunque est"),
]
QUESTION = re.compile(r"\?|¿")

# Known English translations for scripted demo quotes (filled by the replay engine from scenario files).
KNOWN_TRANSLATIONS: dict[str, str] = {}


def _user_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in turns if t.get("role") == "user" and t.get("text")]


def fake_extract(turns: list[dict[str, Any]]) -> dict[str, Any]:
    symptoms, meds, questions, visits = [], [], [], []
    seen_terms: set[str] = set()
    seen_meds: set[str] = set()
    for t in _user_turns(turns):
        text = t["text"]
        low = text.lower()
        for term, pat in SYMPTOM_LEXICON:
            if term not in seen_terms and re.search(pat, low) and not re.match(r"^\s*(no|never|nunca|nada)\b", low):
                seen_terms.add(term)
                symptoms.append({"term": term, "verbatim_en": fake_translate(text) or text, "turn_index": t["i"], "quote": text})
        for name, pat in MED_LEXICON:
            if name not in seen_meds and re.search(pat, low):
                seen_meds.add(name)
                meds.append({"name": name, "change": "started", "indication_en": None, "start_text": None,
                             "turn_index": t["i"], "quote": text})
        if QUESTION.search(text) and len(text) > 12 and re.search(r"\b(should|can i|is it|debo|puedo|es el|es normal)\b", low):
            questions.append({"text_en": fake_translate(text) or text, "turn_index": t["i"], "quote": text})
        if re.search(r"urgent care|emergency room|\ber\b|hospital|urgencias|sala de emergencias", low):
            visits.append({"description_en": fake_translate(text) or text, "turn_index": t["i"], "quote": text})
    return {"symptoms": symptoms, "medications": meds, "questions": questions, "care_visits": visits}


def fake_safety_net(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for t in _user_turns(turns):
        low = t["text"].lower()
        for fid, pat in FLAG_LEXICON:
            if fid not in seen and re.search(pat, low):
                seen.add(fid)
                hits.append({"red_flag_id": fid, "turn_index": t["i"], "quote": t["text"]})
    return hits


def fake_translate(text: str) -> str:
    """Known scripted translations only; unknown text gets "" (no translation shown) rather than a fake one."""
    return KNOWN_TRANSLATIONS.get(text.strip(), "")


def template_narrative(p: dict[str, Any]) -> str:
    pt, rx = p.get("patient", {}), p.get("reaction", {})
    sex = {"F": "female", "M": "male"}.get(pt.get("sex", ""), "patient")
    cms = ", ".join(c.get("medication", "") for c in p.get("concomitant", [])) or "none reported"
    crit = ", ".join(s.replace("_", " ") for s in p.get("seriousness", [])) or "none"
    grade = rx.get("provisional_ctcae_grade")
    return (
        f"Subject {pt.get('subject_id')} ({pt.get('age')}-year-old {sex}) enrolled in study "
        f"{p.get('study', {}).get('nct_id')} reported {str(rx.get('term', '')).lower()} during a between-visit "
        f"automated check-in call. Onset {rx.get('onset_date') or 'unknown'}; last study drug dose "
        f"{p.get('suspect_product', {}).get('last_dose_date') or 'unknown'}. Patient report: "
        f"{rx.get('description') or 'see evidence quotes'}. Provisional CTCAE v{rx.get('ctcae_version', '5.0')} "
        f"grade {grade if grade is not None else 'not assigned'}. Seriousness criteria: {crit}. "
        f"Concomitant medications reported: {cms}. Investigator causality assessment: "
        f"{str(p.get('causality', {}).get('result', 'pending')).replace('_', ' ')}. Outcome at time of report: "
        f"{str(rx.get('outcome', 'unknown')).replace('_', ' ')}."
    )
