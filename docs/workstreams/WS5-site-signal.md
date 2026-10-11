# WS5 · Site Signal statistics (`monitoring/`)

Owner: the statistics lane (one Claude Code agent; the team lead, or a teammate the team lead names, reviews the SAP before the tag). Folders and files: `monitoring/` (new, separate uv project), `validation/site_signal/`, `docs/11-site-signal-sap.md` (only §11.5 values at tag time, the §1.5 change log and §17 Deviations), `Makefile` targets `planning-grid`, `site-signal`, `site-signal-validate`, `blind-run`, `cohort`, `test-monitoring`, and the `monitoring` job in `.github/workflows/ci.yml`.

Read first: `CLAUDE.md`; [`docs/11-site-signal-sap.md`](../11-site-signal-sap.md) (the SAP: on statistics it overrides every other document, including this one); [`docs/10-site-signal.md`](../10-site-signal.md) (product requirements); `docs/03-api-contracts.md` §5 (the payloads the backend serves from your outputs); `docs/02-data-model.md` § Site Signal (Site, Episode, SiteAE, SiteSignalRow); `data/signal_rules.json` and `data/site_queries.json` (WS4, D11); `data/ctcae_rules.json`, `data/red_flags.json` and `backend/app/services/rules.py` (graded input).

Added in the planning round on Sat Oct 10, late. All times are Sun Oct 11, ET. Sources for every method and parameter are in `docs/11` §19; this file adds none.

## What WS5 delivers

A pre-registered, deterministic, seed-reproducible Python package that:

1. simulates a 20-site study (sites 101–120) whose patient stream is graded by the real `rules.py` and whose site AE log follows a stated capture model with planted site behaviors and a hidden answer key;
2. builds episodes, matches them to site-originated AEs, applies evaluability, paged-stratum and minimum-data rules (one implementation shared with the backend: `backend/app/services/episodes.py`, B16);
3. computes the capture-discordance indicator (leave-one-site-out O/E, overdispersion-adjusted z) and two comparators on the identical study, a gsm-style AE-rate KRI and simaerep classic (legacy), with Look and Watch thresholds calibrated once from a pre-registered null;
4. measures its own operating characteristics (null false-flag rates with Monte Carlo SE, power at both tiers, failure case, sensitivity) into `validation/site_signal/summary.json`, the only source of Site Signal numbers anywhere;
5. serves blind runs for the dashboard through a CLI, and an equity analysis by language and pace.

Every output object carries `data_origin: "SIMULATED"`. Output is "a reason to look, not a finding".

## Kickoff prompt for Claude Code

