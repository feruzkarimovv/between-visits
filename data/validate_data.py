"""Cross-checks every clinical/seed data file. Run: uv run python data/validate_data.py (exit 1 on failure).

Checks: plan items and red flags exist; every item has EN+ES text (or a script); follow-ups and rule
conditions reference real items and scale values; scripts exist in both languages with known
placeholders and dash-written emergency numbers; tool option enum == all scale options; the agent
prompt lists every option; personas reference real flags/terms; 2x2 persona grid; no licensed content
(PRO-CTCAE claims in item text, MedDRA-style codes). WS4 owns this file; extend it, don't weaken it.

Site Signal files (D11, frozen by the sap-v1 tag): data/signal_rules.json and data/site_queries.json have
exactly the docs/02 schemas (key names, types); every primary term has G2 and G3 rules in ctcae_rules.json;
synonyms lower-case, trimmed and unique across terms; every not_computed reason and every answer-key key
has a label; query placeholders limited to {site_id} {episode_lines} {subject_id} {term} {episode_date}
{grade}; no name placeholder, seeded name or banned phrase in any template or label.

Flags: --data-dir DIR validates a copy of data/ (agent/ and eval/ inputs still come from the repo);
--no-self-test skips the self-test; --self-test runs only the self-test. By default a passing run on the
repo's own data/ ends with the self-test: temp copies of data/ outside the repo, each with one planted
defect (the first: a banned phrase inserted into the SQ_UNMATCHED_EPISODES body), must make the validator
exit 1, and an unmodified copy must exit 0.
"""
import argparse, json, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
_ap = argparse.ArgumentParser(description="Cross-check the data files (exit 1 on failure).")
_ap.add_argument("--data-dir", type=pathlib.Path, help="validate this copy of data/ instead (never runs the self-test)")
_ap.add_argument("--self-test", action="store_true", help="run only the self-test")
_ap.add_argument("--no-self-test", action="store_true", help="skip the self-test")
ARGS = _ap.parse_args()
DATA = ARGS.data_dir.resolve() if ARGS.data_dir else ROOT / "data"


def _path(p: str) -> pathlib.Path:
    """Repo-relative path; data/ files resolve under --data-dir when given."""
    return DATA / p.removeprefix("data/") if p.startswith("data/") else ROOT / p


J = lambda p: json.loads(_path(p).read_text(encoding="utf-8"))
errors: list[str] = []
fail = errors.append

items = J("data/symptom_items.json"); scripts = J("data/scripts.json"); rf = J("data/red_flags.json")
rules = J("data/ctcae_rules.json"); plan = J("data/plan.json"); pats = J("data/patients.json")
tools = J("agent/tools.json"); variants = J("agent/variants.json"); personas = J("eval/personas.json")
I, scales = items["items"], items["scales"]

for c in plan["items"]:
    if c not in I: fail(f"plan item {c} missing")
rf_ids = {r["id"] for r in rf["red_flags"]}
for r in plan["red_flag_ids"]:
    if r not in rf_ids: fail(f"plan red flag {r} missing")

all_opts = {"unknown"}
for code, it in I.items():
    sc = it["scale"]
    if sc not in scales: fail(f"{code}: unknown scale {sc}"); continue
    all_opts |= set(scales[sc].get("options", []))
    if "say_script" in it:
        if it["say_script"] not in scripts["lines"]: fail(f"{code}: say_script missing")
    else:
        for l in ("en", "es"):
            if not it.get("text", {}).get(l): fail(f"{code}: text.{l} missing")
    for l in ("en", "es"):
        if "options_say" in it and not it["options_say"].get(l): fail(f"{code}: options_say.{l} missing")
    for f in it.get("followups", []):
        if f["item"] not in I: fail(f"{code}: follow-up {f['item']} missing")
        for v in f["when"]["in"]:
            if v not in scales[sc].get("options", []): fail(f"{code}: follow-up value {v} not in scale {sc}")

