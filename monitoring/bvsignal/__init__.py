"""Site Signal statistics (docs/10-site-signal.md, docs/11-site-signal-sap.md).

Pre-registered under the annotated tag `sap-v1`. Every output is SIMULATED and is a reason to look,
not a finding. No LLM anywhere on this path (CLAUDE.md rule 1): grades and red flags come only from
backend/app/services/rules.py through `bvsignal._backend`.
"""

from pathlib import Path

MONITORING_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = MONITORING_DIR.parent
PARAMS_FILE = MONITORING_DIR / "params.yaml"
DATA_ORIGIN = "SIMULATED"

__all__ = ["DATA_ORIGIN", "MONITORING_DIR", "PARAMS_FILE", "REPO_ROOT"]