> You are implementing workstream WS5 (Site Signal statistics) of Between Visits. Read CLAUDE.md, docs/11-site-signal-sap.md (the SAP; it overrides every other document on statistics), docs/10-site-signal.md, docs/03-api-contracts.md §5, docs/02-data-model.md § Site Signal and docs/workstreams/WS5-site-signal.md. Start with S1 and nothing else. Until the annotated tag sap-v1 is pushed: use only the dev seed 20261011; do not create monitoring/out/ or validation/site_signal/ in any commit; write only the S1 files (B16 is WS2's and may also land); do not write simulate.py, match.py, indicators.py, calibrate.py, run.py, validate.py or blind.py. Tag only a commit already pushed to origin/main, and never rebase or force-push main after the tag. Every evaluation-seed run appends to validation/site_signal/run_log.jsonl. After the tag, implement S2–S9 exactly as the SAP specifies; any choice the SAP fixes must not change, and any change to a pre-specified choice gets a row in docs/11 §17 in the same commit. numpy and scipy live only in monitoring/; never import an LLM client anywhere in monitoring/; never hard-code a clinical threshold (grade with rules.py; read match, evaluability and minimum-data constants from data/signal_rules.json and tier thresholds from monitoring/out/thresholds.json). Use plan mode per task, run each acceptance check exactly as written, show the output, and commit as "WS5-Sn: <summary>". Never quote a Site Signal number that is not in validation/site_signal/summary.json.

## Ground rules

| Rule | How it is enforced |
|---|---|
| No LLM on the statistics path (CLAUDE.md rule 1) | `monitoring/tests/test_no_llm.py`: AST import scan of `monitoring/bvsignal/` and `backend/app/services/{site_signal,episodes,site_queries}.py` for `anthropic`, `google.genai`, `app.services.llm`, `claude`, `gemini`, `elevenlabs` (REQ-021). The same test asserts `backend/app/` imports no `numpy` or `scipy`. |
| Grades only from `rules.py`; no clinical thresholds in code (rule 2) | The simulator enumerates each item's answer domain and grades candidates with `rules.grade()` and `rules.red_flags()` through `bvsignal/_backend.py`. AST test: every numeric literal in `simulate.py`, `match.py` and `indicators.py` other than 0, 1 and −1 is rejected; values come from `params.yaml`, `data/signal_rules.json` or `thresholds.json` (REQ-023). |
| Pre-registration order | `test_sap_order.py` (REQ-022): the tag exists; its commit is an ancestor of every commit that adds files under `monitoring/out/` or `validation/site_signal/`; the eval seed equals the derivation from the tag commit and `monitoring/seed_beacon.json` (SAP §1.3); every committed output's sha256 is in `run_log.jsonl` and no log line predates the tag. Skipped with a visible reason outside a git checkout (Docker), never in CI (`fetch-depth: 0`, tags fetched). |
| Frozen inputs | `calibrate.py`, `run.py`, `validate.py` and `blind.py` recompute the `params.yaml` `frozen_inputs` hashes and refuse to run on a mismatch unless a SAP §17 row cites the new hash. |
| Thresholds read, never computed, at analysis time | Only `calibrate.py` writes `thresholds.json`; `indicators.py`, the blind run and the backend read it (REQ-023). |
| Never green (rule 5) | Below minimum data, below coverage, study below 10 computed sites, or any exception: `tier = not_computed` with a reason (REQ-025). Tier values are exactly `watch`, `look`, `none`, `not_computed`. |
| Labels (rule 6) | `test_labels.py`: every object in `monitoring/out/*.json` has `data_origin`; simulated quotes have `source: "synthetic"` (REQ-030). |
| Determinism | `test_determinism.py`: two runs of `make site-signal` give byte-identical outputs (sha256). |
| Licensed content (rule 9) | Matching uses CTCAE terms and our own synonyms in `data/signal_rules.json`; no MedDRA codes or hierarchy; `quote_bank.json` is our own patient-side wording, never PRO-CTCAE text, never spoken by the agent; the optional Synthea roster keeps age and language only, no SNOMED codes, no raw output, no jar in git. |

## Pre-registration sequence (the order is the evidence)

| Step | When | What | Check |
|---|---|---|---|
| 1 | by 02:20 | WS4 commits `data/signal_rules.json` and `data/site_queries.json` (D11). | `uv run --project backend python data/validate_data.py` exits 0 |
| 2 | 02:00–02:30 | S1: `monitoring/` skeleton, `params.yaml`, `seed.py`, `_backend.py`, `planning/plan_power.py`; `make planning-grid` with the dev seed applies SAP §11.5 rules P1 (design feasibility) and P2 (gross *f*). Time box 02:30, then the §11.5 fallback. | `jq .chosen monitoring/planning/planning_grid.json` |
| 3 | 02:30 | Fill `params.yaml` (`design.patients_per_site`, `planted.gross.f`, `signal_rules_sha256`, `frozen_inputs`) and `docs/11` §11.5; add the §1.5 change-log line; §17 stays empty. Commit the frozen files plus `monitoring/uv.lock` in one commit on `main`, rebase onto `origin/main`, push. | no file under `monitoring/out/` or `validation/site_signal/` in the commit |
| 4 | 02:45 | **Team lead** reviews the SAP diff. No OK by 01:45: tag anyway, §1.5 says "tagged without human review". | OK in the team chat |
| 5 | 02:45 | `git fetch origin && git tag -a sap-v1 origin/main -m 'Site Signal SAP v1' && git push origin sap-v1`. The tag is never moved or deleted; `main` is never rebased or force-pushed after it. | `git ls-remote --tags origin sap-v1`; `git rev-parse sap-v1^{commit}` = `git rev-parse origin/main` at tag time |
| 6 | 02:45–02:55 | Ask the team lead to publish the tag sha externally (GitHub Release on the tag; Devpost draft or organizer channel). | links in a §17 clarification |
| 7 | ~03:00 | After the beacon round (SAP §1.3): `uv run --project monitoring python -m bvsignal.seed --fetch-beacon`, commit `monitoring/seed_beacon.json` with a §17 clarification, then `--show` prints the tag commit, beacon round and eval seed. Post them in the team chat. | — |
| 8 | after the tag | Write S2–S9. Develop with the dev seed and small replicate counts; development outputs go to a scratch directory (`--seed dev --out <dir>`), never to `monitoring/out/` (`run.py` refuses). | — |
| 9 | ~05:00 | On a clean checkout of `main`: `calibrate.py` (stream 1) → `thresholds.json`; `make site-signal` (stream 0) → `monitoring/out/*.json` and `validation/site_signal/report.md`; every eval-seed run appends to `run_log.jsonl`; commit outputs and log together and push without rebasing afterwards. The first eval-seed run of a given code commit is the one committed. | `git merge-base --is-ancestor sap-v1 <commit>` |
| 10 | ~05:10 | `make site-signal-validate` (streams 2–4) in the background; commit `validation/site_signal/*.json` and the log. Then `make blind-run ARGS=--precompute`. | REQ-022, REQ-023 |
| 11 | any time after the tag | Every clarification or deviation: one row in `docs/11` §17 (date/time ET, commit, SAP section, type, change, reason, eval outputs seen?, expected effect), in the same commit as the change. A bug fix that changes committed outputs is regenerated from the **same** eval seed, logged in `run_log.jsonl`, and recorded in §17. | reviewer check |

Never: re-seed, re-tag, move the tag, choose among several evaluation runs, commit dev-seed outputs (except `planning_grid.json`), or quote a planning-grid value as a result.

## Layout

| Path | What |
|---|---|
| `monitoring/pyproject.toml`, `uv.lock` | Separate uv project, Python 3.12: numpy, scipy, pyyaml, pydantic, pydantic-settings (needed to import `app.content` and `app.services.rules`), pytest, ruff. Never imported by the backend. |
| `monitoring/params.yaml` | Pre-registered parameters; every number has a citation or an `ASSUMPTION` tag; frozen by `sap-v1`. |
| `monitoring/README.md` | How to run, seeds, outputs, SIMULATED labeling, MIT attribution for the simaerep port. |
| `monitoring/planning/plan_power.py`, `planning_grid.json` | Pre-tag simplified planning simulation (dev seed), "planning only, not a result". |
| `monitoring/bvsignal/_backend.py` | Adds `backend/` to `sys.path`; re-exports `app.services.rules` (`grade`, `red_flags`, `level_for`) and `app.services.episodes` (B16). No DB, no LLM imports. |
| `monitoring/bvsignal/seed.py` | Eval-seed derivation from `git rev-parse sap-v1^{commit}` and `monitoring/seed_beacon.json`; `--fetch-beacon` (drand, NIST fallback); `--show`; replicate keys `SeedSequence(eval_seed, spawn_key=(stream, cell_index, role, i))` (SAP §1.3); the run-log writer. |
| `monitoring/seed_beacon.json` | Beacon round and value, committed after the tag (SAP §1.2 step 7). |
| `monitoring/bvsignal/roster.py` | Parametric roster; optional Synthea language/age mix (S10, sensitivity only). |
| `monitoring/bvsignal/simulate.py` | Study generation and answer key (SAP §11.2, §11.4). |
| `monitoring/bvsignal/match.py` | Calls `episodes.py` for episodes, matching, evaluability and the paged stratum; adds coverage and minimum-data status (SAP §4–§7). |
| `monitoring/bvsignal/indicators.py` | LOSO O/E, z, winsorized φ, z\*, tiers from `thresholds.json`; gsm-style rate KRI; tier assignment for all three indicators; `not_computed` reasons; rank. |
| `monitoring/bvsignal/calibrate.py` | Pre-registered null → Look and Watch thresholds per indicator → `out/thresholds.json` (SAP §9). |
| `monitoring/bvsignal/simaerep_classic.py` | MIT port of simaerep's legacy `visit_med75` algorithm (SAP §10.2). |
| `monitoring/bvsignal/equity.py` | Within-site capture odds by language and pace; single-language counterfactual (SAP §14). |
| `monitoring/bvsignal/run.py` | `make site-signal`: eval seed → simulate → match → indicators → equity → `out/*.json` + report; < 60 s. |
| `monitoring/bvsignal/validate.py` | Operating characteristics (SAP §12); `--quick --check` for CI. |
| `monitoring/bvsignal/blind.py` | Blind-run CLI used by the backend (SAP §13); `--precompute`. |
| `monitoring/bvsignal/report.py` | `validation/site_signal/report.md` and `funnel.svg` from the JSON outputs. |
| `monitoring/quote_bank.json` | Synthetic EN/ES patient phrasings per term × grade, labeled synthetic. |
| `monitoring/cohort/` | Optional Synthea roster builder (S10). Raw output and the jar are never committed. |
| `monitoring/tests/` | `conftest.py` (registers `req`), `test_simulate.py`, `test_match.py`, `test_indicators.py`, `test_null_smoke.py`, `test_no_llm.py`, `test_simaerep_fixture.py`, `test_determinism.py`, `test_sap_order.py`, `test_labels.py`, `test_blind.py`, `test_equity.py`, `fixtures/`. |

## Make targets

| Target | Command | Notes |
|---|---|---|
| `planning-grid` | `uv run --project monitoring python monitoring/planning/plan_power.py --seed dev --out monitoring/planning/planning_grid.json` | Pre-tag only. |
| `site-signal` | `uv run --project monitoring python -m bvsignal.run` | Eval seed from the tag; < 60 s. |
| `site-signal-validate` | `uv run --project monitoring python -m bvsignal.validate $(ARGS)` | Full run ≤ 45 min in the background; `ARGS="--quick --check"` in CI. |
| `blind-run` | `uv run --project monitoring python -m bvsignal.blind --seed-label "$(SEED)" $(ARGS)` | `ARGS=--precompute` writes the fallback seeds. |
| `cohort` | `uv run --project monitoring python monitoring/cohort/build_roster.py` | Optional; Java 17+. |
| `test-monitoring` | `cd monitoring && uv run ruff check bvsignal tests && uv run pytest -q` | Added to `make test`. |

## Outputs

| File | Written by | Read by |
|---|---|---|
| `monitoring/out/thresholds.json` | `calibrate.py` (stream 1) | `indicators.py`, `blind.py`, backend `GET /api/sites` |
| `monitoring/out/signal_run.json`, `episodes.json`, `site_ae.json`, `answer_key.json` (key and per-indicator confusion), `equity.json` | `run.py` (stream 0) | backend `services/site_signal.py` (B17) |
| `monitoring/out/blind_precomputed/<label>.json` (10) | `blind.py --precompute` | backend blind-run fallback (B19) |
| `validation/site_signal/summary.json`, `power_grid.json`, `null_rate.json`, `sensitivity.json`, `failure_case.json` | `validate.py` (streams 2–4) | backend `GET /api/site-signal/validation`, UI "How well it works", README, deck, video, `WHAT_IT_GETS_WRONG.md` |
| `validation/site_signal/report.md`, `funnel.svg` | `report.py` | humans; README link |
| `validation/site_signal/run_log.jsonl` | every eval-seed run | `test_sap_order.py` (REQ-022) |

Every output carries `sap_tag_commit`, `eval_seed` and `code_commit` (SAP §15). `code_commit` is the last commit that changed an analysis input (`git log -1 --format=%H -- monitoring/bvsignal monitoring/params.yaml monitoring/uv.lock data/signal_rules.json data/ctcae_rules.json data/red_flags.json data/plan.json data/symptom_items.json backend/app/services/episodes.py backend/app/services/rules.py`), and `generated_at` is that commit's time, so committing outputs does not change them.

## Tasks

### S1 · `monitoring/` project, params.yaml, planning grid, tag `sap-v1` (target 02:45, checkpoint SAP)
- Create the uv project (`monitoring/pyproject.toml`, `uv.lock`), `bvsignal/__init__.py`, `tests/conftest.py` (registers the `req` marker) and `README.md`.
- `bvsignal/seed.py`: `eval_seed()` = `int(sha256(("sap-v1:" + S + ":" + B).encode()).hexdigest()[:8], 16)` with `S` the 40-hex output of `git rev-parse sap-v1^{commit}` and `B` the beacon value from `monitoring/seed_beacon.json` (SAP §1.3); `--fetch-beacon` selects the round from the tagger timestamp + 10 minutes, fetches it (drand; NIST only from round time + 30 min; the empty string only from round time + 60 min) and writes the file with every failed attempt (SAP §1.3); `key(stream, cell_index, role, i)` returns `SeedSequence(eval_seed, spawn_key=(...))`; `log_run(command, outputs)` appends to `validation/site_signal/run_log.jsonl` and refuses a dirty tree; `python -m bvsignal.seed --show` prints `sap_tag_commit=<sha> beacon_round=<n> eval_seed=<int>` and exits non-zero with a clear message before the tag or the beacon file exists, or outside a git checkout.
- `bvsignal/_backend.py`: `sys.path` setup and `rules` re-export (`episodes` is added in S2 once B16 lands). `plan_power.py` needs it to compute paged shares from `rules.red_flags()` (SAP §11.5).
- `params.yaml`: every block of the SAP §11.3 parameter table, each number with a citation or `ASSUMPTION`; `signal_rules_sha256` = sha256 of `data/signal_rules.json`; `frozen_inputs` (SAP §11.3); `seeds.dev: 20261011`, `seeds.eval: derived_from_sap_v1_tag_and_beacon`; a fixed `cell_index` enumeration of grid cells and scenarios.
- `planning/plan_power.py`: the simplified model of SAP §11.5 (with AESTDTC noise and the §5 match rule; no mapping error), dev seed. Rule P1 picks the patients-per-site range from 200 studies per range with the §11.4 composition; rule P2 calibrates once from 1000 null studies, then runs 500 studies per *f* with common random numbers and picks the smallest gross *f* in {0.75, 0.80, 0.85, 0.90} whose one-sided 80% lower bound of Watch power is ≥ 0.80 (else 0.90, shortfall recorded). Output labeled "planning only, not a result". Vectorize; time box 02:30, then the SAP §11.5 fallback (30–60, *f* 0.90, "planning grid not run").
- Fill `params.yaml` and `docs/11` §11.5 from `planning_grid.json`. Add the `planning-grid` Makefile target.
- One commit on `main` with the seven frozen files (`docs/11-site-signal-sap.md`, `monitoring/params.yaml`, `monitoring/uv.lock`, `data/signal_rules.json`, `data/site_queries.json`, `monitoring/planning/plan_power.py`, `monitoring/planning/planning_grid.json`) plus the project skeleton, rebased onto and pushed to `origin/main`. Team-lead review, then tag that pushed commit and push the tag; then the external timestamp and the beacon file (sequence steps 6–7).
- **Files:** `monitoring/pyproject.toml`, `monitoring/uv.lock`, `monitoring/README.md`, `monitoring/params.yaml`, `monitoring/planning/plan_power.py`, `monitoring/planning/planning_grid.json`, `monitoring/bvsignal/__init__.py`, `monitoring/bvsignal/seed.py`, `monitoring/bvsignal/_backend.py`, `monitoring/tests/conftest.py`, `monitoring/seed_beacon.json` (after the tag), `docs/11-site-signal-sap.md` (§11.5, §1.5; §17 clarifications after the tag), `Makefile` (`planning-grid`).
- **Depends on:** D11.
- **Accept:**
  ```bash
  make planning-grid && jq '.chosen' monitoring/planning/planning_grid.json
  test "$(yq -r .signal_rules_sha256 monitoring/params.yaml)" = "$(sha256sum data/signal_rules.json | cut -d' ' -f1)" && echo sha-ok
  git push origin main && git fetch origin && git tag -a sap-v1 origin/main -m 'Site Signal SAP v1' && git push origin sap-v1
  git ls-tree -r sap-v1 --name-only | grep -E '^(monitoring/out|validation/site_signal)/'
  git ls-tree -r sap-v1 --name-only | grep -cE '^(docs/11-site-signal-sap\.md|monitoring/params\.yaml|monitoring/uv\.lock|data/signal_rules\.json|data/site_queries\.json|monitoring/planning/plan_power\.py|monitoring/planning/planning_grid\.json)$'
  git merge-base --is-ancestor sap-v1 origin/main && echo tag-on-main
  # after the beacon round:
  uv run --project monitoring python -m bvsignal.seed --fetch-beacon && uv run --project monitoring python -m bvsignal.seed --show
  ```
  `.chosen` shows `patients_per_site` and `gross_f` (one of 0.75, 0.80, 0.85, 0.90) and whether each rule passed (or "planning grid not run"); `sha-ok`; the first `ls-tree` grep prints nothing; the count prints `7`; `tag-on-main`; `--show` prints the 40-hex tag commit, the beacon round and an integer eval seed. (Use `python -c` with pyyaml if `yq` is not installed.)

### S2 · `simulate.py` and `roster.py` (target 04:05, Checkpoint B)
- `_backend.py` re-exports `app.services.episodes` (B16).
- `roster.py`: parametric roster per `params.yaml` (`n_sites`, site IDs 101–120, patients per site, Spanish share by site, age → pace rule, enrollment spread). Site 101 is the live demo site (Hillside, fictional) and always honest. Fictional site names end in "(fictional)".
- `simulate.py`, following SAP §11.2 step by step: latent episodes per patient (frailty, *μ*, term mix, grade 3 share, duration in calls); q3w dosing and day-1/3/7 calls; per-patient call completion; patient answers generated by enumerating each item's answer domain (`answer_generation` in `params.yaml`) and grading the candidates with `rules.grade()`, red flags and page level from `rules.red_flags()` and `rules.level_for()`; mapping errors (same model in both languages); quotes from `quote_bank.json` with `source: "synthetic"` and labeled translations; the site AE log from the capture model (base capture by term × band, between-site and patient random effects, planted personalities from SAP §11.4), AESTDTC noise, entry lag, other non-symptomatic AEs; the answer key. Returns one `Study` object that every indicator reads (REQ-028).
- Random draws: each replicate's `SeedSequence` spawns separate children for the study and for comparator resampling, so adding or cutting a comparator never changes the simulated study or another indicator's result.
- `quote_bank.json`: synthetic EN/ES phrasings per term × grade, our own words written with AI assistance; `_about` says "synthetic patient phrasings, AI-assisted, not clinical wording; English translations are AI-assisted"; Spanish entries carry an English translation, emitted with `translation_is_ai: true` so the UI shows an `AiLabel`.
- S2 may start from `plan_power.py`'s roster and episode code rather than writing it twice.
- **Files:** `monitoring/bvsignal/_backend.py`, `monitoring/bvsignal/roster.py`, `monitoring/bvsignal/simulate.py`, `monitoring/quote_bank.json`, `monitoring/tests/test_simulate.py`.
- **Depends on:** the `sap-v1` tag, S1, B16.
- **Accept:**
  ```bash
  uv run --project monitoring pytest -q monitoring/tests/test_simulate.py
  ```
  Passes, covering: same seed → identical sha256 of the serialized study; every simulated grade equals `rules.grade()` on the generated answers; the numeric-literal AST check on `simulate.py`; answer-key counts equal the planted counts in `params.yaml`; site 101 is `honest`.

### S3 · `match.py` (target 03:15, Checkpoint B)
- Episodes, matching (SAP §5), evaluability (§6.1), paged stratum (§6.2) and status precedence (§6.4) come from `episodes.py`; `match.py` must not re-implement them. It adds site coverage, minimum-data checks in the SAP §7 order, and the study-level 10-site minimum. All constants from `data/signal_rules.json`.
- `test_match.py`, table-driven, ≥ 18 rows: window edges (AESTDTC = episode date + 7 matches, + 8 does not; AESTDTC = previous negative call − 2 matches, − 3 does not; no previous negative call → lower bound episode date − 21; worsened episode anchored on the last lower-grade call; SE1 and SE2 windows); one-to-one nearest-date greedy with the tie-break order; synonyms (case and whitespace); unmapped `aeterm` never matches; `origin = between_visits` never matches; `entered_on` after the data cut excluded; pending (both evaluability terms); paged (urgent and emergency) takes precedence over pending; coverage 0.59 vs 0.60; 9 vs 10 patients; 14 vs 15 evaluable episodes; study with 9 computed sites; a site with a `between_visits` row → `integrated_mode`; exception → `not_computed` with reason `error`; status precedence paged > pending > not_evaluated > matched/unmatched; an unmatched episode at a `low_coverage` site stays `unmatched`. Tag REQ-024 and REQ-025.
- **Files:** `monitoring/bvsignal/match.py`, `monitoring/tests/test_match.py`.
- **Depends on:** S2, B16.
- **Accept:** `uv run --project monitoring pytest -q monitoring/tests/test_match.py` passes with ≥ 18 parametrized rows (`pytest --collect-only -q monitoring/tests/test_match.py | grep -c '::'` ≥ 18).

### S4 · `calibrate.py` and `indicators.py` (target 03:30 code; thresholds run at about 05:00, Checkpoint B)
- `indicators.py` (SAP §8, §10.1, §10.3): leave-one-site-out *E* by cell, cluster-robust *V* (floored at the binomial variance), *z*, winsorized *φ̂* (10/90%) over computed sites, additive *τ̂²* and *z\** = (O − E)/√(V + τ̂²E²); gsm-style rate KRI with multiplicative *φ̂*; the AE-to-report ratio ablation; tier assignment for all three indicators from `thresholds.json` (discordance and rate KRI flag at ≤ threshold, simaerep classic at ≥ threshold, `docs/03` §5.1); every Watch site also passes Look; `not_computed` reasons; rank by `z_adj` ascending among computed sites; BH q-values on calibrated empirical p-values as a secondary column only.
- `calibrate.py` (SAP §9.2–9.3): stream 1, *R* = `r_null` = 2000 null studies at the `sap-v1` design, all three indicators and the ablation on each identical study; refuses on a `frozen_inputs` mismatch; logs the run; Look = pooled per-site 5% with the discreteness rule; Watch = 10% quantile of per-study minima; `c_watch := min(c_watch, c_look)`; writes `thresholds.json` with achieved in-sample rates, their MC SE and `expected_false_look_flags_per_study`. Vectorize; target < 10 min.
- Run the committed calibration once simaerep classic is fixture-green or cut (S5, 05:00 at the latest), so `thresholds.json` is written once.
- **Files:** `monitoring/bvsignal/calibrate.py`, `monitoring/bvsignal/indicators.py`, `monitoring/out/thresholds.json`, `monitoring/tests/test_indicators.py`, `monitoring/tests/test_null_smoke.py`, `monitoring/tests/test_no_llm.py`.
- **Depends on:** S3.
- **Accept:**
  ```bash
  uv run --project monitoring pytest -q monitoring/tests/test_indicators.py monitoring/tests/test_null_smoke.py monitoring/tests/test_no_llm.py
  time uv run --project monitoring python -m bvsignal.calibrate
  jq '{r_null, discordance, rate_kri, simaerep_classic, achieved}' monitoring/out/thresholds.json
  ```
  The hand-computed 3-site example reproduces O, E, V, *z* and *φ̂* to 1e-9; the null smoke test (200 replicates from a fresh stream) gives a Look per-site rate ≤ 0.085 and a Watch family-wise rate ≤ 0.16 (one-sided); `test_no_llm` passes; calibration finishes in < 10 min with `r_null: 2000`. Tags: REQ-021, REQ-023.

### S5 · simaerep classic (legacy) port with fixture test (target 03:45; cut at 05:00, Checkpoint B)
- `simaerep_classic.py`: SAP §10.2 step by step (evaluation point `visit_med75`, site mean, patient-resampling bootstrap `prob_low` = (1 + #)/(1 + *r*) with *r* = 1000 everywhere, vectorized, and simaerep's #/*r* form behind a flag for the fixture test, two-sample Poisson rate test with R `poisson.test` semantics, BH, `prob`). Labeled "simaerep classic (legacy)" in every output; the v1.0.0 inframe default is not ported.
- Fixture: `monitoring/tests/fixtures/simaerep_pval_fixture.csv`, extracted once from the regression data shipped in openpharma/simaerep v1.0.0 (`R/sysdata.rda`), with the MIT license text in `monitoring/tests/fixtures/SIMAEREP_LICENSE`. Commit the small extraction script next to it for reproducibility; its reader package is not a runtime dependency.
- **Files:** `monitoring/bvsignal/simaerep_classic.py`, `monitoring/tests/fixtures/simaerep_pval_fixture.csv`, `monitoring/tests/fixtures/SIMAEREP_LICENSE`, `monitoring/tests/test_simaerep_fixture.py`.
- **Depends on:** S1.
- **Accept:**
  ```bash
  uv run --project monitoring pytest -q monitoring/tests/test_simaerep_fixture.py
  ```
  10/10 site *p*-values match with maximum relative difference < 1e-9; the bootstrap `prob` matches within the Monte Carlo tolerance written in the test docstring. Tag REQ-028. **Cut:** not green by 05:00 → drop simaerep classic from the UI and `summary.json`, keep the gsm-style KRI, list it in `NOT_BUILT.md`, log a §17 row.

### S6 · `run.py` and report: `make site-signal` (target 05:10, Checkpoint B)
- `run.py`: eval seed (stream 0) → simulate → match → indicators (reading `thresholds.json`) → equity (S9, when present) → `monitoring/out/{signal_run,episodes,site_ae,answer_key}.json` (`answer_key.json` holds the key and the per-indicator confusion), then `report.py`. Deterministic; < 60 s. `code_commit` and `generated_at` follow the definition under Outputs, so two runs give byte-identical files even after the outputs are committed. Refuses a dirty tree and a `frozen_inputs` mismatch with the eval seed; appends to `run_log.jsonl`. Flags: `--seed dev|eval` (default `eval`) and `--out DIR`; with `--seed dev` it refuses to write into `monitoring/out/`. `signal_run.json` holds the run block of `GET /api/sites` (`id: "sr_committed"`, `data_origin`, `sap_tag_commit`, `eval_seed`, `generated_at`, `code_commit`, design, thresholds, `expected_false_look_flags_per_study`, `phi`, `n_computed_sites`), the sites, rows and funnel limits.
- `report.py`: `validation/site_signal/report.md` (ranked sites, three indicators, funnel image, answer-key confusion labeled "illustration only", the SAP link, §17 deviations that apply, and the statement that the only non-circular validation is retrospective analysis of trials with paired patient-reported and clinician-reported data) and `funnel.svg`. Every number badged SIMULATED.
- Makefile: `site-signal`, `test-monitoring`; `make test` runs `test-monitoring`; `make setup` syncs `monitoring/` (R2). CI job `monitoring`: `actions/checkout@v4` with `fetch-depth: 0` and `fetch-tags: true` (the tag must be present), `uv sync`, ruff, pytest.
- **Files:** `monitoring/bvsignal/run.py`, `monitoring/bvsignal/report.py`, `monitoring/out/*.json`, `validation/site_signal/report.md`, `validation/site_signal/funnel.svg`, `validation/site_signal/run_log.jsonl`, `monitoring/tests/test_determinism.py`, `monitoring/tests/test_sap_order.py`, `monitoring/tests/test_labels.py`, `Makefile`, `.github/workflows/ci.yml`.
- **Depends on:** S4, S5 (or its cut), D11.
- **Accept:**
  ```bash
  time make site-signal
  make site-signal && git diff --exit-code monitoring/out && echo deterministic
  git merge-base --is-ancestor sap-v1 "$(git log --diff-filter=A --format=%H -- monitoring/out/signal_run.json | tail -1)" && echo order-ok
  uv run --project monitoring pytest -q monitoring/tests/test_determinism.py monitoring/tests/test_sap_order.py monitoring/tests/test_labels.py
  ```
  Under 60 s; `deterministic`; `order-ok` (after the outputs are committed); tests pass. Tags: REQ-022, REQ-030.

### S7 · `validate.py`: operating characteristics (full run target 05:50, Checkpoint B)
- SAP §12: null false-flag rates on stream 2 (*R* = 2000, fresh null studies, `sap-v1` thresholds), Look per-site rate with cluster-aware MC SE, overall and by *E* tertile, expected false Look flags per study and Watch family-wise rate with MC SE and Clopper-Pearson CI, also by *K* bin, computability; power grid on stream 3 (per-design calibration from 1000 null studies reused across *f*, common random numbers across *f*, both tiers, all three indicators and the ablation, P(computed), each design's achieved null rates, the `sap-v1` design row with committed thresholds next to its planning value; *f* = 0.25 and 0.50 rows always present); full planted mix with FDR and equity coverage; paired comparator head-to-head (grid primary, full-mix rows labeled); failure case (a) and (b) on stream 4; sensitivity SE1–SE21; committed-study confusion labeled illustration only.
- Writes `validation/site_signal/{summary.json, power_grid.json, null_rate.json, sensitivity.json, failure_case.json}`; `summary.json` follows SAP §12.9 and is the single source of every Site Signal number.
- Runtime budget ≤ 45 min in the background. Fallbacks in SAP order (grid reps down to no fewer than 200; simaerep classic only on the design row and full mix), each logged in §17.
- `--quick --check`: the first `r_quick` replicates of the same keys; exits non-zero unless the sha256 of each stream's per-replicate results equals `summary.json` `quick_hashes` exactly (SAP §12). Added to the CI `monitoring` job.
- **Files:** `monitoring/bvsignal/validate.py`, `validation/site_signal/summary.json`, `power_grid.json`, `null_rate.json`, `sensitivity.json`, `failure_case.json`, `Makefile` (`site-signal-validate`), `.github/workflows/ci.yml`.
- **Depends on:** S6.
- **Accept:**
  ```bash
  make site-signal-validate        # background, <= 45 min
  jq '{null: .null, n_power_rows: (.power|length), has_f025: ([.power[]|select(.f==0.25)]|length>0), has_f050: ([.power[]|select(.f==0.5)]|length>0), failure_case: (.failure_case!=null), sensitivity: (.sensitivity|length)}' validation/site_signal/summary.json
  time make site-signal-validate ARGS="--quick --check"
  ```
  `null` shows `look_per_site`, `look_per_study` and `watch_fwer` each with `rate` and `mc_se`, `look_per_site_by_e_tertile` and `r: 2000`; both *f* flags are `true`; failure case present; 21 sensitivity rows; the REQ-023 acceptance in SAP §12.1 holds or its failure is reported; quick check exits 0 in < 90 s.

### S8 · `blind.py` CLI and precomputed seeds (target 05:25, Checkpoint B)
- SAP §13: `seed_int` from the label; planted count *K* uniform on {0..3} at the gross *f* among non-101 sites, nothing else planted; full pipeline with the fixed `thresholds.json` (its sha256 reported); JSON on stdout with rows, `thresholds_sha256`, `code_commit`, `sap_tag_commit`, the answer key and the per-indicator confusion (the backend stores both and hides them until reveal). Target < 10 s.
- `--precompute` writes the 10 labels in `params.yaml` `blind_run.precomputed_labels` to `monitoring/out/blind_precomputed/<label>.json`.
- **Files:** `monitoring/bvsignal/blind.py`, `monitoring/out/blind_precomputed/*.json`, `monitoring/tests/test_blind.py`, `Makefile` (`blind-run`).
- **Depends on:** S4.
- **Accept:**
  ```bash
  time make blind-run SEED=demo-42
  make blind-run ARGS=--precompute && ls monitoring/out/blind_precomputed | wc -l
  uv run --project monitoring pytest -q monitoring/tests/test_blind.py
  ```
  JSON rows, the key and the confusion print in < 10 s (`demo-42` is not a precomputed label, so this exercises the CLI); `10` files; the test shows the same label gives identical output, the planted count over 200 labels covers 0–3, and every precomputed file equals the CLI output for its label.

### S9 · `equity.py` (target 05:40, Checkpoint B; UI at C)
- SAP §14: Mantel-Haenszel odds ratio across sites with ≥ 5 evaluable episodes per group, patient-cluster bootstrap 95% CI (*B* = 2000) as primary and Robins-Breslow-Greenland as secondary, Breslow-Day heterogeneity, per-site odds ratios with within-site bootstrap intervals (point estimate only below 10 episodes per group), site × term sensitivity; pace as a built-in negative control; single-language counterfactual per site (`tier_now`, `tier_if_english_only`, reason, share of patients with no reference stream); "power is low" note. Writes `monitoring/out/equity.json` from `run.py`.
- **Files:** `monitoring/bvsignal/equity.py`, `monitoring/out/equity.json`, `monitoring/tests/test_equity.py`.
- **Depends on:** S6.
- `equity.py` draws only from its own keys (stream 0, `role` 2, SAP §1.3), so adding it changes no other committed output.
- **Accept:** `uv run --project monitoring pytest -q monitoring/tests/test_equity.py` passes: the MH odds ratio and RBG variance on a hand-built 2-site table match a hand computation; the bootstrap is reproducible from its keys; `equity.json` has `language` and `pace` blocks with `ci95` and one counterfactual row per site. After `make site-signal`, the other outputs are unchanged apart from the provenance fields `code_commit` and `generated_at` (compare the previous and new files with those fields deleted by `jq`). REQ-031 is tagged now and added to `requirements.yaml` at Checkpoint C with the UI (F17), after D12.

### S10 · Optional Synthea roster, language and age mix only (Checkpoint C; drop at 05:50)
- `monitoring/cohort/build_roster.py` downloads a pinned Synthea jar and refuses on a sha256 mismatch; `manifest.json` records the jar sha256, Synthea commit, seeds and arguments; `roster.json` keeps age and language only (no names, no organizations, no SNOMED codes); `NOTICE` carries Synthea's Apache-2.0 notice. Raw output and the jar are never committed.
- Pre-registration: `params.yaml` fixes the parametric roster for the committed study. A Synthea roster is reported only as a labeled sensitivity result (`make site-signal ARGS="--roster synthea"` → a "Roster source" section in `report.md`, "roster language and age mix from Synthea; everything else parametric"). It never replaces the committed study; log a §17 clarification.
- **Files:** `monitoring/cohort/build_roster.py`, `monitoring/cohort/manifest.json`, `monitoring/cohort/roster.json`, `monitoring/cohort/NOTICE`, `monitoring/bvsignal/roster.py`, `Makefile` (`cohort`).
- **Depends on:** S2; Java 17+ locally.
- **Accept:** `make cohort` with a wrong pinned hash exits non-zero; with `roster.json` present, `make site-signal ARGS="--roster synthea"` writes the sensitivity section and leaves `git diff --exit-code monitoring/out` clean; without it all tests pass.

## Requirements (planned)

Tag tests now with `@pytest.mark.req("REQ-0xx")`. A requirement enters `validation/requirements.yaml` only in the commit that adds its passing test (`make validate ARGS=--check` fails CI otherwise). Requirements whose only tests live in `monitoring/tests/` (REQ-022, REQ-028, REQ-031, and the monitoring parts of REQ-023) can be added only once D12 makes `build_traceability.py` collect monitoring tests, or in the same commit as D12.

| REQ | Title | WS5 tests |
|---|---|---|
| REQ-021 | No LLM on the statistics path | `test_no_llm.py` |
| REQ-022 | Pre-registration order | `test_sap_order.py` |
| REQ-023 | Calibrated thresholds | `test_null_smoke.py`, `validate --quick --check`, numeric-literal check |
| REQ-024 | Stream independence | `test_match.py` (with B16 `test_episodes.py`) |
| REQ-025 | Never green | `test_match.py` (with B17) |
| REQ-028 | Comparators on identical data | `test_simaerep_fixture.py`, shared `Study` object check |
| REQ-030 | SIMULATED / MEASURED labeling | `test_labels.py` (with B17 schema walk) |
| REQ-031 | Site Signal equity strata | `test_equity.py` |

## Reporting rules (for everyone who quotes WS5 output)

- Numbers come only from `validation/site_signal/summary.json`, `monitoring/out/*.json` or `answer_key.json`. Planning-grid values and figures from before the SAP are never quoted.
- Every simulated rate shows its MC SE; every fixed-sample proportion shows a Clopper-Pearson 95% CI; power is always shown at both tiers, including the *f* = 0.25 and 0.50 rows; the failure case is shown next to favourable rows.
- Wording: "capture discordance", "a reason to look, not a finding", "No signal at this sample size". Never "clean", never green, never "detects under-reporting", "fraud" or "misconduct".
- Rounding (SAP §15): proportions 2 dp; MC SE and CI limits 3 dp; *z* 2; O/E 2; *E* and *V* 1.

## Cut rules for WS5

- Never cut: the SAP-before-data order, the null false-flag rate with MC SE, the *f* = 0.25 and 0.50 rows, SIMULATED labels, the failure case.
- 01:00: planning grid not finished → SAP §11.5 fallback (30–60 patients per site, gross *f* 0.90), "planning grid not run".
- 01:45: no SAP review OK → tag anyway with "tagged without human review" in §1.5.
- 04:00: simaerep classic not fixture-green → drop it (S5 cut).
- 04:30: Checkpoint B behind → `/sites` and `/sites/[id]` read-only plus `report.md`; the query flow and blind run go to `NOT_BUILT.md` (WS2/WS3 cut). S8 output stays committed if it exists.
- Blind run slower than 10 s on the host → the backend serves precomputed seeds only (`BLIND_RUN_TIMEOUT_S=0`).
- 05:00: S10 not done → parametric roster only.
- 06:30: equity UI not done → equity numbers stay in `report.md` and the "How well it works" tab.

## Handoffs

| To | What | When |
|---|---|---|
| WS2 B16 | The SAP §4–§6 rules for the shared `episodes.py`; WS5 reviews its tests | 03:30 |
| WS2 B16b, B17 | WS2 builds against its own hand-written fixtures (B16b, ~04:05; WS5 reviews their shapes); WS5 hands over the committed `monitoring/out/` | ~05:10 |
| WS2 B19 | `blind.py` CLI contract and the precomputed seeds | 05:25 |
| WS3 F12, F16, F17 | `signal_run.json` funnel limits, `summary.json`, `equity.json` | ~05:10, ~05:50 |
| WS4 D12, D13, D14 | Monitoring tests with `req` tags; `summary.json` for `WHAT_IT_GETS_WRONG.md` and the deck | 05:50 |