KNOWN_PH = {"study_team_name", "patient_first_name", "caregiver_name", "options"}
for k, v in scripts["lines"].items():
    for l in ("en", "es"):
        if not v.get(l): fail(f"script {k}.{l} missing")
        for ph in re.findall(r"\{(\w+)\}", v.get(l, "")):
            if ph not in KNOWN_PH: fail(f"script {k}: unknown placeholder {{{ph}}}")
    if re.search(r"\b911\b|\b988\b", json.dumps(v)): fail(f"script {k}: write 9-1-1 / 9-8-8")

def walk(cond, where):
    if "any" in cond or "all" in cond:
        for c in cond.get("any", []) + cond.get("all", []): walk(c, where)
    elif "item" in cond:
        it = I.get(cond["item"])
        if not it: fail(f"{where}: item {cond['item']} missing"); return
        opts = scales[it["scale"]].get("options", [])
        for v in ([cond["eq"]] if "eq" in cond else []) + cond.get("in", []):
            if v not in opts: fail(f"{where}: {cond['item']} value {v} not in scale")
    elif "derived" in cond:
        if cond["derived"] not in rules["derived_inputs"]: fail(f"{where}: unknown derived {cond['derived']}")
    else:
        fail(f"{where}: bad condition {cond}")

for r in rf["red_flags"]:
    if r["level"] not in rf["levels"]: fail(f"{r['id']}: bad level")
    if r.get("rule"): walk(r["rule"], r["id"])
    if r.get("say_script") and r["say_script"] not in scripts["lines"]: fail(f"{r['id']}: say_script missing")
    if re.search(r"\{(first_name|name|last_name)\}", r["page_phrase_en"]): fail(f"{r['id']}: page phrase must not contain names")
for ru in rules["rules"]:
    walk(ru["when"], ru["id"])
    if ru["term"] not in rules["terms"]: fail(f"{ru['id']}: term missing from catalog")

props = tools["tools"][0]["api_schema"]["request_body_schema"]["properties"]
enum = set(props["option_code"]["enum"])
if enum != all_opts: fail(f"record_answer option enum mismatch: missing {all_opts - enum}, extra {enum - all_opts}")
prompt = (ROOT / "agent/prompt.md").read_text(encoding="utf-8")
for o in sorted(all_opts):
    if f"`{o}`" not in prompt: fail(f"agent/prompt.md does not list option `{o}`")
for ph in ("${RED_FLAG_LIST}", "{{pace_instructions}}", "{{language_name}}", "{{patient_first_name}}", "{{caregiver_name}}", "{{study_team_name}}"):
    if ph not in prompt: fail(f"agent/prompt.md missing {ph}")

terms = set(rules["terms"]) | {"Chest pain"}
grid: dict = {}
for p in personas["personas"]:
    grid[(p["language"], p["pace"])] = grid.get((p["language"], p["pace"]), 0) + 1
    for f in p["expected"]["red_flags"]:
        if f not in rf_ids: fail(f"{p['id']}: unknown red flag {f}")
    for a in p["expected"]["ae"]:
        if a["term"] not in terms: fail(f"{p['id']}: unknown term {a['term']}")
if sorted(grid.values()) != [5, 5, 5, 5]: fail(f"persona grid not 5x4: {grid}")

ids = [p["id"] for p in pats["patients"]]
if len(ids) != len(set(ids)): fail("duplicate patient ids")
for p in pats["patients"]:
    if p["language"] not in ("en", "es") or p["pace"] not in ("standard", "extra_time"): fail(f"{p['id']}: bad language/pace")
    if not str(p["phone_e164"]).startswith("+1555555"): fail(f"{p['id']}: real-looking phone number in committed seed")
if set(variants["variants"]) != {"en-standard", "en-extra_time", "es-standard", "es-extra_time"}: fail("agent variants incomplete")

if "PRO-CTCAE" in json.dumps(I): fail("item text mentions PRO-CTCAE (our wording is not PRO-CTCAE)")
if re.search(r"\b10\d{6}\b", json.dumps(rules)): fail("MedDRA-style code found in ctcae_rules.json")

# ---------------------------------------------------------------------------------------------------------
# Site Signal data files (D11): data/signal_rules.json and data/site_queries.json.
# Schemas: docs/02-data-model.md § Files behind Site Signal (exact key names). Values: docs/11 §4-§8.
# Text rules: docs/10-site-signal.md §6.1, §6.4 and §7.3. Frozen with docs/11 by the sap-v1 tag.
# ---------------------------------------------------------------------------------------------------------
import unicodedata  # noqa: E402
from typing import Literal  # noqa: E402

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model  # noqa: E402

