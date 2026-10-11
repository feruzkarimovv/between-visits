"""Cross-checks every clinical/seed data file. Run: uv run python data/validate_data.py (exit 1 on failure).

Checks: plan items and red flags exist; every item has EN+ES text (or a script); follow-ups and rule
conditions reference real items and scale values; scripts exist in both languages with known
placeholders and dash-written emergency numbers; tool option enum == all scale options; the agent
prompt lists every option; personas reference real flags/terms; 2x2 persona grid; no licensed content
(PRO-CTCAE claims in item text, MedDRA-style codes). WS4 owns this file; extend it, don't weaken it.

Grade bands (D9): per term in ctcae_rules.json the grades are consecutive and the bands are contiguous and do
not overlap (numeric bands meet exactly, or at the next whole number on a count input; option bands are runs of
the item's scale in grade order, with no option in two grades). data/mutation_probe.py and
backend/tests/test_rule_boundaries.py pin each threshold itself.

Site Signal files (D11, frozen by the sap-v1 tag): data/signal_rules.json and data/site_queries.json have
exactly the docs/02 schemas (key names, types); every primary term has G2 and G3 rules in ctcae_rules.json;
synonyms lower-case, trimmed and unique across terms; every not_computed reason and every answer-key key
has a label; query placeholders limited to {site_id} {episode_lines} {subject_id} {term} {episode_date}
{grade}; no name placeholder, seeded name or banned phrase in any template or label.

Product-name guard (D8, CLAUDE.md rule 8: the study drug is named by class only): every text file from
`git ls-files -co --exclude-standard` (binaries and lockfiles skipped) is lower-cased and split into
[a-z0-9]+ tokens; a token, or two tokens joined across one separator character (a hyphenated or spaced
product code), whose sha256 is in PRODUCT_NAME_SHA256 fails with file:line. Only the hashes are in git, and
the guard never prints the text that matched. It runs on the repo's own data/ only (not with --data-dir).

Flags: --data-dir DIR validates a copy of data/ (agent/ and eval/ inputs still come from the repo);
--no-self-test skips the self-test; --self-test runs only the self-test. By default a passing run on the
repo's own data/ ends with the self-test: temp copies of data/ outside the repo, each with one planted
defect (the first: a banned phrase inserted into the SQ_UNMATCHED_EPISODES body), must make the validator
exit 1, and an unmodified copy must exit 0; for the product-name guard, the denylist is swapped for the hash
of a random dummy token and a temp file containing that token must fail (--guard-file/--guard-sha256 are
for this self-test only).
"""
import argparse, hashlib, json, re, subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
_ap = argparse.ArgumentParser(description="Cross-check the data files (exit 1 on failure).")
_ap.add_argument("--data-dir", type=pathlib.Path, help="validate this copy of data/ instead (never runs the self-test)")
_ap.add_argument("--self-test", action="store_true", help="run only the self-test")
_ap.add_argument("--no-self-test", action="store_true", help="skip the self-test")
_ap.add_argument("--guard-file", type=pathlib.Path, action="append",
                 help="self-test only: run just the product-name guard over this file (repeatable)")
_ap.add_argument("--guard-sha256", action="append",
                 help="self-test only: with --guard-file, use this denylist hash instead (repeatable)")
ARGS = _ap.parse_args()
DATA = ARGS.data_dir.resolve() if ARGS.data_dir else ROOT / "data"

