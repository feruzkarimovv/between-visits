"""bvsignal._backend: the real rules engine, importable without a .env, a database or any LLM client."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from bvsignal import MONITORING_DIR

PROBE = """
import sys
import bvsignal._backend as b
from app import config
banned_roots = {"sqlmodel", "sqlalchemy", "fastapi", "starlette", "anthropic", "httpx", "twilio", "google"}
banned = sorted(m for m in sys.modules if m.split(".")[0] in banned_roots
                or m in {"app.db", "app.models", "app.main", "app.services.llm", "app.services.claude",
                         "app.services.gemini", "app.services.elevenlabs", "app.services.pager"})
assert not banned, banned
assert config.get_settings.cache_info().currsize == 0, "settings (.env) were read"
A = b.AnswerInput
g = b.grade("Dyspnea", {"SOB_SEV": A("mild"), "SOB_EXERTION": A("light_activity")}, None)
assert (g.provisional_grade, g.grade_basis) == (2, "rule"), g
assert b.level_for(b.red_flags({"TEMP_HIGHEST": A(numeric_value=39.5, unit="celsius")}, None)) == "urgent"
assert b.level_for(b.red_flags({"FEVER_CHILLS": A("no")}, None)) == "none"
assert not b.term_present("Fever", {"FEVER_CHILLS": A("no")})
assert b.episodes.STATUSES[0] == "paged" and callable(b.episodes.analyze)
print("ok")
"""


def test_backend_bridge_imports_without_env_db_or_llm(tmp_path: Path) -> None:
    secret_prefixes = ("TOOL_", "ANTHROPIC", "GEMINI", "ELEVENLABS", "NTFY", "TWILIO", "DEMO_", "APP_ENV", "LLM_", "CLAUDE_")
    env = {k: v for k, v in os.environ.items() if not k.startswith(secret_prefixes)}
    proc = subprocess.run([sys.executable, "-c", PROBE], cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 0 and proc.stdout.strip() == "ok", proc.stderr


def test_backend_bridge_imports_only_content_rules_and_episodes() -> None:
    tree = ast.parse((MONITORING_DIR / "bvsignal" / "_backend.py").read_text())
    app_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            modules = ("app", "app.services")
            app_imports.add(node.module + ":" + ",".join(sorted(a.name for a in node.names if node.module in modules)))
        elif isinstance(node, ast.Import):
            assert all(not a.name.startswith("app") for a in node.names)
    assert app_imports == {"app:content", "app.services:episodes", "app.services.rules:"}