NOT_COMPUTED_REASONS = ("error", "integrated_mode", "low_coverage", "insufficient_patients",
                        "insufficient_episodes", "study_below_min_sites")  # docs/11 §7, in check order
ANSWER_KEY_PLANTED = ("gross_under", "under_50", "under_25", "language_gap")  # docs/11 §11.4, not honest
ANSWER_KEY_HONEST = ("decoy_healthy_casemix", "honest_low_diligence", "low_coverage", "small_site", "honest")
RESPONSE_CODES = ("entered_now", "recorded_as_medical_history", "recorded_under_other_term",
                  "not_an_ae_per_investigator", "other")  # docs/03 §5.4
# docs/02 minimum list; the file may add phrases, never drop these.
REQUIRED_BANNED = {"under-report", "underreport", "fraud", "misconduct", "failed to", "you must",
                   "should treat", "dose", "discontinue"}
QUERY_TEMPLATE = "SQ_UNMATCHED_EPISODES"
BODY_PLACEHOLDERS = frozenset({"site_id", "episode_lines"})
LINE_PLACEHOLDERS = frozenset({"subject_id", "term", "episode_date", "grade"})
# docs/10 §6.4 content rules: data completeness only, review source documents, enter or explain, not a finding.
BODY_MUST_SAY = ("source documents", "either enter the event or", "data-completeness request only",
                 "not a finding about the site", "does not concern clinical management")
LINE_MUST_SAY = ("provisional grade", "rule-graded")
PH = re.compile(r"\{([^{}]*)\}")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _En(_Strict):
    en: str = Field(min_length=1)


class _Episode(_Strict):
    gap_days: int = Field(ge=1)
    worsened_opens_new: bool


class _Window(_Strict):
    id: str = Field(pattern=r"^SE\d+$")
    window_days: int = Field(ge=0)
    lower_tolerance_days: int = Field(ge=0)


class _Match(_Strict):
    window_days: int = Field(ge=0)
    lower_anchor: Literal["last_negative_call"]
    lower_tolerance_days: int = Field(ge=0)
    sensitivity: list[_Window] = Field(min_length=1)
    one_to_one: bool
    exclude_origins: list[Literal["site", "between_visits"]]
    term_synonyms: dict[str, list[str]]


class _Evaluability(_Strict):
    entry_window_days: int = Field(ge=0)
    next_visit_plus_days: int = Field(ge=0)


class _Paged(_Strict):
    levels: list[str] = Field(min_length=1)
    policy: Literal["exclude_from_oe_report_separately"]
    proximity_days: int = Field(ge=0)


class _MinimumData(_Strict):
    min_sites: int = Field(ge=2)
    min_patients: int = Field(ge=1)
    min_evaluable_episodes: int = Field(ge=1)
    min_call_completion: float = Field(gt=0, le=1)


class _IntegratedMode(_Strict):
    site_roles: list[Literal["coordinator", "investigator"]] = Field(min_length=1)


class _Look(_Strict):
    per_site_alpha: float = Field(gt=0, lt=0.5)


class _Watch(_Strict):
    family_wise_alpha: float = Field(gt=0, lt=0.5)


class _Tiers(_Strict):
    look: _Look
    watch: _Watch


class _Overdispersion(_Strict):
    method: Literal["additive"]
    winsor: list[float] = Field(min_length=2, max_length=2)


_Reasons = create_model("_Reasons", __base__=_Strict, **{k: (_En, ...) for k in NOT_COMPUTED_REASONS})
_AnswerKey = create_model("_AnswerKey", __base__=_Strict,
                          **{k: (_En, ...) for k in ANSWER_KEY_PLANTED + ANSWER_KEY_HONEST})


class _Labels(_Strict):
    watch: _En
    look: _En
    none: _En
    not_computed: _En
    footer: _En
    footer_expected_false_look: _En
    reasons: _Reasons
    answer_key: _AnswerKey


