"""B17: Site Signal read API (docs/03 §5.1-5.3, §6.1) against the hand-written B16b fixtures.

The fixtures hold placeholder numbers in the shapes of monitoring/out/ ("fixture, not a result"); nothing here
asserts a result. REQ-021 no LLM on the statistics path; REQ-023 no threshold literal in site_signal.py and
thresholds only from thresholds.json; REQ-025 never green (missing or invalid outputs are 503, guarded sites
are not computed with a reason); REQ-026 evidence on every flag; REQ-030 SIMULATED / MEASURED labels (schema
walk; the live site 101 episodes built from the app database are MEASURED and never pooled).
"""

import ast
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import Session

from app import content
from app.config import BACKEND_DIR
from app.ids import new_id
from app.models import Answer, CheckIn, Patient
from app.schemas import SiteSignalRow
from app.services import replay, rules, site_signal
from app.services.checkins import active_plan
from app.timeutil import local_date, utcnow
from tests.conftest import COORD, INVESTIGATOR, SITE_SIGNAL_FIXTURES

CRA = {"X-BV-User": "Sam Rivera", "X-BV-Role": "cra"}
SPONSOR = {"X-BV-User": "Sponsor reviewer", "X-BV-Role": "sponsor"}
SERVICES = BACKEND_DIR / "app" / "services"
SIGNAL_SERVICE = SERVICES / "site_signal.py"
SIGNAL_ROUTER = BACKEND_DIR / "app" / "routers" / "site_signal.py"
TIERS = {"watch", "look", "none", "not_computed"}
REASONS = {"error", "integrated_mode", "low_coverage", "insufficient_patients", "insufficient_episodes",
           "study_below_min_sites"}
ORIGINS = {"SIMULATED", "MEASURED", "MIXED"}
SOURCES = {"live_call", "replay", "synthetic"}
INDICATORS = ("discordance", "rate_kri", "simaerep_classic")
READ_ROUTES = ["/api/sites", "/api/sites/112", "/api/site-signal/answer-key", "/api/site-signal/equity",
               "/api/site-signal/validation"]


def fixture_doc(name: str) -> Any:
    return json.loads((SITE_SIGNAL_FIXTURES / name).read_text(encoding="utf-8"))


def error_code(r) -> str:  # noqa: ANN001
    return r.json()["error"]["code"]


@pytest.fixture
def out_copy(tmp_path: Path, site_signal_out) -> Iterator[Callable[[str, Callable[[Any], Any] | None], Path]]:
    """A writable copy of the fixtures as MONITORING_OUT. `edit(name, fn)` rewrites one file through `fn`
    (fn returns the new document, or a str written as is); `edit(name, None)` deletes it."""
    out = tmp_path / "out"
    shutil.copytree(SITE_SIGNAL_FIXTURES, out)
    site_signal_out(out)

    def edit(name: str, fn: Callable[[Any], Any] | None) -> Path:
        path = out / name
        if fn is None:
            path.unlink()
            return path
        new = fn(json.loads(path.read_text(encoding="utf-8")))
        path.write_text(new if isinstance(new, str) else json.dumps(new), encoding="utf-8")
        st = path.stat()  # a new mtime even on a coarse clock, so the cache sees a new file version
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        return path

    yield edit


# ---- REQ-021: no LLM on the statistics path -------------------------------------------------------------------

FORBIDDEN_PREFIXES = ("anthropic", "openai", "google.genai", "google.generativeai", "app.services.llm",
                      "app.services.postcall")
FORBIDDEN_COMPONENTS = ("anthropic", "claude", "gemini", "elevenlabs", "openai")
PATH_SERVICES = [SERVICES / f"{name}.py" for name in ("site_signal", "episodes", "site_queries")]


def is_llm(module: str) -> bool:
    if any(module == p or module.startswith(p + ".") for p in FORBIDDEN_PREFIXES):
        return True
    return any(part.lower().startswith(c) for part in module.split(".") for c in FORBIDDEN_COMPONENTS)


