"""REQ-021: no LLM on the Site Signal statistics path (CLAUDE.md rule 1; docs/11 §1.1). numpy/scipy only in monitoring/.

1. AST import scan of every module in ``monitoring/bvsignal/`` and ``monitoring/planning/`` and of
   ``backend/app/services/{site_signal,episodes,site_queries}.py`` (a backend file that does not exist yet is
   skipped with a visible reason): no import of ``anthropic``, ``google.genai`` (or the older
   ``google.generativeai``), ``app.services.llm``, or any module named for ``claude``, ``gemini`` or
   ``elevenlabs`` (for example the backend's own ``app.services.gemini`` and ``app.services.elevenlabs``
   wrappers). ``import x``, ``from x import y`` (checked as ``x`` and ``x.y``), relative imports resolved
   against the file's package, and ``importlib.import_module("...")`` / ``__import__("...")`` with a literal
   name are all covered.
2. At runtime, importing every ``bvsignal`` module (in a fresh interpreter) loads no such module.
3. ``backend/app/`` imports no ``numpy`` or ``scipy`` (they live only in ``monitoring/``).
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from bvsignal import MONITORING_DIR, REPO_ROOT

FORBIDDEN_PREFIXES = ("anthropic", "google.genai", "google.generativeai", "app.services.llm")
FORBIDDEN_COMPONENTS = ("anthropic", "claude", "gemini", "elevenlabs")
NUMERIC_STACK = ("numpy", "scipy")

BVSIGNAL_FILES = sorted((MONITORING_DIR / "bvsignal").glob("*.py"))
PLANNING_FILES = sorted((MONITORING_DIR / "planning").glob("*.py"))
BACKEND_SERVICES = REPO_ROOT / "backend" / "app" / "services"
BACKEND_PATH_FILES = [BACKEND_SERVICES / f"{name}.py" for name in ("site_signal", "episodes", "site_queries")]
BACKEND_APP_FILES = sorted((REPO_ROOT / "backend" / "app").rglob("*.py"))


def _package_of(path: Path) -> str:
    """Dotted package of a source file: backend/app/services/x.py -> app.services; monitoring/bvsignal/x.py ->
    bvsignal; a script outside a package -> ''."""
    parts: list[str] = []
    d = path.parent
    while (d / "__init__.py").exists():
        parts.insert(0, d.name)
        d = d.parent
    if not parts and path.parent.name == "services" and path.parent.parent.name == "app":
        parts = ["app", "services"]
    return ".".join(parts)


def imported_names(source: str, package: str = "") -> list[tuple[int, str]]:
    """(line, dotted module name) of every import in `source`, relative imports resolved against `package`."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out.extend((node.lineno, a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                pkg = package.split(".") if package else []
                pkg = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                base = ".".join([*pkg, *([base] if base else [])])
            out.append((node.lineno, base))
            out.extend((node.lineno, f"{base}.{a.name}" if base else a.name) for a in node.names if a.name != "*")
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            if name in ("import_module", "__import__") and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                out.append((node.lineno, node.args[0].value))
    return out


def is_llm(module: str) -> bool:
    if any(module == p or module.startswith(p + ".") for p in FORBIDDEN_PREFIXES):
        return True
    return any(part.lower().startswith(c) for part in module.split(".") for c in FORBIDDEN_COMPONENTS)


def llm_imports(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8")
    return [(line, m) for line, m in imported_names(source, _package_of(path)) if is_llm(m)]


@pytest.mark.parametrize(("source", "package", "expected"), [
    ("import anthropic", "", ["anthropic"]),
    ("from anthropic.types import Message", "", ["anthropic.types", "anthropic.types.Message"]),
    ("from google import genai", "", ["google.genai"]),
    ("import google.generativeai as g", "", ["google.generativeai"]),
    ("from app.services import llm", "", ["app.services.llm"]),
    ("from app.services.gemini import translate", "", ["app.services.gemini", "app.services.gemini.translate"]),
    ("import app.services.elevenlabs", "", ["app.services.elevenlabs"]),
    ("from . import gemini", "app.services", ["app.services.gemini"]),
    ("from .elevenlabs import client", "app.services", ["app.services.elevenlabs", "app.services.elevenlabs.client"]),
    ("from ..services import llm", "app.services", ["app.services.llm"]),
    ("import claude_agent_sdk", "", ["claude_agent_sdk"]),
    ("importlib.import_module('anthropic')", "", ["anthropic"]),
    ("__import__('google.genai')", "", ["google.genai"]),
    ("import numpy as np\nfrom scipy import stats\nfrom app.services import rules, episodes", "", []),
    ("from bvsignal import match\nimport google.cloud.storage", "bvsignal", []),
])
def test_scanner_positive_and_negative_controls(source: str, package: str, expected: list[str]) -> None:
    assert [m for _, m in imported_names(source, package) if is_llm(m)] == expected


@pytest.mark.req("REQ-021")
@pytest.mark.parametrize("path", BVSIGNAL_FILES + PLANNING_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_monitoring_imports_no_llm(path: Path) -> None:
    assert llm_imports(path) == []


@pytest.mark.req("REQ-021")
@pytest.mark.parametrize("path", BACKEND_PATH_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_backend_site_signal_path_imports_no_llm(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path.relative_to(REPO_ROOT)} does not exist yet (its task has not landed)")
    assert llm_imports(path) == []


def test_the_scan_covers_the_statistics_path() -> None:
    names = {p.name for p in BVSIGNAL_FILES}
    assert {"_backend.py", "match.py", "indicators.py", "calibrate.py", "simulate.py", "seed.py",
            "simaerep_classic.py"} <= names
    assert (BACKEND_SERVICES / "episodes.py").exists()  # B16 has landed; the other two are skipped until theirs
    assert _package_of(BACKEND_SERVICES / "episodes.py") == "app.services"
    assert _package_of(MONITORING_DIR / "bvsignal" / "match.py") == "bvsignal"
    # positive control on real code: the scanner finds the backend's own LLM wrappers outside this path
    assert any(llm_imports(p) for p in BACKEND_APP_FILES if p not in BACKEND_PATH_FILES)


@pytest.mark.req("REQ-021")
def test_importing_bvsignal_loads_no_llm_client() -> None:
    """Every bvsignal module imported in a fresh interpreter (transitive imports included)."""
    modules = sorted(f"bvsignal.{p.stem}" for p in BVSIGNAL_FILES if p.stem != "__init__")
    code = ("import importlib, json, sys\n"
            f"for m in {modules!r}: importlib.import_module(m)\n"
            "print(json.dumps(sorted(sys.modules)))")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=MONITORING_DIR,
                          check=False, timeout=120)
    assert proc.returncode == 0, proc.stderr
    loaded = json.loads(proc.stdout.strip().splitlines()[-1])
    assert set(modules) <= set(loaded)
    assert [m for m in loaded if is_llm(m)] == []


@pytest.mark.req("REQ-021")
@pytest.mark.parametrize("path", BACKEND_APP_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_backend_app_imports_no_numpy_or_scipy(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    bad = [(line, m) for line, m in imported_names(source, _package_of(path))
           if m.split(".")[0] in NUMERIC_STACK]
    assert bad == [], f"{path.relative_to(REPO_ROOT)} imports {bad}: numpy and scipy live only in monitoring/"