class _SignalRules(_Strict):
    about: str = Field(alias="_about", min_length=1)
    version: int = Field(ge=1)
    primary_terms: list[str] = Field(min_length=1)
    min_grade: int = Field(ge=1)
    grade_source: str = Field(min_length=1)
    ungraded_terms_policy: Literal["context_only"]
    episode: _Episode
    match: _Match
    evaluability: _Evaluability
    paged: _Paged
    minimum_data: _MinimumData
    integrated_mode: _IntegratedMode
    tiers: _Tiers
    overdispersion: _Overdispersion
    labels: _Labels


class _QueryTemplate(_Strict):
    title_en: str = Field(min_length=1)
    body_en: str = Field(min_length=1)
    episode_line_en: str = Field(min_length=1)


class _ResponseCode(_Strict):
    code: str = Field(min_length=1)
    label_en: str = Field(min_length=1)


class _SiteQueries(_Strict):
    about: str = Field(alias="_about", min_length=1)
    version: int = Field(ge=1)
    templates: dict[str, _QueryTemplate] = Field(min_length=1)
    response_codes: list[_ResponseCode] = Field(min_length=1)
    banned_phrases_en: list[str] = Field(min_length=1)


def _load_model(rel: str, model: type[BaseModel]):
    try:
        raw_text = _path(rel).read_text(encoding="utf-8")
        obj = model.model_validate(json.loads(raw_text))
    except (OSError, ValueError) as e:  # missing file or invalid JSON (JSONDecodeError is a ValueError)
        if isinstance(e, ValidationError):
            for er in e.errors():
                fail(f"{rel}: {'.'.join(map(str, er['loc'])) or '(root)'}: {er['msg']}")
        else:
            fail(f"{rel}: cannot read ({e})")
        return None
    if re.search(r"\b10\d{6}\b", raw_text): fail(f"{rel}: MedDRA-style code found")
    return obj


sr = _load_model("data/signal_rules.json", _SignalRules)
sq = _load_model("data/site_queries.json", _SiteQueries)
banned = [b.lower() for b in sq.banned_phrases_en] if sq else sorted(REQUIRED_BANNED)


def _fold(s: str) -> str:
    """Lower-case and strip accents, so an unaccented spelling still matches a seeded name."""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


seeded_names = sorted({_fold(n) for p in pats["patients"]
                       for n in (p.get("first_name"), p.get("last_name"), p.get("caregiver_name")) if n})


def _is_normalized(s: str) -> bool:
    """Lower-case, trimmed, single-spaced, non-empty."""
    return bool(s) and s == " ".join(s.split()).lower()


def check_text(where: str, text: str, allowed: frozenset = frozenset(), required: frozenset = frozenset()) -> None:
    """Placeholders limited to `allowed` (all of `required` present), no name placeholder, no stray brace,
    no banned phrase (case-insensitive), no seeded patient or caregiver name (whole word)."""
    found = PH.findall(text)
    for ph in found:
        if "name" in ph.lower():
            fail(f"{where}: name placeholder {{{ph}}} (subject IDs only)")
        elif ph not in allowed:
            fail(f"{where}: placeholder {{{ph}}} not allowed here (allowed: {sorted(allowed) or 'none'})")
    for ph in sorted(required - set(found)):
        fail(f"{where}: missing placeholder {{{ph}}}")
    if re.search(r"[{}]", PH.sub("", text)):
        fail(f"{where}: stray brace outside a placeholder")
    low = text.lower()
    for b in banned:
        if b in low: fail(f"{where}: banned phrase {b!r}")
    folded = _fold(text)
    for n in seeded_names:
        if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", folded):
            fail(f"{where}: contains a seeded patient or caregiver name (subject IDs only)")


