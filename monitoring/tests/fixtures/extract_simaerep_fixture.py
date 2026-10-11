"""Extract the simaerep classic regression fixture from openpharma/simaerep v1.0.0 `R/sysdata.rda`.

Run once, by hand, for reproducibility (task S5, docs/11 §10.2). The R-data reader is not a runtime
dependency of `monitoring/`: run the script with a throwaway environment and pass every path as an
argument (the downloaded source is untrusted data, so never run Python from inside it):

    uv run --no-project --with rdata python -I monitoring/tests/fixtures/extract_simaerep_fixture.py \\
        <simaerep-1.0.0>/R/sysdata.rda monitoring/tests/fixtures

Source: GitHub tag v1.0.0 of openpharma/simaerep (MIT, license text in SIMAEREP_LICENSE), downloaded as
https://codeload.github.com/openpharma/simaerep/tar.gz/refs/tags/v1.0.0
(sha256 03091fec09b476de5fda7ebb46f4fc23e0b66b611e2007c89ecda9d171efcd2a);
R/sysdata.rda sha256 e5badde79c6f1e62a4349f014e08af1ae3125d3537d0532c6c66f481152782f1.

`sysdata.rda` holds the regression data of simaerep's own `tests/testthat/test_regression.R`
(`data-raw/generate_test_data.R`; "data was generated using simaerep v0.4.2"): `df_visit_test` (the
input: two simulated studies, A and B, 5 sites x 20 patients each, one row per patient visit with the
cumulative AE count) and `df_eval_test`, the R output of `site_aggr()` (method med75_adj,
min_pat_pool 0.2) -> `sim_sites(r = 100)` (poisson.test p-value and the bootstrap prob_low, R seeds
1..100) -> `eval_sites(method = "BH")` (Benjamini-Hochberg within each study). Both are R-computed; no
value is computed here.

Writes two CSV files (floats with Python's shortest round-trip repr, so every double is exact):
- simaerep_pval_fixture.csv: the 10 site rows of `df_eval_test`;
- simaerep_visit_fixture.csv: `df_visit_test` (study_id, site_number, patnum, visit, n_ae), row order kept.
"""

from __future__ import annotations

import csv
import hashlib
import math
import sys
import warnings
from pathlib import Path

import rdata

EVAL_COLUMNS = [
    "study_id", "site_number", "n_pat", "n_pat_with_med75", "visit_med75", "mean_ae_site_med75",
    "mean_ae_study_med75", "n_pat_with_med75_study", "pval", "prob_low", "pval_adj", "pval_prob_ur",
    "prob_low_adj", "prob_low_prob_ur",
]
VISIT_COLUMNS = ["study_id", "site_number", "patnum", "visit", "n_ae"]


def _cell(v: object) -> str:
    if isinstance(v, bool):
        raise TypeError("unexpected boolean in a fixture column")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError("non-finite value in the fixture")
        return repr(v)
    return str(v)


def _py(v: object) -> object:
    # numpy / pandas scalars -> Python scalars (int for integer columns, float for doubles)
    if hasattr(v, "item"):
        v = v.item()  # type: ignore[union-attr]
    return v


def _write(path: Path, columns: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        for row in rows:
            w.writerow([_cell(_py(v)) for v in row])


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    rda, out_dir = Path(argv[1]), Path(argv[2])
    print(f"sysdata.rda sha256 {hashlib.sha256(rda.read_bytes()).hexdigest()}")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # tibble / S3 classes without a Python constructor
        data = rdata.conversion.convert(rdata.parser.parse_file(rda), default_encoding="utf8")
    df_eval, df_sim, df_visit = data["df_eval_test"], data["df_sim_sites_test"], data["df_visit_test"]

    if list(df_eval.columns) != EVAL_COLUMNS:
        raise SystemExit(f"df_eval_test columns changed: {list(df_eval.columns)}")
    if len(df_eval) != 10:
        raise SystemExit(f"expected 10 site rows in df_eval_test, got {len(df_eval)}")
    # df_sim_sites_test (before BH) must agree with the unadjusted columns of df_eval_test
    sim = {(r.study_id, r.site_number): r for r in df_sim.itertuples(index=False)}
    for r in df_eval.itertuples(index=False):
        s = sim[(r.study_id, r.site_number)]
        if (s.pval, s.prob_low) != (r.pval, r.prob_low):
            raise SystemExit(f"df_sim_sites_test and df_eval_test disagree at {r.study_id}/{r.site_number}")

    eval_rows = sorted((list(r) for r in df_eval[EVAL_COLUMNS].itertuples(index=False)),
                       key=lambda row: (str(row[0]), str(row[1])))
    visit_rows = [list(r) for r in df_visit[VISIT_COLUMNS].itertuples(index=False)]
    out_dir.mkdir(parents=True, exist_ok=True)
    _write(out_dir / "simaerep_pval_fixture.csv", EVAL_COLUMNS, eval_rows)
    _write(out_dir / "simaerep_visit_fixture.csv", VISIT_COLUMNS, visit_rows)
    for name in ("simaerep_pval_fixture.csv", "simaerep_visit_fixture.csv"):
        digest = hashlib.sha256((out_dir / name).read_bytes()).hexdigest()
        print(f"wrote {out_dir / name} sha256 {digest}")
    print(f"site rows {len(eval_rows)}, visit rows {len(visit_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