def imported_modules(path: Path) -> set[str]:
    """Dotted names of every import in a backend module: `import x`, `from x import y` (as x and x.y), relative
    imports resolved against the module's package, and importlib.import_module / __import__ with a literal."""
    package = ".".join(path.relative_to(BACKEND_DIR).with_suffix("").parts[:-1])
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                base = ".".join([*parts, *([base] if base else [])])
            out.add(base)
            out |= {f"{base}.{a.name}" for a in node.names if a.name != "*"}
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            if name in ("import_module", "__import__") and node.args and isinstance(node.args[0], ast.Constant):
                out.add(str(node.args[0].value))
    return out


def module_file(module: str) -> Path | None:
    base = BACKEND_DIR.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def import_closure(files: list[Path]) -> set[str]:
    """Every module imported by `files`, following imports of the backend's own `app` package transitively."""
    seen: set[str] = set()
    todo = list(files)
    done: set[Path] = set()
    while todo:
        path = todo.pop()
        if path in done:
            continue
        done.add(path)
        for module in imported_modules(path):
            seen.add(module)
            if module.split(".")[0] == "app" and (target := module_file(module)) is not None:
                todo.append(target)
    return seen


@pytest.mark.req("REQ-021")
def test_no_llm_import_on_the_statistics_path() -> None:
    """site_signal.py, episodes.py (and site_queries.py once it exists) import no LLM client, directly or through
    any module of the app package they import; no numpy or scipy either (they live only in monitoring/)."""
    files = [p for p in PATH_SERVICES if p.exists()]
    assert SIGNAL_SERVICE in files and SERVICES / "episodes.py" in files
    modules = import_closure(files)
    assert "app.services.episodes" in modules and "app.services.rules" in modules  # the scan follows app imports
    assert sorted(m for m in modules if is_llm(m)) == []
    assert sorted(m for m in modules if m.split(".")[0] in ("numpy", "scipy")) == []


@pytest.mark.req("REQ-021")
def test_statistics_path_loads_no_llm_module_at_runtime() -> None:
    code = "import sys, app.services.site_signal, app.services.episodes; print(' '.join(sorted(sys.modules)))"
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, capture_output=True, text=True, check=True)
    loaded = done.stdout.split()
    assert "app.services.site_signal" in loaded
    assert [m for m in loaded if is_llm(m)] == []


# ---- REQ-023: thresholds are read, never computed --------------------------------------------------------------