n_synonyms = 0
if sr:
    W = "signal_rules.json"
    grades_by_term: dict[str, set] = {}
    for ru in rules["rules"]: grades_by_term.setdefault(ru["term"], set()).add(ru["grade"])
    if len(set(sr.primary_terms)) != len(sr.primary_terms): fail(f"{W}: duplicate primary term")
    for t in sr.primary_terms:
        g = grades_by_term.get(t, set())
        for need in (2, 3):
            if need not in g: fail(f"{W}: primary term {t} has no G{need} rule in data/ctcae_rules.json")
        if sr.min_grade not in g: fail(f"{W}: primary term {t} has no rule at min_grade {sr.min_grade}")
    if "data/ctcae_rules.json" not in sr.grade_source: fail(f"{W}: grade_source must name data/ctcae_rules.json")
    syn = sr.match.term_synonyms
    if set(syn) != set(sr.primary_terms):
        fail(f"{W}: match.term_synonyms keys {sorted(syn)} != primary_terms {sorted(sr.primary_terms)}")
    owner: dict[str, str] = {}
    for term, words in syn.items():
        if not words: fail(f"{W}: no synonyms for {term}")
        if term.lower() not in words: fail(f"{W}: synonyms of {term} must include {term.lower()!r}")
        for w in words:
            n_synonyms += 1
            if not _is_normalized(w): fail(f"{W}: synonym {w!r} ({term}) must be lower-case and trimmed")
            if w in owner:
                fail(f"{W}: synonym {w!r} listed under {owner[w]} and {term} (must be unique across terms)")
            else:
                owner[w] = term
    se_ids = [s.id for s in sr.match.sensitivity]
    if len(set(se_ids)) != len(se_ids): fail(f"{W}: duplicate sensitivity window id")
    if "between_visits" not in sr.match.exclude_origins:
        fail(f"{W}: match.exclude_origins must exclude between_visits (stream independence, REQ-024)")
    for lv in sr.paged.levels:
        if not rf["levels"].get(lv, {}).get("page"): fail(f"{W}: paged level {lv!r} is not a paging level in red_flags.json")
    lo, hi = sr.overdispersion.winsor
    if not 0 <= lo < hi <= 1: fail(f"{W}: overdispersion.winsor must be 0 <= low < high <= 1")
    L, md = sr.labels, sr.minimum_data
    flat = {k: getattr(L, k).en for k in ("watch", "look", "none", "not_computed", "footer")}
    flat.update({f"reasons.{k}": getattr(L.reasons, k).en for k in NOT_COMPUTED_REASONS})
    flat.update({f"answer_key.{k}": getattr(L.answer_key, k).en for k in ANSWER_KEY_PLANTED + ANSWER_KEY_HONEST})
    for k, text in flat.items(): check_text(f"{W}: labels.{k}", text)
    fe = frozenset({"expected_false_look"})
    check_text(f"{W}: labels.footer_expected_false_look", L.footer_expected_false_look.en, fe, fe)
    # A reason label states the rule it reports, so any number in it must be that rule's minimum_data value.
    reason_numbers = {"low_coverage": {str(round(md.min_call_completion * 100))},
                      "insufficient_patients": {str(md.min_patients)},
                      "insufficient_episodes": {str(md.min_evaluable_episodes)},
                      "study_below_min_sites": {str(md.min_sites)}}
    for k in NOT_COMPUTED_REASONS:
        text = getattr(L.reasons, k).en
        if not text.endswith(".") or re.search(r"[.!?]\s", text):
            fail(f"{W}: labels.reasons.{k} must be one plain sentence")
        stray = set(re.findall(r"\d+(?:\.\d+)?", text)) - reason_numbers.get(k, set())
        if stray: fail(f"{W}: labels.reasons.{k} quotes {sorted(stray)}, which is not its minimum_data value")
    for k in ANSWER_KEY_PLANTED:
        if not getattr(L.answer_key, k).en.startswith("Planted"):
            fail(f"{W}: labels.answer_key.{k} is planted (docs/11 §11.4) and must read 'Planted...'")
    for k in ANSWER_KEY_HONEST:
        if not getattr(L.answer_key, k).en.startswith("Honest"):
            fail(f"{W}: labels.answer_key.{k} is honest by the key (docs/11 §11.4) and must read 'Honest...'")

