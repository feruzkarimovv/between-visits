# monitoring/: Site Signal statistics

Pre-registered, deterministic, seed-reproducible statistics behind Site Signal: capture discordance between what a site's own patients told Between Visits and what the site's AE log records. A tier is a reason to look, not a finding. The plan is [`docs/11-site-signal-sap.md`](../docs/11-site-signal-sap.md) (the SAP; on statistics it overrides every other document); the product requirements are [`docs/10-site-signal.md`](../docs/10-site-signal.md); tasks are S1–S10 in [`docs/workstreams/WS5-site-signal.md`](../docs/workstreams/WS5-site-signal.md).

**Every Site Signal study is SIMULATED.** Both streams (patient episodes and site AE logs) of sites 101–120 are generated here from `params.yaml`; only live and replayed calls at site 101 are MEASURED, and they never enter a statistic. No LLM is used anywhere in this folder (CLAUDE.md rule 1): grades and red flags come from the real `backend/app/services/rules.py` through `bvsignal/_backend.py`, and every match, evaluability, minimum-data and tier constant is read from `data/signal_rules.json` or `params.yaml`.

## Setup

A separate uv project (Python 3.12; numpy, scipy, pyyaml, pydantic and pydantic-settings; pytest and ruff for development). numpy and scipy live only here; the backend never imports this project.

```bash
uv sync --project monitoring
uv run --project monitoring pytest -q          # from the repository root (or: cd monitoring && uv run pytest -q)
cd monitoring && uv run ruff check .
```

`monitoring/uv.lock` is committed and frozen by the `sap-v1` tag: numpy does not promise identical random streams across versions.

## Files

| Path | What | Status |
|---|---|---|
| `params.yaml` | Every pre-registered parameter (SAP §11.3, §11.4), each number with a citation or `ASSUMPTION`; `signal_rules_sha256` and `frozen_inputs` | S1 |
| `bvsignal/seed.py` | Evaluation-seed derivation, replicate keys, beacon fetch, run log, frozen-input hashes | S1 |
| `bvsignal/_backend.py` | Puts `backend/` on `sys.path` and re-exports the rules engine (`grade`, `red_flags`, `level_for`); no `.env`, database or LLM | S1 |
| `planning/plan_power.py`, `planning/planning_grid.json` | Pre-tag planning grid (SAP §11.5 rules P1 and P2), dev seed, **planning only, not a result** | S1 |
| `planning/check_params_sap.py` | Checks `params.yaml` against the SAP §11.3 and §11.4 tables and the §11.5 values | S1 |
| `seed_beacon.json` | Beacon round and randomness, fetched once after the tag | after the tag |
| `bvsignal/{roster,simulate,match,indicators,calibrate,simaerep_classic,equity,run,validate,blind,report}.py`, `out/` | Simulation, analysis and committed outputs | after the `sap-v1` tag (S2–S10) |

## Seeds and pre-registration order (SAP §1.2, §1.3)

- **Dev seed** `20261011` (`params.yaml` `seeds.dev`): development, unit tests and the planning grid only. Dev-seed outputs are never committed, except `planning/planning_grid.json`.
- **Evaluation seed**: `int(sha256(("sap-v1:" + S + ":" + B).encode()).hexdigest()[:8], 16)`, where `S` is `git rev-parse sap-v1^{commit}` and `B` is the randomness of the first drand mainnet round at least 10 minutes after the `sap-v1` tagger timestamp (NIST beacon 2.0 fallback; the empty string, with a SAP §17 entry, if neither is reachable).
- Every replicate draws from `numpy.random.SeedSequence(seed, spawn_key=(stream, cell_index, role, i))`; streams are listed in `params.yaml` `streams` and cells in `cell_index`.
- Before the tag only the S1 files (and B16, `backend/app/services/episodes.py`) may exist; nothing under `monitoring/out/` or `validation/site_signal/` is committed before the tag.

```bash
make planning-grid                                                      # pre-tag planning grid (dev seed)
uv run --project monitoring python -m bvsignal.seed --frozen-inputs     # print signal_rules_sha256 and frozen_inputs
uv run --project monitoring python -m bvsignal.seed --write-frozen      # write them into params.yaml (comments kept)
uv run --project monitoring python -m bvsignal.seed --check-frozen      # exit 1 on a mismatch no SAP §17 row cites
uv run --project monitoring python monitoring/planning/check_params_sap.py   # params.yaml vs the SAP tables
# after the sap-v1 tag is pushed:
uv run --project monitoring python -m bvsignal.seed --fetch-beacon [--wait]
uv run --project monitoring python -m bvsignal.seed --show              # sap_tag_commit=<sha> beacon_round=<n> eval_seed=<int>
```

`--show` exits non-zero with a clear message before the tag exists, before the beacon file exists, or outside a git checkout. Every evaluation-seed run of `calibrate`, `run`, `validate` and `blind --precompute` refuses a dirty working tree and appends `{utc_time, code_commit, git_dirty, command, output_sha256}` to `validation/site_signal/run_log.jsonl` (`bvsignal.seed.log_run`).

## Outputs and labels

- Every output object carries `data_origin: "SIMULATED"`, `sap_tag_commit`, `eval_seed` and `code_commit` (SAP §15 rule 7).
- Numbers quoted anywhere come only from `validation/site_signal/summary.json` and `monitoring/out/*.json` (SAP §15 rule 1). `planning_grid.json` is never quoted as a result.
- Wording: "capture discordance", "a reason to look, not a finding", and "No signal at this sample size" for the `none` tier. Tiers are `watch`, `look`, `none` and `not_computed`; there is no green tier.

## Third-party attribution

The simaerep classic (legacy) comparator (task S5, after the tag) is a Python port of the original algorithm of openpharma/simaerep, MIT License; its license text will ship as `tests/fixtures/SIMAEREP_LICENSE` with the fixture test.
