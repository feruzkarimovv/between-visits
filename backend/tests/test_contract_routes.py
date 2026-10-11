"""B20: every built route in docs/03 §5.2 and §6 exists in /openapi.json with the documented method.

The routes are read from the contract itself, so a route added to docs/03 without code (or renamed in code without
the doc) fails here. Rows of the §5.2 table marked "not built" (cut for time, NOT_BUILT.md) are not checked; the
blind-run routes among them must not exist either, so nothing describes them as built.
"""

import re

import pytest

from app.config import ROOT

CONTRACT = ROOT / "docs" / "03-api-contracts.md"
METHODS = ("GET", "POST", "PATCH", "PUT", "DELETE")
# `| GET | `/api/sites` | cra, sponsor | ...` (docs/03 §5.2 endpoint summary)
TABLE_ROW = re.compile(r"^\|\s*(" + "|".join(METHODS) + r")\s*\|\s*`(/[^`]+)`([^\n]*)$", re.MULTILINE)
# `GET /api/audit/verify`, `POST /api/demo/replay/{scenario_id}?speed=1|2|4` (docs/03 §6 prose and role table)
INLINE_ROUTE = re.compile(r"`(" + "|".join(METHODS) + r") (/[^`\s?]+)")
PARAM = re.compile(r"\{[^}]*\}")


def _section(text: str, start: str, end: str | None) -> str:
    """From `start` up to `end` (exclusive), or to the end of the document when `end` is None."""
    i = text.index(start)
    return text[i:] if end is None else text[i : text.index(end, i + len(start))]


def _norm(path: str) -> str:
    """Path parameters compare by position, not name (`{id}` in the prose is `{sae_id}` in the code)."""
    return PARAM.sub("{}", path.strip())


def _contract() -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """(built routes, not-built routes) as (METHOD, normalized path) pairs."""
    text = CONTRACT.read_text(encoding="utf-8")
    built: set[tuple[str, str]] = set()
    not_built: set[tuple[str, str]] = set()
    for method, path, rest in TABLE_ROW.findall(_section(text, "### 5.2 Endpoint summary", "### 5.3 ")):
        (not_built if "not built" in rest else built).add((method, _norm(path)))
    for method, path in INLINE_ROUTE.findall(_section(text, "## 6. Readiness contract changes", None)):
        built.add((method, _norm(path)))
    return built, not_built


def _openapi_routes(client) -> set[tuple[str, str]]:  # noqa: ANN001
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    return {
        (method.upper(), _norm(path))
        for path, ops in resp.json()["paths"].items()
        for method in ops
        if method.upper() in METHODS
    }


def test_contract_parsed_enough_routes():
    """Guards against a doc reformat that would make the conformance test pass vacuously."""
    built, not_built = _contract()
    section_52 = {r for r in built if r[1].startswith(("/api/sites", "/api/site-signal", "/api/site-queries"))}
    assert len(section_52) >= 12, sorted(section_52)
    assert {("GET", "/api/audit/verify"), ("GET", "/api/eval/voice-checks"),
            ("GET", "/api/demo/scenarios/{}/audio"), ("GET", "/api/eval/latest")} <= built
    assert len(not_built) == 5, sorted(not_built)


def test_every_built_route_exists_with_documented_method(client):
    built, _ = _contract()
    missing = sorted(built - _openapi_routes(client))
    assert not missing, f"routes in docs/03 §5.2/§6 missing from /openapi.json: {missing}"


def test_cut_blind_run_routes_absent(client):
    """The blind run is cut for time (NOT_BUILT.md): its routes must not exist under any method."""
    _, not_built = _contract()
    blind = {path for _, path in not_built if path.startswith("/api/site-signal/blind-run")}
    assert len(blind) == 4, sorted(blind)
    paths = {path for _, path in _openapi_routes(client)}
    assert not blind & paths, sorted(blind & paths)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/sites"),
        ("GET", "/api/sites/{}"),
        ("POST", "/api/site-queries"),
        ("PATCH", "/api/site-queries/{}"),
        ("POST", "/api/site-queries/{}/respond"),
        ("GET", "/api/audit/verify"),
        ("POST", "/api/demo/replay/{}"),
        ("GET", "/api/export/ae.csv"),
    ],
)
def test_parser_finds_known_rows(method, path):
    """Spot checks that the parser reads both the §5.2 table and the §6 prose."""
    built, _ = _contract()
    assert (method, path) in built