if sq:
    W = "site_queries.json"
    if QUERY_TEMPLATE not in sq.templates: fail(f"{W}: template {QUERY_TEMPLATE} missing")
    for tid, t in sq.templates.items():
        if not re.fullmatch(r"SQ_[A-Z0-9_]+", tid): fail(f"{W}: template id {tid!r} must look like SQ_NAME")
        check_text(f"{W}: {tid}.title_en", t.title_en)
        check_text(f"{W}: {tid}.body_en", t.body_en, BODY_PLACEHOLDERS, BODY_PLACEHOLDERS)
        check_text(f"{W}: {tid}.episode_line_en", t.episode_line_en, LINE_PLACEHOLDERS, LINE_PLACEHOLDERS)
        for field in ("title_en", "episode_line_en"):
            if "\n" in getattr(t, field): fail(f"{W}: {tid}.{field} must be one line")
        for s in BODY_MUST_SAY:
            if s not in t.body_en.lower(): fail(f"{W}: {tid}.body_en must say {s!r} (docs/10 §6.4)")
        for s in LINE_MUST_SAY:
            if s not in t.episode_line_en.lower(): fail(f"{W}: {tid}.episode_line_en must say {s!r}")
    codes = [c.code for c in sq.response_codes]
    if len(set(codes)) != len(codes): fail(f"{W}: duplicate response code")
    if set(codes) != set(RESPONSE_CODES):
        fail(f"{W}: response codes {sorted(codes)} != {sorted(RESPONSE_CODES)} (docs/03 §5.4)")
    for c in sq.response_codes: check_text(f"{W}: response_codes.{c.code}.label_en", c.label_en)
    for b in sq.banned_phrases_en:
        if not _is_normalized(b): fail(f"{W}: banned phrase {b!r} must be lower-case and trimmed")
    if len(set(sq.banned_phrases_en)) != len(sq.banned_phrases_en): fail(f"{W}: duplicate banned phrase")
    for b in sorted(REQUIRED_BANNED - set(sq.banned_phrases_en)):
        fail(f"{W}: banned_phrases_en must keep {b!r} (docs/02)")


