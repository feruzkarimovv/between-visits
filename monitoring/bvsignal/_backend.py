"""The one bridge from `monitoring/` to the backend's grading code (docs/11 §1.1, §11.2).

Adds `backend/` to `sys.path` and re-exports the pure rules engine, so the simulator and the planning
grid grade generated answers with the real `backend/app/services/rules.py` (driven only by
`data/ctcae_rules.json` and `data/red_flags.json`) instead of re-coding any clinical threshold.

Importing this module needs no `.env` (settings are read lazily by the backend and never here), opens
no database and imports no LLM client: only `app.content` (JSON loader), `app.config` (paths) and
`app.services.rules` (pure functions) are loaded. The `episodes` re-export (B16) is added in S2.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import content  # noqa: E402
from app.services.rules import (  # noqa: E402
    ABSENT_OPTIONS,
    LEVEL_RANK,
    AnswerInput,
    GradeResult,
    RedFlagHit,
    grade,
    level_for,
    red_flags,
)

__all__ = [
    "ABSENT_OPTIONS",
    "BACKEND_DIR",
    "LEVEL_RANK",
    "AnswerInput",
    "GradeResult",
    "RedFlagHit",
    "content",
    "grade",
    "level_for",
    "red_flags",
]