# ---------------------------------------------------------------------------------------------------------
# Product-name guard (D8). Hashes of lower-case [a-z0-9]+ tokens, computed locally; the names themselves are
# never written to any file, commit message, test or log.
# ---------------------------------------------------------------------------------------------------------
PRODUCT_NAME_SHA256 = frozenset({
    "fce00fa0a39a9ff866ef2f2e523f5767fd5695bba8680942a331b3ac067c6ccc",  # brand (former red_flags.json citations)
    "153409d26150cce4333108ae3d3dec073cd24f6fd395eb4f5a8e11f7b3af0b50",  # product code (former study.json registry_title)
    "21fb1ce50629fcd3119baf2fd723545f071b63af38b89610df8991378a485b1d",  # generic name (supplied by the team lead)
})
LOCKFILES = frozenset({"uv.lock", "poetry.lock", "Pipfile.lock", "package-lock.json", "npm-shrinkwrap.json",
                       "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "Cargo.lock"})
_TOKEN = re.compile(r"[a-z0-9]+")


def _repo_files() -> list[pathlib.Path]:
    """Every file git tracks or would track (tracked + untracked, minus ignored), relative to ROOT."""
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True,
                         check=True, timeout=60).stdout.decode("utf-8", "surrogateescape")
    return [pathlib.Path(p) for p in sorted(set(out.split("\0"))) if p]


def product_name_guard(files: list[pathlib.Path], denylist: frozenset, report) -> int:
    """Report `file:line` for every line holding a denylisted token; returns the number of files scanned.
    Skips lockfiles, symlinks, directories, missing files and binaries (a NUL byte). Prints no matched text."""
    memo: dict[str, bool] = {}

    def denied(tok: str) -> bool:
        if tok not in memo: memo[tok] = hashlib.sha256(tok.encode()).hexdigest() in denylist
        return memo[tok]

    scanned = 0
    for rel in files:
        p = rel if rel.is_absolute() else ROOT / rel
        if rel.name in LOCKFILES or p.is_symlink() or not p.is_file(): continue
        raw = p.read_bytes()
        if b"\0" in raw: continue
        scanned += 1
        for n, line in enumerate(raw.decode("utf-8", "replace").lower().splitlines(), 1):
            toks = list(_TOKEN.finditer(line))
            hit = any(denied(m.group()) for m in toks) or any(  # also two tokens split by one character
                b.start() - a.end() == 1 and denied(a.group() + b.group()) for a, b in zip(toks, toks[1:]))
            if hit: report(f"product-name guard: {rel}:{n}: a product brand name, product code or generic name "
                           f"(sha256 denylist); name the drug by class only (CLAUDE.md rule 8)")
    return scanned


if ARGS.guard_file:  # self-test hook: the guard alone, over the given files
    _hits: list[str] = []
    _n = product_name_guard([f.resolve() for f in ARGS.guard_file],
                            frozenset(ARGS.guard_sha256 or PRODUCT_NAME_SHA256), _hits.append)
    print("\n".join("FAIL: " + h for h in _hits) or f"product names: 0 hits in {_n} files")
    sys.exit(1 if _hits else 0)


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

# ---------------------------------------------------------------------------------------------------------
# Grade-band contiguity (D9): per term, the grade bands are contiguous and do not overlap, so a value gets at
# most one grade and nothing between two graded bands is left ungraded. A term's grades are consecutive.
# Numeric bands (each rule one gte/gt/lte/lt leaf, all on one input): consecutive grades meet exactly
# (lte t then gt t, or lt t then gte t); on a count input, whose answers are whole numbers, lte a then gte a+1
# also meets. Option bands (each rule one eq/in leaf, all on one item): no option in two grades, and each
# grade's options are a run of the item's scale that follows the previous grade's run.
# ---------------------------------------------------------------------------------------------------------
DISCRETE_SCALES = frozenset({"count"})  # whole-number answers
W_RULES = "ctcae_rules.json"


def _leaf_items(leaf) -> set:
    """Items a numeric leaf reads (a derived input: the item codes named in `derived_inputs`)."""
    if "item" in leaf: return {leaf["item"]}
    return {c for c in re.findall(r"\b[A-Z][A-Z0-9_]+\b", rules["derived_inputs"].get(leaf["derived"], "")) if c in I}


def _numeric_band(where: str, w: dict, discrete: bool):
    """(low, low inclusive, high, high inclusive), None for an open end; count bands become closed integer
    ranges. Returns None (after failing) for a malformed band."""
    lo = hi = None; lo_in = hi_in = True
    for op in ("gte", "gt", "lte", "lt"):
        if op not in w: continue
        t = w[op]
        if isinstance(t, bool) or not isinstance(t, (int, float)):
            fail(f"{W_RULES}: {where}: {op} must be a number"); return None
        if discrete and not isinstance(t, int):
            fail(f"{W_RULES}: {where}: {op} {t} on a count input must be a whole number"); return None
        if op in ("gte", "gt"):
            if lo is not None: fail(f"{W_RULES}: {where}: two lower edges"); return None
            lo, lo_in = t, op == "gte"
        else:
            if hi is not None: fail(f"{W_RULES}: {where}: two upper edges"); return None
            hi, hi_in = t, op == "lte"
    if discrete:  # closed integer range
        if lo is not None and not lo_in: lo, lo_in = lo + 1, True
        if hi is not None and not hi_in: hi, hi_in = hi - 1, True
    if lo is not None and hi is not None and (lo > hi or (lo == hi and not (lo_in and hi_in))):
        fail(f"{W_RULES}: {where}: empty band"); return None
    return lo, lo_in, hi, hi_in


def _edge(v, inclusive: bool) -> str:
    return f"{v} ({'inclusive' if inclusive else 'exclusive'})"


def check_grade_bands() -> int:
    """Fail on any term whose grade bands overlap, leave a gap, or skip a grade; returns the number of terms."""
    by_term: dict = {}
    for ru in rules["rules"]: by_term.setdefault(ru["term"], []).append(ru)
    for term, rs in by_term.items():
        rs = sorted(rs, key=lambda r: r["grade"])
        grades = [r["grade"] for r in rs]
        if len(set(grades)) != len(grades): fail(f"{W_RULES}: {term}: two rules for one grade {grades}"); continue
        if grades != list(range(grades[0], grades[0] + len(grades))):
            fail(f"{W_RULES}: {term}: grades {grades} are not consecutive (a band is missing)"); continue
        whens = [r["when"] for r in rs]
        numeric = all(any(op in w for op in ("gte", "gt", "lte", "lt")) and ("item" in w or "derived" in w)
                      and not {"eq", "in", "any", "all"} & set(w) for w in whens)
        options = all(set(w) in ({"item", "eq"}, {"item", "in"}) for w in whens)
        if numeric and len({(w.get("item"), w.get("derived")) for w in whens}) == 1:
            items_read = _leaf_items(whens[0])
            discrete = bool(items_read) and all(I[c]["scale"] in DISCRETE_SCALES for c in items_read)
            bands = [_numeric_band(r["id"], r["when"], discrete) for r in rs]
            if None in bands: continue
            for g, (_, _, a_hi, a_hi_in), (b_lo, b_lo_in, _, _) in zip(grades, bands, bands[1:]):
                ga, gb = f"G{g}", f"G{g + 1}"
                if a_hi is None or b_lo is None:
                    fail(f"{W_RULES}: {term}: {ga} and {gb} bands overlap ({ga} has no upper edge or {gb} no lower edge)")
                    continue
                span = f"({ga} up to {_edge(a_hi, a_hi_in)}, {gb} from {_edge(b_lo, b_lo_in)})"
                if a_hi > b_lo or (a_hi == b_lo and a_hi_in and b_lo_in):
                    fail(f"{W_RULES}: {term}: {ga} and {gb} bands overlap {span}")
                elif not (b_lo == a_hi + 1 if discrete else a_hi == b_lo and a_hi_in != b_lo_in):
                    fail(f"{W_RULES}: {term}: gap between the {ga} and {gb} bands {span}")
        elif options and len({w["item"] for w in whens}) == 1:
            item = whens[0]["item"]
            scale_opts = scales.get(I[item]["scale"], {}).get("options", []) if item in I else []
            runs, owner = [], {}
            for r in rs:
                opts = [r["when"]["eq"]] if "eq" in r["when"] else list(r["when"]["in"])
                for o in opts:
                    if o in owner:
                        fail(f"{W_RULES}: {term}: option {o!r} of {item} is in G{owner[o]} and G{r['grade']} (bands overlap)")
                    owner[o] = r["grade"]
                idx = sorted(scale_opts.index(o) for o in opts if o in scale_opts)  # unknown options: walk() reports them
                if idx and idx != list(range(idx[0], idx[0] + len(idx))):
                    fail(f"{W_RULES}: {term}: the G{r['grade']} options of {item} are not a run of its scale")
                runs.append((r["grade"], idx))
            for (ga, ia), (gb, ib) in zip(runs, runs[1:]):
                if ia and ib and ib[0] != ia[-1] + 1:
                    fail(f"{W_RULES}: {term}: the G{gb} options of {item} do not follow the G{ga} options on its scale "
                         f"(gap between the bands, or bands out of order)")
        else:
            fail(f"{W_RULES}: {term}: cannot check contiguity: each rule must be one numeric leaf on the same input, "
                 f"or one eq/in leaf on the same item (extend data/validate_data.py for other shapes)")
    return len(by_term)


n_band_terms = check_grade_bands()

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
    import secrets
    import shutil
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

    def shift_upper_edge(by: int):  # the first grading rule with an `lte` edge (a band with a higher grade above it)
        def shift(c, d) -> None:
            w = next(ru["when"] for ru in c["rules"] if "lte" in ru["when"])
            w["lte"] += by
        return edit("ctcae_rules.json", shift)

    def option_in_two_grades(c, d) -> None:  # the next grade of an option-graded term takes the previous grade's option
        terms: dict = {}
        for ru in c["rules"]:
            if set(ru["when"]) == {"item", "eq"}: terms.setdefault(ru["term"], []).append(ru)
        rs = sorted(next(v for v in terms.values() if len(v) > 1), key=lambda ru: ru["grade"])
        rs[1]["when"]["eq"] = rs[0]["when"]["eq"]

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
        ("a gap between two grade bands (an upper edge one unit lower)", shift_upper_edge(-1), 1, "gap between the"),
        ("two grade bands overlapping (an upper edge one unit higher)", shift_upper_edge(1), 1, "bands overlap"),
        ("one option graded in two grades", edit("ctcae_rules.json", option_in_two_grades), 1, "(bands overlap)"),
    ]
    # Product-name guard: the denylist is swapped for the hash of a random dummy token (never a real name).
    dummy = "zqx" + secrets.token_hex(5)
    dummy_hash = hashlib.sha256(dummy.encode()).hexdigest()
    filler = "Example study of an anti-PD-1 antibody.\nThe drug is named by class only.\n"
    guard_cases = [  # (description, temp file text, expected exit code, expected text in the output)
        ("product-name guard: temp file with the dummy token (upper case, line 3)",
         filler + f"Dosed with {dummy.upper()} today.\n", 1, "guard.txt:3: a product brand name"),
        ("product-name guard: dummy token split by a hyphen (line 3)",
         filler + f"Code {dummy[:3].upper()}-{dummy[3:]} here.\n", 1, "guard.txt:3: a product brand name"),
        ("product-name guard: same file without the dummy token", filler + "Dosed today.\n", 0,
         "product names: 0 hits in 1 files"),
    ]
    base = pathlib.Path(tempfile.mkdtemp(prefix="bv-validate-selftest-")).resolve()
    try:
        if base.is_relative_to(ROOT):
            print(f"self-test FAIL: temp dir {base} is inside the repo"); return 1
        print(f"self-test: {len(cases)} temp copies of data/ and {len(guard_cases)} product-name guard files "
              f"under {base} (outside the repo)")

        def run(i: int):
            desc, mutate, want_code, want_text = cases[i]
            d = base / f"case{i:02d}" / "data"
            shutil.copytree(DATA, d, ignore=shutil.ignore_patterns("local", "*.local.json", "__pycache__"))
            if mutate: mutate(d)
            p = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), "--data-dir", str(d)],
                               capture_output=True, text=True, timeout=300, cwd=base)
            out = p.stdout + p.stderr
            return desc, p.returncode, want_code, want_text in out, out

        def run_guard(i: int):
            desc, text, want_code, want_text = guard_cases[i]
            f = base / f"guard{i:02d}" / "guard.txt"
            f.parent.mkdir(parents=True)
            f.write_text(text, encoding="utf-8")
            p = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), "--guard-file", str(f),
                                "--guard-sha256", dummy_hash], capture_output=True, text=True, timeout=60, cwd=base)
            out = p.stdout + p.stderr
            # the guard must never echo the text that matched
            return desc, p.returncode, want_code, want_text in out and dummy not in out.lower(), out

        bad = 0
        total = len(cases) + len(guard_cases)
        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(run, range(len(cases)))) + list(ex.map(run_guard, range(len(guard_cases))))
            for desc, code, want_code, has_text, out in results:
                ok = code == want_code and has_text
                bad += not ok
                print(f"  {'ok  ' if ok else 'FAIL'} exit={code} (expected {want_code}): {desc}")
                if not ok: print("       " + "\n       ".join(out.strip().splitlines()[-8:]))
        print(f"self-test {'OK' if not bad else 'FAILED'}: {total - bad}/{total} cases behave as expected")
        return 1 if bad else 0
    finally:
        shutil.rmtree(base, ignore_errors=True)


