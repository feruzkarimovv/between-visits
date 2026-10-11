"""Loads data/*.json once and assembles approved text. All clinical wording lives in data/, never here.

`question_say` prefers data/local/symptom_items.local.json (gitignored; official items for registered
studies) item by item when that file exists.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
LOCAL_ITEMS = DATA_DIR / "local" / "symptom_items.local.json"


class ContentError(Exception):
    pass


def _load(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


@lru_cache
def items_doc() -> dict[str, Any]:
    return _load("symptom_items.json")


@lru_cache
def local_items() -> dict[str, Any]:
    if LOCAL_ITEMS.exists():
        return json.loads(LOCAL_ITEMS.read_text(encoding="utf-8")).get("items", {})
    return {}


@lru_cache
def scripts_doc() -> dict[str, Any]:
    return _load("scripts.json")


@lru_cache
def red_flags_doc() -> dict[str, Any]:
    return _load("red_flags.json")


@lru_cache
def rules_doc() -> dict[str, Any]:
    return _load("ctcae_rules.json")


@lru_cache
def study_doc() -> dict[str, Any]:
    return _load("study.json")


@lru_cache
def plan_doc() -> dict[str, Any]:
    return _load("plan.json")


@lru_cache
def patients_doc() -> dict[str, Any]:
    return _load("patients.json")


@lru_cache
def signal_rules() -> dict[str, Any]:
    """data/signal_rules.json: Site Signal episode, match, evaluability, paging and minimum-data rules and UI
    labels (schema: docs/02 § Files behind Site Signal); the `cfg` of services/episodes.py. Do not mutate."""
    return _load("signal_rules.json")


@lru_cache
def site_queries() -> dict[str, Any]:
    """data/site_queries.json: approved site query templates, response codes and banned phrases (English)."""
    return _load("site_queries.json")


def reload() -> None:
    for f in (items_doc, local_items, scripts_doc, red_flags_doc, rules_doc, study_doc, plan_doc, patients_doc,
              signal_rules, site_queries):
        f.cache_clear()


# ---- items -------------------------------------------------------------------------------------------


def item(code: str) -> dict[str, Any]:
    try:
        return items_doc()["items"][code]
    except KeyError as e:
        raise ContentError(f"unknown item {code}") from e


def has_item(code: str) -> bool:
    return code in items_doc()["items"]


def scale(code: str) -> dict[str, Any]:
    return items_doc()["scales"][item(code)["scale"]]


def item_options(code: str) -> list[str]:
    """Allowed option codes for an item (always includes `unknown`)."""
    return [*scale(code).get("options", []), "unknown"]


def is_numeric(code: str) -> bool:
    return bool(scale(code).get("numeric"))


def item_units(code: str) -> list[str]:
    return list(scale(code).get("units", []))


def term_of(code: str) -> str | None:
    return item(code).get("term")


def attribute_of(code: str) -> str:
    """Answer.attribute from the item's scale (frequency, severity, yes_no, count, temperature, ...)."""
    sc = item(code)["scale"]
    return {"exertion": "severity"}.get(sc, sc)


def items_for_term(term: str) -> list[str]:
    return [c for c, it in items_doc()["items"].items() if it.get("term") == term]


def item_text(code: str, lang: str) -> dict[str, str | None]:
    it = item(code)
    local = local_items().get(code, {})
    text = (local.get("text") or {}).get(lang) or (it.get("text") or {}).get(lang)
    opts = (local.get("options_say") or {}).get(lang) or (it.get("options_say") or {}).get(lang)
    return {"text": text, "options_say": opts}


def item_source(code: str) -> str:
    return "nci_pro_ctcae_local" if code in local_items() else "study_team"


def question_say(code: str, lang: str, pace: str = "standard", **vars: str) -> str:
    """Spoken text for an item: `text` + `options_say`, or its approved script for flow items."""
    it = item(code)
    if "say_script" in it:
        return script(it["say_script"], lang, **vars)
    t = item_text(code, lang)
    if not t["text"]:
        raise ContentError(f"{code}: no text for {lang}")
    return f"{t['text']} {t['options_say']}" if t["options_say"] else str(t["text"])


def options_phrase(code: str, lang: str) -> str | None:
    """The option list inside options_say ('never, rarely, ... or almost all the time'), for `reask_options`."""
    opts = item_text(code, lang)["options_say"]
    if not opts:
        return None
    m = re.match(r"^\s*(?:Would you say|¿Diría que)\s+(.*?)\?\s*$", opts)
    return m.group(1) if m else None


# ---- scripts -----------------------------------------------------------------------------------------


def script(key: str, lang: str, **vars: Any) -> str:
    try:
        text: str = scripts_doc()["lines"][key][lang]
    except KeyError as e:
        raise ContentError(f"script {key}.{lang} missing") from e
    missing = [p for p in _PLACEHOLDER.findall(text) if vars.get(p) in (None, "")]
    if missing:
        raise ContentError(f"script {key}.{lang}: unfilled placeholders {missing}")
    return _PLACEHOLDER.sub(lambda m: str(vars[m.group(1)]), text)


def pace_instructions(pace: str) -> str:
    return scripts_doc()["pace_instructions"][pace]


def language_name(lang: str, in_lang: str = "en") -> str:
    return scripts_doc()["language_names"][lang][in_lang]


def page_template(key: str) -> Any:
    return scripts_doc()["page_templates_en"][key]


# ---- red flags and rules -----------------------------------------------------------------------------


def red_flags() -> list[dict[str, Any]]:
    return red_flags_doc()["red_flags"]


def red_flag(flag_id: str) -> dict[str, Any]:
    for rf in red_flags():
        if rf["id"] == flag_id:
            return rf
    raise ContentError(f"unknown red flag {flag_id}")


def has_red_flag(flag_id: str) -> bool:
    return any(rf["id"] == flag_id for rf in red_flags())


def level_say_script(level: str) -> str | None:
    return red_flags_doc()["levels"].get(level, {}).get("say_script")


def grading_rules() -> list[dict[str, Any]]:
    return rules_doc()["rules"]


def rules_for(term: str) -> list[dict[str, Any]]:
    return [r for r in grading_rules() if r["term"] == term]


def ctcae_version() -> str:
    return rules_doc().get("ctcae_version", "5.0")


def find_unfilled(text: str) -> list[str]:
    return _PLACEHOLDER.findall(text) + re.findall(r"\$\{(\w+)\}", text)


def data_path(name: str) -> Path:
    return DATA_DIR / name