@pytest.mark.req("REQ-023")
@pytest.mark.parametrize("path", [SIGNAL_SERVICE, SIGNAL_ROUTER], ids=["service", "router"])
def test_no_threshold_literals(path: Path) -> None:
    """No numeric literal other than 0, 1 and -1 (-1 is unary minus on 1): no threshold, limit or cut-off can be
    written into the Site Signal read path."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    literals = [(n.lineno, n.value) for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, int | float | complex)
                and not isinstance(n.value, bool)]
    if path == SIGNAL_SERVICE:
        assert literals, "the scan sees the service's numeric literals"
    assert [(line, v) for line, v in literals if v not in (0, 1)] == []


@pytest.mark.req("REQ-023")
def test_thresholds_come_from_thresholds_json(client, site_signal_fixtures) -> None:
    file = fixture_doc("thresholds.json")
    run = client.get("/api/sites", headers=CRA).json()["run"]
    assert run["thresholds"] == {k: {"look": file[k]["look"], "watch": file[k]["watch"]} for k in INDICATORS}
    assert run["expected_false_look_flags_per_study"] == file["expected_false_look_flags_per_study"]


@pytest.mark.req("REQ-023")
@pytest.mark.parametrize(
    ("name", "fn"),
    [
        ("thresholds.json", None),
        ("thresholds.json", lambda d: {**d, "discordance": {**d["discordance"], "look": -9.0}}),
        ("thresholds.json", lambda d: {**d, "expected_false_look_flags_per_study": 7.0}),
        ("thresholds.json", lambda d: {**d, "eval_seed": 12345}),
    ],
    ids=["missing", "other-look-threshold", "other-expected-false-look", "other-run"],
)
def test_thresholds_disagreeing_with_the_run_are_unavailable(client, out_copy, name, fn) -> None:
    out_copy(name, fn)
    r = client.get("/api/sites", headers=CRA)
    assert r.status_code == 503 and error_code(r) == "site_signal_unavailable"


# ---- REQ-025: never green ------------------------------------------------------------------------------------


@pytest.mark.req("REQ-025")
@pytest.mark.parametrize("path", ["/api/sites", "/api/sites/112", "/api/sites/101", "/api/site-signal/answer-key"])
def test_missing_outputs_are_unavailable(client, site_signal_out, tmp_path: Path, path: str) -> None:
    site_signal_out(tmp_path / "missing")
    r = client.get(path, headers=CRA)
    assert r.status_code == 503, r.text
    assert error_code(r) == "site_signal_unavailable" and "not computed" in r.json()["error"]["message"]
    assert client.get(path, headers=COORD).status_code == 403  # the role check still comes first


def _row(site_id: str, **change: Any) -> Callable[[Any], Any]:
    def fn(doc: Any) -> Any:
        doc["rows"] = [{**r, **change} if r["site_id"] == site_id else r for r in doc["rows"]]
        return doc
    return fn


def _evidence_of(episode_id: str) -> dict[str, Any]:
    return next(e["evidence"] for e in fixture_doc("episodes.json") if e["episode_id"] == episode_id)


def _episode(episode_id: str, **change: Any) -> Callable[[Any], Any]:
    def fn(doc: Any) -> Any:
        return [{**e, **change} if e["episode_id"] == episode_id else e for e in doc]
    return fn


@pytest.mark.req("REQ-025")
@pytest.mark.parametrize(
    ("name", "fn"),
    [
        ("signal_run.json", None),
        ("signal_run.json", lambda d: "{truncated"),
        ("signal_run.json", lambda d: ""),
        ("signal_run.json", lambda d: d["rows"]),
        ("signal_run.json", _row("112", tier="green")),
        ("signal_run.json", _row("112", tier="clean")),
        ("signal_run.json", _row("117", not_computed_reason=None)),
        ("signal_run.json", _row("112", not_computed_reason="low_coverage")),
        ("signal_run.json", _row("117", not_computed_reason="too_small")),
        ("signal_run.json", _row("112", data_origin="MEASURED")),
        ("signal_run.json", lambda d: {**d, "rows": d["rows"][1:]}),
        ("signal_run.json", lambda d: {**d, "sites": [*d["sites"], d["sites"][0]]}),
        ("signal_run.json", lambda d: {**d, "run": {k: v for k, v in d["run"].items() if k != "sap_tag_commit"}}),
        ("signal_run.json", lambda d: {**d, "run": {**d["run"], "study_not_computed_reason": "study_below_min_sites"}}),
        ("episodes.json", None),
        ("episodes.json", _episode("ep_112_17", matched_site_ae_id="ae_112_4")),
        ("episodes.json", _episode("ep_112_05", matched_site_ae_id="ae_does_not_exist")),
        ("episodes.json", _episode("ep_112_05", matched_site_ae_id="ae_101_2")),
        ("episodes.json", _episode("ep_112_17", site_id="199")),
        ("episodes.json", _episode("ep_112_17", data_origin="MEASURED")),
        ("episodes.json", _episode("ep_112_17", evidence={**_evidence_of("ep_112_17"),
                                                        "source": "live_call"})),
        ("episodes.json", _episode("ep_112_17", evidence={**_evidence_of("ep_112_17"),
                                                        "translation_is_ai": False})),
        ("episodes.json", _episode("ep_112_18", paged_level=None)),
        ("episodes.json", lambda d: [*d, d[0]]),
        ("site_ae.json", None),
        ("site_ae.json", lambda d: [r for r in d if r["site_ae_id"] != "ae_112_4"]),
    ],
    ids=["run-missing", "run-truncated", "run-empty", "run-list", "tier-green", "tier-clean",
         "not-computed-without-reason", "computed-with-reason", "unknown-reason", "row-not-simulated",
         "site-without-row", "duplicate-site", "no-provenance", "study-reason-not-on-rows", "episodes-missing",
         "unmatched-with-match", "dangling-match", "match-at-other-site", "episode-at-unknown-site",
         "simulated-episode-measured", "simulated-quote-not-synthetic", "translation-not-labeled",
         "paged-without-level", "duplicate-episode", "site-ae-missing", "matched-row-removed"],
)
def test_invalid_outputs_are_unavailable(client, out_copy, name, fn) -> None:
    assert client.get("/api/sites", headers=CRA).status_code == 200
    out_copy(name, fn)
    for path in ("/api/sites", "/api/sites/112"):
        r = client.get(path, headers=SPONSOR)
        assert r.status_code == 503, r.text
        assert error_code(r) == "site_signal_unavailable"


@pytest.mark.req("REQ-025")
def test_rewritten_outputs_are_picked_up(client, out_copy) -> None:
    """The mtime cache serves a new file version on the next request, in both directions."""
    original = (SITE_SIGNAL_FIXTURES / "signal_run.json").read_text(encoding="utf-8")
    assert client.get("/api/sites", headers=CRA).status_code == 200
    out_copy("signal_run.json", _row("112", tier="green"))
    assert client.get("/api/sites", headers=CRA).status_code == 503
    out_copy("signal_run.json", lambda d: original)
    assert client.get("/api/sites", headers=CRA).status_code == 200


@pytest.mark.req("REQ-025")
def test_tiers_and_not_computed_sites(client, site_signal_fixtures) -> None:
    r = client.get("/api/sites", headers=CRA)
    assert r.status_code == 200
    body = r.json()
    rows = {s["site_id"]: s for s in body["sites"]}
    assert len(body["sites"]) == len(rows) == 20 and body["run"]["data_origin"] == "SIMULATED"
    # the small site and the low-coverage site are grey, with a reason and no statistic
    for site_id, reason in (("117", "insufficient_patients"), ("103", "low_coverage")):
        row = rows[site_id]
        assert (row["tier"], row["not_computed_reason"], row["rank"]) == ("not_computed", reason, None)
        assert row["O"] is row["E"] is row["z_adj"] is row["oe_ratio"] is None
    for row in body["sites"]:
        assert row["tier"] in TIERS
        if row["tier"] == "not_computed":
            assert row["not_computed_reason"] in REASONS and row["not_computed_reason"] in body["labels"]["reasons"]
        else:
            assert row["not_computed_reason"] is None and isinstance(row["rank"], int)
        assert row["comparators"]["rate_kri"]["tier"] in TIERS
        assert row["comparators"]["simaerep_classic"]["tier"] in TIERS
    # computed sites first by rank, then not-computed sites by site_id
    computed = [s for s in body["sites"] if s["tier"] != "not_computed"]
    grey = [s for s in body["sites"] if s["tier"] == "not_computed"]
    assert body["sites"] == computed + grey
    assert [s["rank"] for s in computed] == sorted(s["rank"] for s in computed)
    assert [s["site_id"] for s in grey] == sorted(s["site_id"] for s in grey) == ["103", "117"]
    text = r.text.lower()
    assert "green" not in text and "clean" not in text


def test_labels_pass_through_flattened(client, site_signal_fixtures) -> None:
    labels = client.get("/api/sites", headers=CRA).json()["labels"]
    source = content.signal_rules()["labels"]
    assert labels["none"] == source["none"]["en"] == "No signal at this sample size"
    assert labels["footer"] == source["footer"]["en"]
    assert "{expected_false_look}" in labels["footer_expected_false_look"]
    assert labels["reasons"] == {k: v["en"] for k, v in source["reasons"].items()}
    assert labels["answer_key"] == {k: v["en"] for k, v in source["answer_key"].items()}
    assert set(labels["reasons"]) == REASONS


def test_site_row_merges_site_and_signal(client, site_signal_fixtures) -> None:
    doc = fixture_doc("signal_run.json")
    site = next(s for s in doc["sites"] if s["site_id"] == "112")
    row = next(r for r in doc["rows"] if r["site_id"] == "112")
    got = next(s for s in client.get("/api/sites", headers=CRA).json()["sites"] if s["site_id"] == "112")
    expected = {**{k: v for k, v in site.items() if k != "_about"}, **row, "open_queries": 0}
    assert got == expected
    assert client.get("/api/sites", headers=CRA).json()["funnel"] == {
        "points": doc["funnel"]["points"], "limits": doc["funnel"]["limits"]}


def test_low_coverage_site_keeps_matched_and_unmatched(client, site_signal_fixtures) -> None:
    """docs/11 §6.4: episodes at a site not computed for low coverage stay matched or unmatched (citable)."""
    detail = client.get("/api/sites/103", headers=CRA).json()
    assert detail["signal"]["tier"] == "not_computed"
    assert {e["status"] for e in detail["episodes"]} == {"unmatched", "pending"}


def test_drill_down_strata_and_paged_stratum(client, site_signal_fixtures) -> None:
    detail = client.get("/api/sites/112", headers=CRA).json()
    assert detail["signal"] == next(r for r in fixture_doc("signal_run.json")["rows"] if r["site_id"] == "112")
    assert [e["episode_id"] for e in detail["episodes"]] == ["ep_112_05", "ep_112_17", "ep_112_18", "ep_112_23",
                                                             "ep_112_30"]
    # O/E set = matched or unmatched (pending and paged excluded): 112-003 en/standard matched,
    # 112-014 es/extra_time unmatched, 112-020 en/standard unmatched
    assert detail["strata"] == {
        "language": {"en": {"evaluable": 2, "matched": 1}, "es": {"evaluable": 1, "matched": 0}},
        "pace": {"standard": {"evaluable": 2, "matched": 1}, "extra_time": {"evaluable": 1, "matched": 0}},
    }
    assert detail["paged_stratum"] == {"n": 1, "matched": 1}
    assert detail["queries"] == []


def test_status_filter_and_errors(client, site_signal_fixtures) -> None:
    eps = client.get("/api/sites/112", params={"status": "unmatched,pending"}, headers=CRA).json()["episodes"]
    assert [e["episode_id"] for e in eps] == ["ep_112_17", "ep_112_23", "ep_112_30"]
    assert client.get("/api/sites/112", params={"status": " paged "}, headers=CRA).json()["episodes"][0][
        "episode_id"] == "ep_112_18"
    r = client.get("/api/sites/112", params={"status": "unmatched,missed"}, headers=CRA)
    assert r.status_code == 422 and error_code(r) == "validation_error"
    r = client.get("/api/sites/199", headers=CRA)
    assert r.status_code == 404 and error_code(r) == "site_not_found"
    r = client.get("/api/sites/112", params={"run_id": "sr_ABCDEFGHJK"}, headers=CRA)
    assert r.status_code == 404 and error_code(r) == "signal_run_not_found"
    assert client.get("/api/sites/112", params={"run_id": "sr_committed"}, headers=CRA).status_code == 200


# ---- answer key, validation summary, equity --------------------------------------------------------------------


def test_answer_key_is_the_file(client, site_signal_fixtures) -> None:
    file = fixture_doc("answer_key.json")
    body = client.get("/api/site-signal/answer-key", headers=SPONSOR).json()
    assert body == {"run_id": "sr_committed", "data_origin": "SIMULATED", "answer_key": file["answer_key"],
                    "confusion": file["confusion"]}
    labels = client.get("/api/sites", headers=CRA).json()["labels"]["answer_key"]
    assert {e["label"] for e in body["answer_key"]} <= set(labels)


@pytest.mark.req("REQ-025")
@pytest.mark.parametrize("fn", [None, lambda d: {**d, "answer_key": [{"site_id": "112", "label": "under_reporter",
                                                                       "f": None}]},
                                lambda d: {**d, "confusion": {"discordance": {"watch": {"tp": 1}}}}],
                         ids=["missing", "unknown-label", "bad-confusion"])
def test_answer_key_unavailable(client, out_copy, fn) -> None:
    out_copy("answer_key.json", fn)
    r = client.get("/api/site-signal/answer-key", headers=CRA)
    assert r.status_code == 503 and error_code(r) == "site_signal_unavailable"


def test_validation_summary_verbatim(client, site_signal_fixtures) -> None:
    file = fixture_doc("summary.json")
    for headers in (COORD, INVESTIGATOR, CRA, SPONSOR, {}):
        r = client.get("/api/site-signal/validation", headers=headers)
        assert r.status_code == 200
        assert r.json() == {**file, "data_origin": "SIMULATED"}


def test_validation_summary_missing_or_invalid(client, out_copy, site_signal_out, tmp_path: Path) -> None:
    out = out_copy("summary.json", lambda d: {**d, "power": {"not": "a list"}}).parent
    r = client.get("/api/site-signal/validation", headers=COORD)
    assert r.status_code == 503 and error_code(r) == "site_signal_unavailable"
    site_signal_out(out, tmp_path / "missing.json")
    r = client.get("/api/site-signal/validation", headers=COORD)
    assert r.status_code == 404 and error_code(r) == "no_validation_run"


def test_equity_is_the_file(client, site_signal_fixtures, out_copy) -> None:
    assert client.get("/api/site-signal/equity", headers=CRA).json() == fixture_doc("equity.json")


def test_equity_missing_or_invalid(client, out_copy) -> None:
    out_copy("equity.json", lambda d: {**d, "language": ["not", "an", "object"]})
    r = client.get("/api/site-signal/equity", headers=CRA)
    assert r.status_code == 503 and error_code(r) == "site_signal_unavailable"
    out_copy("equity.json", None)
    r = client.get("/api/site-signal/equity", headers=CRA)
    assert r.status_code == 404 and error_code(r) == "no_equity_run"


# ---- REQ-026: evidence on every flag -------------------------------------------------------------------------


@pytest.mark.req("REQ-026")
def test_every_flag_drills_down_to_evidence(client, site_signal_fixtures) -> None:
    sites = client.get("/api/sites", headers=CRA).json()["sites"]
    flagged = [s["site_id"] for s in sites if s["tier"] in ("look", "watch")]
    assert flagged == ["112", "107", "109", "108", "111"]
    translated = 0
    for site_id in flagged:
        detail = client.get(f"/api/sites/{site_id}", headers=CRA).json()
        cited = [e for e in detail["episodes"] if e["status"] == "unmatched"]
        assert cited, f"site {site_id} is flagged without an unmatched evaluable episode"
        for e in cited:
            ev = e["evidence"]
            assert ev["quote"].strip() and ev["quote_lang"] in ("en", "es")
            assert date.fromisoformat(e["episode_date"]) and ev["source"] in SOURCES
            assert e["data_origin"] in ("SIMULATED", "MEASURED")
        for e in detail["episodes"]:
            ev = e["evidence"]
            if ev["translation_en"] is not None:
                assert ev["translation_is_ai"] is True
                translated += 1
            if ev["quote_lang"] != "en":
                assert ev["translation_en"] and ev["translation_is_ai"] is True
    assert translated, "the flagged sites include a Spanish quote with its AI translation"


# ---- REQ-030: SIMULATED / MEASURED labels and the live site 101 bridge -----------------------------------------

RECORD_KEYS = ("run", "site", "signal")
RECORD_LISTS = ("sites", "episodes")


def labeled_records(body: Any) -> list[dict]:
    """Every run, site row, site card, signal row and episode in a payload, wherever it sits."""
    found: list[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "episode_id" in node:
                found.append(node)
            for key, value in node.items():
                if key in RECORD_KEYS and isinstance(value, dict):
                    found.append(value)
                if key in RECORD_LISTS and isinstance(value, list):
                    found.extend(v for v in value if isinstance(v, dict) and "episode_id" not in v)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(body)
    return found


def rosa_replay(session: Session) -> str:
    return replay.start(session, "rosa_es_urgent", speed=10_000, run_async=False)


@pytest.mark.req("REQ-030")
def test_every_payload_is_labeled(client, session, site_signal_fixtures) -> None:
    rosa_replay(session)
    for path in READ_ROUTES + ["/api/sites/101", "/api/sites/103"]:
        body = client.get(path, headers=CRA).json()
        assert body.get("data_origin", "SIMULATED") in ORIGINS
        if not path.startswith("/api/sites"):
            assert body["data_origin"] == "SIMULATED"
        for record in labeled_records(body):
            assert record.get("data_origin") in ORIGINS, (path, record)
        for e in (r for r in labeled_records(body) if "episode_id" in r):
            if e["data_origin"] == "SIMULATED":
                assert e["evidence"]["source"] == "synthetic" and e["episode_id"].startswith("ep_1")
            else:
                assert e["data_origin"] == "MEASURED" and e["evidence"]["source"] in ("live_call", "replay")
    assert len(labeled_records(client.get("/api/sites", headers=CRA).json())) == 21  # run + 20 site rows


@pytest.mark.req("REQ-030")
def test_rosa_replay_lists_a_measured_paged_episode_first(client, session, site_signal_fixtures) -> None:
    before = client.get("/api/sites/101", headers=CRA).json()
    assert before["site"]["data_origin"] == "SIMULATED"
    assert all(e["data_origin"] == "SIMULATED" for e in before["episodes"])
    sites_before = client.get("/api/sites", headers=CRA).json()

    cid = rosa_replay(session)
    after = client.get("/api/sites/101", headers=CRA).json()
    live = [e for e in after["episodes"] if e["data_origin"] == "MEASURED"]
    assert after["episodes"][: len(live)] == live and len(live) == 1  # placed first; Fever and Dyspnea not asked
    ep = live[0]
    assert ep["episode_id"] == f"ep_live_{cid}_Diarrhea" and ep["checkin_ids"] == [cid]
    assert (ep["site_id"], ep["subject_id"], ep["language"], ep["pace"]) == ("101", "101-007", "es", "extra_time")
    assert (ep["term"], ep["grade"], ep["kind"]) == ("Diarrhea", 3, "new")
    assert (ep["status"], ep["paged_level"], ep["matched_site_ae_id"]) == ("paged", "urgent", None)
    assert ep["episode_date"] == local_date(utcnow()).isoformat()
    ev = ep["evidence"]
    assert ev["source"] == "replay" and ev["checkin_id"] == cid and ev["quote_lang"] == "es"
    assert ev["quote"].strip() and ev["translation_is_ai"] is (ev["translation_en"] is not None)
    assert after["site"]["data_origin"] == "MIXED"

    # never pooled: the signal row, strata, paged stratum and simulated episodes are unchanged
    for key in ("signal", "strata", "paged_stratum"):
        assert after[key] == before[key]
    assert after["episodes"][len(live):] == before["episodes"]
    assert client.get("/api/sites", headers=CRA).json() == sites_before
    # other sites never get live episodes; the status filter applies to live episodes too
    assert all(e["data_origin"] == "SIMULATED" for e in client.get("/api/sites/112", headers=CRA).json()["episodes"])
    paged = client.get("/api/sites/101", params={"status": "paged"}, headers=CRA).json()["episodes"]
    assert paged[0]["episode_id"] == ep["episode_id"]
    pending = client.get("/api/sites/101", params={"status": "pending"}, headers=CRA).json()["episodes"]
    assert all(e["data_origin"] == "SIMULATED" for e in pending)


def _completed_call(session: Session, patient_id: str, answers: list[tuple[str, str | None, float | None, str]],
                    channel: str = "web") -> CheckIn:
    study, plan = active_plan(session)
    patient = session.get(Patient, patient_id)
    assert patient is not None
    now = utcnow()
    c = CheckIn(id=new_id("ci"), patient_id=patient_id, study_id=study.id, plan_id=plan.id, channel=channel,
                language=patient.language, pace=patient.pace, status="completed", started_at=now, ended_at=now)
    session.add(c)
    for code, option, value, quote in answers:
        session.add(Answer(id=new_id("ans"), checkin_id=c.id, item_code=code, term=content.term_of(code),
                           attribute=content.attribute_of(code), option_code=option, numeric_value=value,
                           verbatim_quote=quote, quote_lang=patient.language))
    session.commit()
    return c


@pytest.mark.req("REQ-030")
def test_live_call_episode_is_pending_then_not_evaluated(client, session, site_signal_fixtures, monkeypatch) -> None:
    """A rule-graded Dyspnea grade 2 call without a page is pending at today's cut; once its entry window has
    passed it is not evaluated (the live bridge is integrated by construction, docs/11 §2.4), never unmatched."""
    c = _completed_call(session, "pat_james", [
        ("SOB_SEV", "moderate", None, "It's moderate, I'd say."),
        ("SOB_EXERTION", "light_activity", None, "Walking to the kitchen leaves me short of breath."),
        ("DIARRHEA_FREQ", "never", None, "No, none of that."),
    ])
    eps = client.get("/api/sites/101", headers=SPONSOR).json()["episodes"]
    live = [e for e in eps if e["data_origin"] == "MEASURED"]
    assert [(e["episode_id"], e["term"], e["grade"], e["status"]) for e in live] == [
        (f"ep_live_{c.id}_Dyspnea", "Dyspnea", 2, "pending")]
    ev = live[0]["evidence"]
    assert ev == {"quote": "Walking to the kitchen leaves me short of breath.", "quote_lang": "en",
                  "translation_en": None, "translation_is_ai": False, "t_s": None, "source": "live_call",
                  "checkin_id": c.id}

    today = local_date(utcnow())
    patient = session.get(Patient, "pat_james")
    patient.dose_dates = [(today - timedelta(days=1)).isoformat(), (today + timedelta(days=20)).isoformat()]
    session.add(patient)
    session.commit()
    monkeypatch.setattr(site_signal, "data_cut_today", lambda: today + timedelta(days=60))
    live = [e for e in client.get("/api/sites/101", headers=SPONSOR).json()["episodes"] if e["data_origin"] == "MEASURED"]
    assert [(e["status"], e["matched_site_ae_id"]) for e in live] == [("not_evaluated", None)]


def test_incomplete_calls_and_other_sites_give_no_live_episodes(client, session, site_signal_fixtures) -> None:
    c = _completed_call(session, "pat_james", [("SOB_SEV", "moderate", None, "Moderate."),
                                               ("SOB_EXERTION", "light_activity", None, "Walking.")])
    c.status = "no_answer"
    session.add(c)
    session.commit()
    assert site_signal.live_episodes(session, "101") == []
    assert site_signal.live_episodes(session, "112") == []


def _answers(**values: Any) -> rules.Answers:
    out: rules.Answers = {}
    for code, value in values.items():
        if isinstance(value, tuple):
            out[code] = rules.AnswerInput(numeric_value=value[0], unit=value[1])
        else:
            out[code] = rules.AnswerInput(option_code=value)
    return out


@pytest.mark.parametrize(
    ("term", "answers", "expected"),
    [
        ("Diarrhea", {}, None),  # not asked
        ("Diarrhea", _answers(DIARRHEA_FREQ="unknown"), None),  # unknown counts as not answered
        ("Fever", _answers(TEMP_HIGHEST="not_measured"), None),
        ("Diarrhea", _answers(DIARRHEA_FREQ="never"), 0),  # reported absent
        ("Dyspnea", _answers(SOB_SEV="none"), 0),
        ("Fever", _answers(FEVER_CHILLS="no"), 0),
        ("Diarrhea", _answers(DIARRHEA_FREQ="often"), None),  # present, no rule matched: needs_clinician
        ("Fever", _answers(FEVER_CHILLS="yes"), None),
        ("Diarrhea", _answers(DIARRHEA_FREQ="almost_always", DIARRHEA_STOOLS_PER_DAY=(8, "per_day")), 3),
        ("Diarrhea", _answers(DIARRHEA_FREQ="often", DIARRHEA_STOOLS_PER_DAY=(6, "per_day")), 2),
        ("Dyspnea", _answers(SOB_SEV="moderate", SOB_EXERTION="light_activity"), 2),
        ("Fever", _answers(FEVER_CHILLS="yes", TEMP_HIGHEST=(39.5, "celsius")), 2),
        ("Fever", _answers(TEMP_HIGHEST=(38.5, "celsius")), 1),  # a numeric value is an answer
        ("Dyspnea", _answers(DIARRHEA_FREQ="often"), None),  # another term's items say nothing about this one
    ],
)
def test_term_grade_mapping(term: str, answers: rules.Answers, expected: int | None) -> None:
    """docs/11 §4.2: g_k = 0 when asked and reported absent; rules.grade's provisional grade otherwise (None when
    needs_clinician); None when not asked."""
    assert site_signal.term_grade(term, answers, {"stools_per_day": 1}) == expected


def test_signal_row_model_rejects_untiered_rows() -> None:
    row = next(r for r in fixture_doc("signal_run.json")["rows"] if r["site_id"] == "117")
    assert SiteSignalRow.model_validate(row).tier == "not_computed"
    with pytest.raises(ValueError):
        SiteSignalRow.model_validate({**row, "tier": "none"})