if ARGS.self_test:
    sys.exit(_self_test())
n_guard_files = 0
if ARGS.data_dir is None:  # the guard covers the repository, so it runs on the repo's own data/ only
    try:
        n_guard_files = product_name_guard(_repo_files(), PRODUCT_NAME_SHA256, fail)
    except (OSError, subprocess.SubprocessError) as e:  # fail closed: no file list means no clean bill
        fail(f"product-name guard: cannot list the repository files with git ls-files ({type(e).__name__})")
if errors:
    print("\n".join("FAIL: " + e for e in errors)); sys.exit(1)
print(f"data OK: {len(I)} items, {len(rf_ids)} red flags, {len(rules['rules'])} grading rules, {len(personas['personas'])} personas")
print(f"grade bands OK: {n_band_terms} terms, bands contiguous and non-overlapping, grades consecutive")
print(f"site signal OK: {len(sr.primary_terms)} primary terms with G2 and G3 rules, {n_synonyms} synonyms, "
      f"{len(NOT_COMPUTED_REASONS)} not_computed reasons and {len(ANSWER_KEY_PLANTED + ANSWER_KEY_HONEST)} answer-key "
      f"keys labelled, {len(sq.templates)} query template(s), {len(sq.response_codes)} response codes, "
      f"{len(sq.banned_phrases_en)} banned phrases")
if ARGS.data_dir is None:
    print(f"product names: 0 hits in {n_guard_files} files")
if ARGS.data_dir is None and not ARGS.no_self_test:
    sys.exit(_self_test())
