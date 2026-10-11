"""params.yaml agrees with the SAP tables (docs/11 §11.3, §11.4, §11.5 values filled at tag time)."""

from __future__ import annotations

import importlib.util
import sys

from bvsignal import MONITORING_DIR, REPO_ROOT

_spec = importlib.util.spec_from_file_location("check_params_sap", MONITORING_DIR / "planning" / "check_params_sap.py")
assert _spec and _spec.loader
chk = importlib.util.module_from_spec(_spec)
sys.modules["check_params_sap"] = chk
_spec.loader.exec_module(chk)


def test_number_extraction_ignores_references_and_code() -> None:
    assert chk.numbers("Diarrhea G2 0.56, G3 0.70 (§11.5) `visit_med75` true `r_null` 2000") == [0.56, 0.70, 2000.0]
    assert chk.numbers("*u_s* := −1.5 × 0.35 (the 7th percentile)") == [-1.5, 0.35]
    assert chk.numbers("20 (`site_ids` `101`–`120`)") == [20.0, 101.0, 120.0]


def test_params_yaml_agrees_with_the_sap_tables() -> None:
    rows = chk.compare(REPO_ROOT)
    bad = [f"§{r.section} {r.key}: SAP {r.sap} | params {r.params}" for r in rows if not r.ok]
    assert not bad, "\n".join(bad)
    sections = {r.section for r in rows}
    assert sections == {"11.3", "11.4", "11.5"}
    assert sum(r.section == "11.4" for r in rows) == 10
