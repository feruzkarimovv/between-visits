"""The one bridge from `monitoring/` to the backend's grading and episode code (docs/11 §1.1, §4-§6, §11.2).

Adds `backend/` to `sys.path` and re-exports:

* the pure rules engine `app.services.rules` (`grade`, `term_present`, `red_flags`, `level_for`), so the
  simulator and the planning grid grade generated answers with the real `backend/app/services/rules.py`
  (driven only by `data/ctcae_rules.json` and `data/red_flags.json`) instead of re-coding any clinical
  threshold;
* `app.services.episodes` (task B16), the one implementation of episode construction, matching,
  evaluability, the paged stratum and status precedence (docs/11 §4-§6), shared with the backend's site 101
  live bridge and never re-implemented in `monitoring/`.

Importing this module needs no `.env` (settings are read lazily by the backend and never here), opens no
database and imports no LLM client: only `app.content` (JSON loader), `app.config` (paths),
`app.services.rules` and `app.services.episodes` (pure functions, standard library only) are loaded.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import content  # noqa: E402
from app.services import episodes  # noqa: E402
from app.services.rules import (  # noqa: E402
    ABSENT_OPTIONS,
    LEVEL_RANK,
    AnswerInput,
    GradeResult,
    RedFlagHit,
    grade,
    level_for,
    red_flags,
    term_present,
)

__all__ = [
    "ABSENT_OPTIONS",
    "BACKEND_DIR",
    "LEVEL_RANK",
    "AnswerInput",
    "GradeResult",
    "RedFlagHit",
    "content",
    "episodes",
    "grade",
    "level_for",
    "red_flags",
    "term_present",
]