def _self_test() -> int:
    """Validate temp copies of data/ (outside the repo), each with one planted defect, in subprocesses.
    Every defect must make the validator exit 1 with the expected message; an unmodified copy must exit 0."""
    import shutil
    import subprocess
    import tempfile
    from concurrent.futures import ThreadPoolExecutor

    def edit(rel: str, fn):
        """Mutation that loads data/<rel> from the copy, applies fn(obj, copy_dir) and writes it back."""
        def apply(d: pathlib.Path) -> None:
            p = d / rel
            obj = json.loads(p.read_text(encoding="utf-8"))
            fn(obj, d)
            p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return apply

    def read(d: pathlib.Path, rel: str):
        return json.loads((d / rel).read_text(encoding="utf-8"))

    def first_banned(d: pathlib.Path) -> str:  # taken from the copy, so no banned phrase is spelled out here
        return read(d, "site_queries.json")["banned_phrases_en"][0]

    def template(q) -> dict:
        return q["templates"][QUERY_TEMPLATE]

    def banned_into_body(q, d) -> None:
        t = template(q)
        t["body_en"] = t["body_en"].replace("{episode_lines}", f"Note: {first_banned(d)}.\n{{episode_lines}}", 1)

    def banned_into_answer_key(r, d) -> None:
        r["labels"]["answer_key"]["honest_low_diligence"]["en"] = f"Honest ({first_banned(d)})"

    def append(field: str, suffix: str):
        return edit("site_queries.json", lambda q, d: template(q).update({field: template(q)[field] + suffix}))

    def name_into_body(q, d) -> None:  # a seeded last name, written without its accents
        t = template(q)
        t["body_en"] += " " + _fold(read(d, "patients.json")["patients"][0]["last_name"]).title()

    def synonym_shared(r, d) -> None:
        syn, terms = r["match"]["term_synonyms"], r["primary_terms"]
        syn[terms[-1]].append(syn[terms[0]][0])

    def drop_g3_rule(c, d) -> None:
        term = read(d, "signal_rules.json")["primary_terms"][-1]
        c["rules"] = [ru for ru in c["rules"] if not (ru["term"] == term and ru["grade"] == 3)]

    reason, ak_key = NOT_COMPUTED_REASONS[-1], ANSWER_KEY_HONEST[-2]
    cases = [  # (description, mutation, expected exit code, expected text in the output)
        ("unmodified copy", None, 0, "site signal OK"),
        (f"banned phrase inserted into the {QUERY_TEMPLATE} body", edit("site_queries.json", banned_into_body), 1,
         f"{QUERY_TEMPLATE}.body_en: banned phrase"),
        ("name placeholder in the episode line", append("episode_line_en", " {first_name}"), 1, "name placeholder"),
        ("placeholder outside the allowed set in the body", append("body_en", " {data_cut}"), 1, "not allowed here"),
        ("stray brace in the body", append("body_en", " }"), 1, "stray brace"),
        ("a seeded patient's name in the body", edit("site_queries.json", name_into_body), 1, "seeded patient"),
        ("a not_computed reason without a label",
         edit("signal_rules.json", lambda r, d: r["labels"]["reasons"].pop(reason)), 1, f"labels.reasons.{reason}"),
        ("an answer-key key without a display label",
         edit("signal_rules.json", lambda r, d: r["labels"]["answer_key"].pop(ak_key)), 1, f"labels.answer_key.{ak_key}"),
        ("banned phrase in an answer-key display label", edit("signal_rules.json", banned_into_answer_key), 1,
         "labels.answer_key.honest_low_diligence: banned phrase"),
        ("an unknown key in signal_rules.json",
         edit("signal_rules.json", lambda r, d: r["match"].update(window_days_extra=1)), 1, "Extra inputs"),
        ("an upper-case synonym",
         edit("signal_rules.json", lambda r, d: r["match"]["term_synonyms"][r["primary_terms"][0]].append("Upper Case")),
         1, "must be lower-case"),
        ("a synonym shared by two terms", edit("signal_rules.json", synonym_shared), 1, "unique across terms"),
        ("a primary term without a G3 rule in ctcae_rules.json", edit("ctcae_rules.json", drop_g3_rule), 1,
         "has no G3 rule"),
    ]
    base = pathlib.Path(tempfile.mkdtemp(prefix="bv-validate-selftest-")).resolve()
    try:
        if base.is_relative_to(ROOT):
            print(f"self-test FAIL: temp dir {base} is inside the repo"); return 1
        print(f"self-test: {len(cases)} temp copies of data/ under {base} (outside the repo)")

        def run(i: int):
            desc, mutate, want_code, want_text = cases[i]
            d = base / f"case{i:02d}" / "data"
            shutil.copytree(DATA, d, ignore=shutil.ignore_patterns("local", "*.local.json", "__pycache__"))
            if mutate: mutate(d)
            p = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), "--data-dir", str(d)],
                               capture_output=True, text=True, timeout=300, cwd=base)
            out = p.stdout + p.stderr
            return desc, p.returncode, want_code, want_text in out, out

        bad = 0
        with ThreadPoolExecutor(max_workers=4) as ex:
            for desc, code, want_code, has_text, out in ex.map(run, range(len(cases))):
                ok = code == want_code and has_text
                bad += not ok
                print(f"  {'ok  ' if ok else 'FAIL'} exit={code} (expected {want_code}): {desc}")
                if not ok: print("       " + "\n       ".join(out.strip().splitlines()[-8:]))
        print(f"self-test {'OK' if not bad else 'FAILED'}: {len(cases) - bad}/{len(cases)} cases behave as expected")
        return 1 if bad else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


if ARGS.self_test:
    sys.exit(_self_test())
if errors:
    print("\n".join("FAIL: " + e for e in errors)); sys.exit(1)
print(f"data OK: {len(I)} items, {len(rf_ids)} red flags, {len(rules['rules'])} grading rules, {len(personas['personas'])} personas")
print(f"site signal OK: {len(sr.primary_terms)} primary terms with G2 and G3 rules, {n_synonyms} synonyms, "
      f"{len(NOT_COMPUTED_REASONS)} not_computed reasons and {len(ANSWER_KEY_PLANTED + ANSWER_KEY_HONEST)} answer-key "
      f"keys labelled, {len(sq.templates)} query template(s), {len(sq.response_codes)} response codes, "
      f"{len(sq.banned_phrases_en)} banned phrases")
if ARGS.data_dir is None and not ARGS.no_self_test:
    sys.exit(_self_test())
