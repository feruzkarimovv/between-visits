# 11 · Site Signal statistical analysis plan (SAP)

The pre-registered analysis plan for Site Signal, the sponsor-side statistical layer described in [`docs/10-site-signal.md`](10-site-signal.md). It fixes, before any evaluation output exists:

- the estimand;
- the episode, match and evaluability rules;
- the indicator, the null model and the thresholds;
- the comparators;
- the simulation used to evaluate all of these;
- what may be reported.

Interfaces are in [`docs/03-api-contracts.md` §5](03-api-contracts.md). Tasks are S1–S10 in [`docs/workstreams/WS5-site-signal.md`](workstreams/WS5-site-signal.md) and D11 in WS4. **On statistics, this document overrides every other doc.**

**Status: frozen by the annotated tag `sap-v1` (§1.5). No evaluation output exists at the tag.** Owner: WS5. WS4 owns the data files frozen with it.

| | |
|---|---|
| Version | `sap-v1` (annotated git tag, pushed) |
| Frozen together | This file, `monitoring/params.yaml`, `data/signal_rules.json`, `data/site_queries.json`, `monitoring/planning/plan_power.py`, `monitoring/planning/planning_grid.json`, `monitoring/uv.lock`. `params.yaml` `frozen_inputs` also pins the hashes of the grading and paging inputs (§11.3). |
| Filled at tag time | Design patients per site and gross capture loss *f* (§11.5) |
| Evaluation seed | Derived from the `sap-v1` commit and a public randomness beacon published after the tag (§1.3); `uv run --project monitoring python -m bvsignal.seed --show` prints it |
| Data | Both streams of every Site Signal study are **SIMULATED**. Only live and replayed calls at site 101 are **MEASURED** (§2.3). |
| Results | None in this file. Every number comes from `validation/site_signal/summary.json` (§15). |
| Data-file schemas | `data/signal_rules.json` and `data/site_queries.json`: `docs/02-data-model.md` § Files behind Site Signal (exact key names) |
| Deviations | §17 (empty at the tag) |

---

## 1. Purpose, status and pre-registration

### 1.1 Purpose

Site Signal asks one question per site:

> Among the symptom episodes that a site's own patients reported to Between Visits, does the site's own AE log contain fewer matching entries than the other sites record for the same symptom mix?

The answer is a ranked list of sites with two tiers, **Watch** and **Look**: a reason to look, not a finding. It supports centralized monitoring as ICH E6(R3) describes it: qualified staff, including statisticians, review accumulated data to find site-specific issues and choose where to look [5]. We paraphrase that guideline here and have not checked the wording against the PDF (UNVERIFIED).

Ground rules. Each one is enforced by a planned requirement listed in `docs/07` §6.

| Rule | Requirement |
|---|---|
| **No LLM anywhere on this path.** Grades and red flags come from `backend/app/services/rules.py`, which reads `data/ctcae_rules.json` and `data/red_flags.json`. Episodes, matches, statistics and tiers come from pre-specified code in `monitoring/` and `backend/app/services/{episodes,site_signal}.py`. | REQ-021 |
| **No clinical thresholds in `monitoring/` code.** The simulator grades the answers it generates with the real `rules.py` (§11.2). The match, evaluability, minimum-data and tier constants are read from `data/signal_rules.json`, and the thresholds from `monitoring/out/thresholds.json`. | REQ-023 |
| **Never green.** Below minimum data, below coverage, or on any error, a site is grey "not computed" and the reason is shown. | REQ-025 |
| **Labels.** Every run, row and episode carries `data_origin` (`SIMULATED` or `MEASURED`; `MIXED` only for the site 101 card and queries that cite both kinds of episode). | REQ-030 |

What this plan does **not** claim:

- Capture discordance is not an under-reporting rate, not evidence of misconduct, and not a protocol deviation.
- The patient stream is a reference, not the truth. In Basch et al., patients reported symptoms earlier and more often than clinicians, but clinician reports were more closely associated with unfavorable outcomes [3].
- Discordance includes legitimate clinical judgment: baseline symptoms recorded as medical history, attribution, and grade conventions.

### 1.2 Pre-registration mechanics (task S1, checkpoint SAP, target Sun 02:45 ET)

1. Run `make planning-grid` with the dev seed (§11.5). Fill §11.5 and `monitoring/params.yaml` with the chosen design and gross *f*, and `params.yaml` `frozen_inputs` with the input hashes (§11.3). Leave §17 empty. **Time box:** if the planning grid has not finished by 02:30, use the fallback values in §11.5 and record "planning grid not run" there.
2. Commit the frozen files (Status table) in one commit on `main`, rebase it onto `origin/main` and push it. The tag goes on that exact pushed commit, never on a worktree commit that is rebased later.
3. Confirm that no evaluation output exists at that commit. This must print nothing:

   ```bash
   git ls-tree -r origin/main --name-only | grep -E '^(monitoring/out|validation/site_signal)/'
   ```

4. The team lead reviews the SAP diff (`docs/09`, human action at 02:45). If the OK has not arrived by 03:15, the tag is pushed anyway and the §1.5 change-log line says "tagged without human review"; review findings later become §17 entries.
5. Create and push the tag on the pushed commit:

   ```bash
   git fetch origin && git tag -a sap-v1 origin/main -m 'Site Signal SAP v1'
   git push origin sap-v1
   ```

   The tag is never moved or deleted. From this point `main` is never rebased or force-pushed. Commits that add evaluation outputs are made on a checkout of `main` after rebasing and are never rebased afterwards, so their ancestry from the tag stays intact.
6. **External timestamp.** Within 10 minutes of the push, publish the tag sha outside the team's control: a GitHub Release on `sap-v1` (server timestamp) and the sha posted in the Devpost draft or the event's organizer channel. The links go in a §17 clarification. The external timestamp must be earlier than the beacon round time (§1.3); if it is not, §17 says so.
7. **Beacon.** From the beacon round time defined in §1.3, `uv run --project monitoring python -m bvsignal.seed --fetch-beacon --wait` retries under the §1.3 deadlines and writes `monitoring/seed_beacon.json` (round, randomness, source URL, the selection times and every failed attempt), and `--show` prints the full tag commit sha, the beacon round and the evaluation seed. Commit the beacon file with a §17 clarification that cites its `attempts`.
8. Only then run the code that produces evaluation output: `calibrate.py`, `run.py`, `validate.py` and `blind.py --precompute`.

**What may be written before the tag.** Only the S1 files (`seed.py`, `_backend.py`, `plan_power.py` and the project skeleton) and B16 (`backend/app/services/episodes.py` and its table tests, which implement §4–§6 exactly and touch no simulated study). Simulation and analysis code (`simulate.py`, `match.py`, `indicators.py`, `calibrate.py`, `run.py`, `validate.py`, `blind.py`) is written after the tag and must implement this SAP. This SAP leaves some choices to the implementation, for example vectorization and file layout. Those choices must not depend on any evaluation output.

**Run log.** Every invocation of `calibrate.py`, `run.py`, `validate.py` or `blind.py --precompute` with the evaluation seed appends one line to `validation/site_signal/run_log.jsonl`: `{utc_time, code_commit, git_dirty, command, output_sha256}`. Evaluation-seed runs refuse a dirty working tree. The log is committed with the outputs.

REQ-022 (`monitoring/tests/test_sap_order.py`) checks from git history and the run log:

- the tag exists;
- the tag commit is an ancestor of every commit that adds files under `monitoring/out/` or `validation/site_signal/`;
- the evaluation seed equals the derivation in §1.3 from the tag commit and `monitoring/seed_beacon.json`, and the beacon round is the one the rule selects; a NIST `B` is backed by failed drand `attempts` at or after round time + 30 min, and an empty `B` by failed drand and NIST `attempts` at or after round time + 60 min;
- every committed evaluation output's sha256 appears in `run_log.jsonl`, and no log line predates the tag.

The tag and beacon fix the seed; the external timestamp shows when the tag existed; the run log shows every evaluation run. Git timestamps alone are set by the author and are not treated as evidence.

### 1.3 Seeds

| Seed | Definition | Used for |
|---|---|---|
| Dev seed | `20261011` (`params.yaml` `seeds.dev`) | Development, unit tests and the pre-tag planning grid only. Outputs made with it are never committed, except `planning_grid.json`. |
| Evaluation seed | `int(sha256(("sap-v1:" + S + ":" + B).encode()).hexdigest()[:8], 16)`. `S` is the 40-hex output of `git rev-parse sap-v1^{commit}`. `B` is the hex randomness of the first drand mainnet round [25] whose time is at least 10 minutes after the tagger timestamp of `sap-v1`. Its *round time* follows from the chain parameters pre-registered in `params.yaml` `seeds.beacon.drand`, so it is known without the network. drand is retried at least once a minute from the round time. Fallback: the output value of the first NIST beacon pulse [26] at least 10 minutes after the tagger timestamp, used only if drand has not returned the round by round time + 30 min. `B` is the empty string only if neither has returned it by round time + 60 min. Every failed attempt (UTC time, URL, error) is recorded in `monitoring/seed_beacon.json` `attempts` and cited in §17. All deadlines are relative to the round time; no clock time applies. | Everything in `monitoring/out/` and `validation/site_signal/` |
| Blind-run seed | `int(sha256(("blind:" + seed_label).encode()).hexdigest()[:8], 16)` | One blind run (§13). Independent of the evaluation seed. |

The beacon value cannot be known when the tag is created, so nobody can choose a favourable seed by re-making the tag commit; the external timestamp (§1.2 step 6) shows the tag existed before the beacon round. Because the fallback deadlines are relative to the round time and every failed attempt is committed with the beacon file, a NIST or empty `B` can be checked to have been forced by the rule rather than chosen. The beacon file is written once and never replaced (§1.4).

Streams. Every replicate is keyed explicitly [18]:

```python
numpy.random.SeedSequence(eval_seed, spawn_key=(stream, cell_index, role, i))
```

| `stream` | Use | Consumer |
|---|---|---|
| 0 | Committed evaluation study (`role` 0); equity bootstrap (`role` 2) | `run.py` → `monitoring/out/*.json` |
| 1 | Null calibration | `calibrate.py` → `thresholds.json` |
| 2 | Null validation (fresh null studies); equity bootstrap inside a replicate (`role` 2, §12.3) | `validate.py` → `null_rate.json` |
| 3 | Power grid, per-design null calibration, and full-mix power; equity bootstrap inside a replicate (`role` 2, §12.3) | `validate.py` → `power_grid.json` |
| 4 | Failure case and sensitivity | `validate.py` → `failure_case.json`, `sensitivity.json` |

- `cell_index` comes from a fixed enumeration of grid cells and scenarios in `params.yaml` (0 where there is no cell). `role` is 0 for a null or committed study, 1 for a power (planted) replicate, 2 for resampling inside one analysis. `i` is the replicate number.
- Adding, cutting or reducing a cell therefore never changes another cell's draws. Every random draw of one simulated study, including comparator resampling, comes from that replicate's generator; comparator resampling uses a child of it so adding or cutting a comparator never changes the study.
- CI quick mode (`--quick`) runs the first `r_quick` replicates of the same keys, so quick results are an exact subset of the full run.

### 1.4 Amendments and deviations

| When | Change | How it is handled |
|---|---|---|
| Before the tag | Anything | Edit freely and add a change-log line (§1.5). |
| After the tag, before any evaluation output is committed | Clarification that changes no pre-specified choice | §17 entry, type `clarification` |
| After the tag, before any evaluation output is committed | Change to a pre-specified choice | §17 entry, type `deviation`, with the reason. The tag and the seed stay as they are. |
| After evaluation outputs exist | Change to a pre-specified choice | §17 entry. The pre-specified analysis is still run and reported as primary. The changed analysis is reported next to it and labeled. |
| Substantive redesign (estimand, null model, tier definition) | — | New tag `sap-v2`, which derives a new evaluation seed. Results of both versions stay committed and are both reported. |

Never allowed: re-seeding, re-tagging, or choosing among several evaluation runs. Each §17 entry records the date and time (ET), the commit, the SAP section, the change, the reason, whether evaluation outputs had been seen, and the expected effect on results.

### 1.5 Change log

| Version | Date | Change |
|---|---|---|
| draft | 2026-10-11 (planning round) | First full draft. |
| draft | 2026-10-11 (SAP review round 1, before the tag) | §4.1–§4.2: exact mapping from a call's answers to *g_k* (absent = 0, ungraded or not asked = null); §11.2 step 5: follow-ups after a gate mapping error. §1.2 step 7, §1.3: beacon fallback deadlines relative to the round time, attempt log in `seed_beacon.json`. §11.2 step 6, §11.3, §15 rule 7: active red flags from `data/plan.json`; `frozen_inputs` also pins red-flag ids, the plan's red-flag list and the primary-term item logic. §15 rule 6, §12.1, §12.9: rounding is for display only; gates use unrounded values. §11.2 steps 4, 7, 8, §11.3: secondary items per call, other-AE entry date, `aeseq`, entry-date formula. |
| draft | 2026-10-11 (SAP review round 2, before the tag) | §12.3, §12.9, §14, §11.3, §1.3: equity validation fixed before the tag. Language-interval coverage uses the first `equity_validation.r` = 500 null studies of §12.1, where no language gap is planted, with not-computed studies reported separately; pace-interval exclusion uses those null studies and the §12.3 full-mix studies; inside a validation replicate the §14 bootstrap uses *B* = `equity_validation.b` = 1000 resamples from `role` 2 keys. §12.5, §12.2, §12 fallback 1, §11.3: replicate counts fixed for the failure case (`failure_case.r_null` 1000 and `reps` 300 per grid *f* for (a), `r_null_b` 1000 for (b)) and for the `sap-v1` design row (`grid.reps` per grid *f*, cell 25, `role` 1); fallback 1 also covers failure-case reps. |
| draft | 2026-10-11 (SAP review round 3, before the tag) | §12.6 SE16: correlated reporting propensity fixed as a Gaussian copula that keeps the §11.2 marginals (normal-scale correlations 0.5 between *z_v* and each of *z_π*, *z_ε*, and 0.25 between *z_π* and *z_ε*). §12.6 SE15: capture boost fixed per simulated study (sites ranked by the share of completed calls at an urgent or emergency level, ties to the lower site id; latent episodes whose start day is within 7 days of such a call of the same subject, paged or not). §6.2, §11.2 step 7: wording aligned. `params.yaml` `sensitivity.scenarios` SE15, SE16 mirror both. |
| draft | 2026-10-11 (SAP review round 4, before the tag) | §11.2 step 5, §11.3: mapping-error step fixed (each recorded primary-term answer independently; ordinal next option up or down with probability 1/2, the only neighbour at a scale end; yes/no flip; stools ±1, +1 at 0; temperature ±0.5 °C; signs with probability 1/2), mirrored in `params.yaml` `patient_stream.mapping_error_step` (`p_up`, `at_scale_end`). §12.6: SE17 (one site drawn from the replicate's generator among the non-101 sites labeled `honest`, all non-101 sites in a null study; entry lag Gamma(shape 2, mean 25 days) for its symptomatic and other-AE rows), SE18 (3 non-101 sites of any label, drawn without replacement; one *ε_s* ~ Beta(2, 18) per site replaces *ε_i* for each of its patients), SE7, SE8 (κ = 20 kept; `low_coverage` keeps mean 0.50) and SE9–SE11 (`honest_low_diligence` offset −1.5 × the scenario SD) fixed and mirrored in `params.yaml` `sensitivity.scenarios`. §11.3 `frozen_inputs`, §15 rule 7: `backend/app/content.py`, through which `rules.py` selects items, grading rules and red flags, is hash-frozen (`content_py_sha256`), and `content.py` and `config.py` join the `code_commit` path list. |
| `sap-v1` | 2026-10-11 | §11.5 values filled from the planning grid (P1 shortfall, P2 shortfall); `frozen_inputs` filled; reviewed by agent with a statistician's lens (4 rounds; findings fixed before the tag); team lead review pending; frozen. |

---

## 2. Data sources

### 2.1 Reference stream (patient-reported)

The reference stream is what patients tell the voice agent on calls 1, 3 and 7 days after each dose (`data/plan.json` `schedule_days_after_dose`). For each completed call and each primary term (§4.1), it supplies:

- subject ID;
- local call date in `DISPLAY_TZ`;
- the `rules.py` provisional grade and `grade_basis`;
- the highest escalation level raised on the call;
- evidence: verbatim quote, `quote_lang`, `t_s`, source.

| Origin | How it is produced | Label |
|---|---|---|
| Simulated sites 101–120 | `monitoring/bvsignal/simulate.py` generates answers, grades them with the real `rules.py` and evaluates red flags with `rules.red_flags()` (§11.2) | SIMULATED, quote source `synthetic` |
| Live site 101 | Findings and escalations in the app database from real browser calls and replays. `services/site_signal.py` builds episodes with `episodes.py`. | MEASURED, quote source `live_call` or `replay` |

### 2.2 Site AE stream (comparison)

The comparison stream is a simulated, SDTM-style AE log, one row per AE (`monitoring/out/site_ae.json`, model `SiteAE` in `docs/03` §5). The fields used here:

| Field | Use |
|---|---|
| `subject_id` | Matching is within subject |
| `aeterm` | Mapped to a CTCAE term through `data/signal_rules.json` `match.term_synonyms` (lower-cased, trimmed, exact match). Unmapped rows never match; the rate KRI still counts them. |
| `aestdtc` | Match window (§5) |
| `entered_on` | A row is in the log at the data cut only if `entered_on <= data_cut` |
| `origin` | Only `site` rows are used. `between_visits` rows (confirmed Between Visits drafts) are excluded from matching and from the comparators (REQ-024). |
| `symptomatic` | `false` marks non-symptomatic AEs (labs, other events), which only the comparators use |
| `aetoxgr` | Descriptive only. A grade disagreement is not a mismatch. |

Every site's AE log is simulated, including site 101's. Confirmed drafts from live calls reach `ae.csv` with `ORIGIN=between_visits` and AESTDTC equal to the local call date (`docs/03` §5), so they never enter matching.

### 2.3 What is simulated and what is measured

| Element | Status | Where |
|---|---|---|
| Roster, calls, answers and episodes at sites 101–120 (committed study and blind runs) | SIMULATED | `monitoring/out/episodes.json`, `signal_run.json`, `blind_precomputed/` |
| Site AE logs, all sites including 101 | SIMULATED | `monitoring/out/site_ae.json` |
| Grades and red flags on simulated answers | Real code (`rules.py`) applied to SIMULATED answers | — |
| Quotes on simulated episodes | SIMULATED: synthetic, our own words, never spoken by the agent | `monitoring/quote_bank.json` |
| Operating characteristics (null rates, power, failure case, sensitivity) | SIMULATED | `validation/site_signal/*.json` |
| Live and replayed episodes at site 101 | MEASURED | App database |
| Voice-agent capture and grading accuracy by language and pace | MEASURED, in text mode with 20 simulated patients | `eval/results/latest.json` |
| Real-call re-verification | MEASURED | `eval/results/voice_checks.json` |

### 2.4 Independence (shadow mode only)

The analysis assumes **shadow mode**, defined operationally: during the analysis period, Between Visits drafts are reviewed only by a sponsor-side central reviewer and are never shown to site roles. Pages to the on-call nurse still happen (rule 5); they are handled by rule 2 below. The site enters AEs from its own visits.

Three rules limit the dependence that remains:

1. `origin = between_visits` rows are excluded (§2.2). This prevents our own confirmed drafts from matching themselves. It does **not** make the streams independent: a site that saw a draft may change its own entries.
2. Episodes on paged calls form a separate stratum (§6.2).
3. Episodes inside the site's entry window are pending (§6.1).

**Guard.** A site with any `origin = between_visits` AE row, or any draft action by a site role (coordinator or investigator) in the analysis window, is not computed with reason `integrated_mode` (§7, order 2). Under integrated mode a site that confirms our draft instead of writing its own row would look like a low-capture site, so the indicator would penalise it for doing the right thing.

Integrated mode is out of scope; a different indicator, based on draft rejection behavior, would be needed and is not built. Site 101's live bridge is integrated by construction (its coordinator reviews drafts), so its MEASURED episodes are descriptive only and never enter any statistic (§2.3, §15 rule 2). The simulated study has no `between_visits` rows, so the guard never fires there.

---

## 3. Estimand

The attributes follow ICH E9(R1) [4], adapted from treatment effects to a site-level monitoring quantity.

| Attribute | Definition |
|---|---|
| Units of inference | Sites of one study running Between Visits in shadow mode (§2.4) |
| Analysis unit | An **episode** (§4): one new or worsened, rule-graded grade ≥ 2 occurrence of Diarrhea, Fever or Dyspnea for one subject |
| Analysis set *A_s* | Episodes at site *s* that are evaluable at the data cut (§6.1) and not in the paged stratum (§6.2). Paging depends on the patient's answers, so the paged exclusion is a restriction of the analysis set, not an intercurrent-event strategy. |
| Variable | *Y_e* = 1 if episode *e* is matched (§5) to a site-originated AE, else 0 |
| Standardization strata | Cell *c_e* = term × grade band (2 or 3). Under the frozen red-flag rules every Fever episode and every grade 3 episode is paged (§4.4), so the strata that actually occur in *A_s* are Diarrhea G2 and Dyspnea G2; the standardization adjusts for that mix. |
| Intercurrent events and handling | Entry window not yet passed: pending, excluded. Missed or incomplete calls: no information, and the coverage guard applies (§7). Answers graded `needs_clinician`: not an episode. Confirmed Between Visits drafts in the site log: never matchable. Treatment discontinuation, withdrawal or death: episodes dated after the subject's end of AE collection are not evaluable. Dose delays: "next scheduled dose visit" (§6.1) is the actual next dose date. |
| Site-level summary | Capture ratio *θ_s*, defined below |
| Direction | One-sided. Interest is in lower capture (*θ_s* < 1). |

```math
\theta_s \;=\; \frac{\sum_{e \in A_s} p_s(e)}{\sum_{e \in A_s} \bar\pi_{-s}(c_e)}
```

Here *p_s(e)* is site *s*'s probability of capturing episode *e*, given its patient, and *π̄₋ₛ(c)* is the episode-weighted mean capture probability for cell *c* among the other sites of the same study. *θ_s* is conditional on *A_s* and relative to the other sites of this study: it is not a fixed site attribute and is not comparable across studies. The estimate is *O_s / E_s* and the test statistic is *z\*_s* (§8). *θ_s* < 1 means the site recorded fewer of its own patients' episodes than the other sites record for the same term-and-band mix. The term used in the UI and docs is **capture discordance**.

---

## 4. Analysis set: episodes

### 4.1 Graded input

| Term | Rules in `data/ctcae_rules.json` | Role |
|---|---|---|
| Diarrhea, Fever, Dyspnea | G1, G2, G3 | **Primary terms** (`signal_rules.json` `primary_terms`), at grade bands 2 and 3 |
| Fatigue, Dizziness | G1 only | Reported, ungraded context. Never an episode. |
| Nausea, Vomiting, Rash, Confusion | No rule | Reported, ungraded context. Never an episode. |

Under the frozen red-flag rules only Diarrhea G2 and Dyspnea G2 episodes reach *A_s* (§4.4); Fever and grade 3 episodes are all paged. No grade bands are created for terms without rules, and no conversion table from patient-reported answers to CTCAE grades is made. A primary-term answer that reports the symptom but has `grade_basis = needs_clinician` (no rule matched, for example a missing stool count) gives no information for that term on that call. It neither opens nor closes an episode. An answer that reports the symptom absent is grade 0 and closes an open episode (§4.2 gives the exact mapping). The ungraded answers are counted per site as "ungraded primary-term reports" in `report.md` only.

### 4.2 Episode construction

Construction is deterministic and identical in `monitoring/` and the backend: the one implementation is `backend/app/services/episodes.py` (task B16, stdlib only, table-driven tests). The parameters come from `signal_rules.json` `episode`.

For each subject and primary term, completed calls are taken in date order. Only calls with `status = completed` count (§6.3). Let *g_k* be the call's provisional grade for the term. For a completed call on which the term's items were asked, *g_k* = 0 when `rules.term_present(term, answers)` is false; otherwise *g_k* = `rules.grade(term, answers, baseline).provisional_grade`, which is null when `grade_basis` = `needs_clinician`. A term not asked on the call has *g_k* = null; an item answered `unknown` or `not_measured` counts as not answered, so a term whose only answers are of that kind has *g_k* = null. The simulator and `services/site_signal.py` both derive *g_k* this way. So grade 0 means the patient reported the symptom absent, and null means no gradable answer.

1. **Open (new).** An episode opens at call *k* when *g_k* ≥ 2 and no episode is open. Kind is `new`. The band is *g_k*.
2. **Continue.** If an episode is open and *g_k* ≥ 2 with *g_k* ≤ its band, call *k* is folded into the same episode (`checkin_ids` grows). A fall from 3 to 2 continues the episode. Its band stays 3.
3. **Worsen.** If an episode is open and *g_k* is above its band, the open episode closes at the previous call. A new episode opens at call *k* with kind `worsened` and band *g_k*.
4. **Close.** An open episode closes at the first completed call with *g_k* < 2.
5. **Gap.** If the next completed call with a non-null grade for the term comes more than `gap_days` = 21 days after the episode's last reporting call, the episode closes at its last reporting call. A grade ≥ 2 at that next call opens a new `new` episode.
6. **Null grades.** A call with a null grade for the term is skipped for that term. The 21-day gap rule still applies.

### 4.3 Episode date

**Episode date** = the `DISPLAY_TZ` local date of the first call folded into the episode. No onset item exists in the interview, and `postcall.py` sets no onset date. The episode date is therefore the date the patient told us, not the date the symptom started. In the live bridge, AESTDTC of a confirmed draft is also the local call date. Symptoms start before the call that reports them, so the match window (§5) looks back to the previous call that reported the symptom below the episode's band. §16 lists the remaining error as a limit.

### 4.4 Structural consequence of the current red-flag rules

The paged-stratum rule (§6.2) interacts with `data/red_flags.json`:

| Cell | Paged? | Reason (rule IDs) |
|---|---|---|
| Fever G2, G3 | **Always.** A highest temperature above 39.0 °C always meets `RF_FEVER` (≥ 38.0 °C). | `CTCAE5_FEVER_G2/G3` vs `RF_FEVER` |
| Diarrhea G3 | **Always** | `CTCAE5_DIARRHEA_G3` vs `RF_DIARRHEA_SEVERE` |
| Dyspnea G3 | **Always** | `CTCAE5_DYSPNEA_G3` vs `RF_BREATHING` |
| Diarrhea G2 | Sometimes: blood in stool (`RF_DIARRHEA_SEVERE`), or dizziness on standing (`RF_DEHYDRATION`) | — |
| Dyspnea G2 | Sometimes: severity rated severe or very severe (`RF_BREATHING`) | — |
| Any cell | Sometimes: another red flag fired on the same call | — |

**O/E is therefore computed on non-paged Diarrhea grade 2 and Dyspnea grade 2 episodes.** Fever and grade 3 episodes appear only in the paged stratum, where the site was told in real time. This is intended, because capture of a paged episode is caused by our own page. It has three consequences:

- The standardization in practice has two live cells.
- Site Signal measures capture of moderate, non-urgent symptoms, not of the most severe ones.
- There are fewer evaluable episodes per site. The planning grid and the simulation therefore apply the real red-flag rules (§11.2, §11.5), so power is not overstated.

The red-flag and grading inputs are hash-frozen in `params.yaml` `frozen_inputs` (§11.3): the red-flag ids, rules and levels, the plan's active red-flag list (`data/plan.json` `red_flag_ids`, which decides which flags can page), the primary-term item logic and the grading rules. A change to them after `sap-v1` is a deviation (§1.4).

---

## 5. Matching rule

Parameters come from `signal_rules.json` `match`.

Patients report a symptom after it starts, and calls happen only on days 1, 3 and 7 after each 21-day dose, so an onset late in a cycle is first reported on the next cycle's day-1 call, up to 14 days later. The window therefore looks back to the previous observation, not symmetrically around the reporting call.

| Element | Rule |
|---|---|
| Candidates | Site AE rows with `origin = site`, `entered_on <= data_cut`, the same `subject_id`, and an `aeterm` that maps to the episode's term through `term_synonyms` (our own list; no MedDRA codes or hierarchy) |
| Observation interval | [*L_e*, *D_e*], where *D_e* is the episode date and *L_e* is the date of the subject's last completed call before *D_e* with a non-null grade for the term below the episode's band (below 2 for a `new` episode, below 3 for a `worsened` one). If there is no such call, or it is more than `gap_days` (21) before *D_e*, *L_e* = *D_e* − `gap_days` (`match.lower_anchor` = `last_negative_call`). |
| Window | A row is a candidate when AESTDTC ∈ [*L_e* − `lower_tolerance_days`, *D_e* + `window_days`], inclusive, with `lower_tolerance_days` = 2 and `window_days` = 7. Sensitivity windows are in §12.6 (SE1, SE2). |
| Grade | Not used. A site row with a different grade still matches. |
| Assignment | **One-to-one, greedy**, per subject and term. Every eligible (episode, row) pair is sorted by its distance to the observation interval (0 when AESTDTC lies in [*L_e*, *D_e*], otherwise the days to the nearer end), then episode date, then `aeseq`. Pairs are taken in that order, skipping any episode or row already used. |
| Scope | Matching runs over all of a subject's episodes for the term, whether paged, pending or evaluable. A site row explained by a paged episode is therefore not reused by a neighbouring episode. |

A worsened episode needs its own site row to match. Sponsors differ in whether a change of grade becomes a new AE record. An onset recorded by the site before *L_e* − `lower_tolerance_days` cannot match by design. §16 lists both as limits.

---

## 6. Evaluability, exclusions and strata

### 6.1 Evaluable or pending

An episode is **evaluable** at the data cut when:

```math
\text{data\_cut} \;\ge\; \max\bigl(\text{episode\_date} + 14\ \text{d},\ \ \text{next scheduled dose visit after episode\_date} + 8\ \text{d}\bigr)
```

The parameters are `evaluability.entry_window_days` = 14 and `next_visit_plus_days` = 8. The 8 days are the visit-to-entry time reported by Tufts CSDD 2017, as quoted in the challenge kit [20]. Every other episode is **pending**. A pending episode is shown greyed, never counts as missed, and enters neither O nor E, even if a match already exists (no early-match bias). For live site-101 episodes, the data cut is the request's local date.

### 6.2 Paged stratum

An episode is **paged** if any call folded into it raised an `urgent` or `emergency` escalation, for any red flag (`signal_rules.json` `paged`). Paged episodes:

- are excluded from O, E and V;
- are matched (§5) and reported per site as `paged_stratum {n, matched}`, descriptive only;
- keep status `paged`, whether evaluable or not.

A page also starts nurse contact with the patient, which may raise the site's capture of the same subject's other, non-paged episodes nearby. The primary rule does not exclude those. Sensitivity SE14 uses a page-proximal rule (an episode is paged if any urgent or emergency page for the same subject falls within `paged.proximity_days` = 7 days of the episode date), and SE15 simulates a capture boost for the latent episodes of a subject that start within 7 days of an urgent or emergency call, at the 5 sites with the highest share of such calls (§12.6).

### 6.3 Incomplete and missed calls

Only calls with `status = completed` contribute to episodes. Calls that were `no_answer`, `failed`, `cancelled` or not completed contribute nothing for any term. Call completion enters only through the coverage guard (§7). Simulated calls are either completed or missed; there are no partial calls.

### 6.4 Episode status (precedence)

1. `paged`, if §6.2 applies.
2. `pending`, if not evaluable (§6.1).
3. `not_evaluated`, if the episode's cell has no leave-one-site-out rate (§8.1), or its site is not computed for reason `error` or `integrated_mode`.
4. `matched` or `unmatched`, from §5.

Statuses 3 and 4 make up *A_s*; only status 4 enters O, E and V. Episodes at a site that is not computed for `low_coverage`, `insufficient_patients`, `insufficient_episodes` or `study_below_min_sites` keep status `matched` or `unmatched`: they are valid data, shown in the drill-down, and an `unmatched` one can be cited in a site query.

---

## 7. Site-level guards (minimum data and coverage)

Parameters come from `signal_rules.json` `minimum_data`. The checks run in this order per site, and the first one that fails sets `not_computed_reason`:

| Order | Check | Reason |
|---|---|---|
| 1 | Any exception while loading or computing the site | `error` |
| 2 | Any `origin = between_visits` AE row at the site, or any draft action by a site role in the analysis window (§2.4) | `integrated_mode` |
| 3 | Coverage = completed calls ÷ scheduled calls (scheduled date ≤ data cut) < `min_call_completion` = 0.60 | `low_coverage` |
| 4 | Patients < `min_patients` = 10 | `insufficient_patients` |
| 5 | Evaluable non-paged episodes (\|*A_s*\|) < `min_evaluable_episodes` = 15, or *V_s* = 0 (§8.1) | `insufficient_episodes` |
| 6 | Study level: fewer than `min_sites` = 10 sites pass checks 1–5. All remaining sites get this reason. | `study_below_min_sites` |

The study-level minimum of 10 sites follows the FDA CDER SMART poster's guidance that its tests need at least 10 sites [6]. A study-level load failure in the backend returns 503 `site_signal_unavailable`, and the UI shows every site grey (REQ-025). The four tier values are `watch`, `look`, `none` and `not_computed`. No value means "clean".

---

## 8. Primary indicator

### 8.1 Expected capture: leave one site out

For site *s* and cell *c* (term × band), with *O_{s'}(c)* matched and *N_{s'}(c)* total episodes in *A_{s'}*:

```math
\hat p_{-s}(c) \;=\; \frac{\sum_{s' \neq s} O_{s'}(c)}{\sum_{s' \neq s} N_{s'}(c)}
```

- The sum runs over every other site except those not computed for `error` or `integrated_mode`. Sites that fail another guard still contribute their episodes, because their data are valid even if too sparse to rank.
- If a cell has no episodes at the other sites, the term's rate pooled over bands is used. If that is empty too, the episode is `not_evaluated`.

```math
O_s = \sum_{e \in A_s} Y_e, \qquad
E_s = \sum_{e \in A_s} \hat p_{-s}(c_e)
```

Episodes cluster within patients, so the variance is cluster-robust at patient level. With *n_s* the number of patients contributing episodes to *A_s*, *A_{s,i}* patient *i*'s episodes, and *p̂_e* = *p̂₋ₛ(c_e)*:

```math
V_s \;=\; \max\Bigl(\tfrac{n_s}{n_s - 1}\sum_{i}\Bigl(\sum_{e \in A_{s,i}} (Y_e - \hat p_e)\Bigr)^{2},\;\; \sum_{e \in A_s} \hat p_e (1 - \hat p_e)\Bigr)
```

If *V_s* = 0, which happens only when every *p̂* is 0 or 1, the site is not computed with reason `insufficient_episodes`.

### 8.2 Score, overdispersion and adjusted score

Between-site variation of honest capture is additive on the ratio scale, so its variance grows with site size. A single multiplicative factor would over-flag large sites and under-flag small ones. The adjustment is therefore additive (random effects), following Spiegelhalter [7, 8]:

```math
z_s = \frac{O_s - E_s}{\sqrt{V_s}}, \qquad
\hat\phi = \frac{1}{K} \sum_{s \in C} \tilde z_s^{\,2}, \qquad
\hat\tau^2 = \max\Bigl(0,\; \frac{K\hat\phi - (K - 1)}{\sum_{s \in C} w_s - \sum_{s \in C} w_s^2 \big/ \sum_{s \in C} w_s}\Bigr), \quad w_s = \frac{E_s^2}{V_s}
```

```math
z^*_s = \frac{O_s - E_s}{\sqrt{V_s + \hat\tau^2 E_s^2}}
```

- *C* is the set of computed sites and *K* = \|*C*\|. *τ̂²* is the between-site variance of *O/E*; *τ̂²* = 0 when *Kφ̂* ≤ *K* − 1.
- *z̃* is *z* winsorized at the 10th and 90th percentiles of {*z_s* : *s* ∈ *C*}, using `numpy.quantile` with `method="linear"` (`signal_rules.json` `overdispersion.winsor`), as in Spiegelhalter [7, 8].
- *τ̂²* is estimated within each study, in the committed run, in every null and power replicate, and in every blind run. The null distribution of *z\** (§9) therefore already includes its estimation.
- Planted sites inflate *τ̂²*. Winsorization limits this, and what remains makes the test more conservative, not less.
- The multiplicative adjustment (*z\** = *z*/√*φ̂* when *φ̂* > 1) is reported as sensitivity SE21 (§12.6).

The `SiteSignalRow` fields are `O`, `E`, `V`, `oe_ratio` = *O/E*, `z_raw` = *z*, `z_adj` = *z\**, and `rank` (ascending *z\** among computed sites). The run block reports `phi` (*φ̂*) and `tau2` (*τ̂²*).

### 8.3 Tiers

The thresholds *c_watch* ≤ *c_look* are read from `monitoring/out/thresholds.json` (§9). The tiers are nested:

| Tier | Condition (computed sites) | On-screen meaning |
|---|---|---|
| `watch` | *z\** ≤ *c_watch* | Family-wise false-flag probability ≤ 10% per study under the pre-registered null |
| `look` | *c_watch* < *z\** ≤ *c_look* | Per-site one-sided 5% under the pre-registered null. The UI states the expected number of false Look flags per study from `thresholds.json` `expected_false_look_flags_per_study` (a calibration mean over null studies, marginal over the number of computed sites *K*), never a typed number, and shows the committed study's *K* next to the tier legend. |
| `none` | *z\** > *c_look* | "No signal at this sample size". Neutral, never green. |
| `not_computed` | §7 | Grey, with the reason |

Power "at the Look tier" counts both `look` and `watch`.

Secondary analysis, reported in `report.md` only and never used for tiers: calibrated empirical *p*-values *p_s* = (1 + #{null pooled *z\** ≤ *z\*_s*}) / (1 + *M*), from the §9.2 Look pool, with Benjamini-Hochberg *q*-values across computed sites [12]. Normal-approximation *p*-values (Φ(*z\**)) are not used: in exploratory simulation done before this SAP (not committed) they proved too optimistic under the null, which is why tiers are calibrated by simulation.

### 8.4 Funnel display

The overview plots each computed site at (*E_s*, *O_s/E_s*). Not-computed sites appear as hollow grey points in a strip below the axis. The lower limits for tier *t* use the same additive variance:

```math
L_t(E) \;=\; 1 + c_t \sqrt{\frac{1 - \bar p}{E} + \hat\tau^2},
\qquad \bar p = \frac{\sum_{s \in C} O_s}{\sum_{s \in C} |A_s|}
```

These lines approximate *V* ≈ *E*(1 − *p̄*) for display. **Tier assignment always uses each site's exact *z\**, never the drawn line.**

---

## 9. Null model (parametric bootstrap) and threshold calibration

### 9.1 Pre-registered null (honest sites only)

The data-generating mechanism is that of §11.2. Every site is honest: no planted capture loss, no planted personalities, and the base design. Each of these sources of variation is drawn independently in every null study:

| Component | Distribution (`params.yaml`) |
|---|---|
| Patient frailty on episode counts | Gamma(shape 2.0, scale 0.5) |
| **Patient capture random effect, (1\|patient)** | Normal(0, 0.5²) on the logit scale |
| Between-site honest capture variation | Normal(0, 0.35²) on the logit scale |
| Site case mix | Log-normal, SD 0.35 on the log scale |
| Call completion | Beta, mean 0.85, κ = 20, per patient |
| Patient-stream mapping error | Beta(2, 38) per patient, same in both languages |
| Paging, evaluability, entry lag, AESTDTC noise | As §11.2 |

The patient random effect is included because episodes cluster within patients. A variance *V_s* that treats episodes as independent would otherwise make the null too narrow. This null is parametric, at assumed parameter values. A null fitted to each study's own data, such as a data-fitted bootstrap, is **not built** (listed in `NOT_BUILT.md`). Misspecification is examined in §12.6.

### 9.2 Calibration procedure (`calibrate.py`, stream 1)

1. Simulate *R* = `r_null` = 2000 null studies at the `sap-v1` design.
2. Run the full analysis on each: episodes, matching, guards, *τ̂²* and *z\**. Run all three indicators and the ablation (§10.3) on the identical study.
3. **Look:** pool the statistic over every computed site in every null study, giving *M* values, and take the per-site one-sided 5% threshold.
4. **Watch:** for each null study *r*, take *m_r* = the minimum statistic over its computed sites (+∞ if none is computed). Take the 10% threshold of {*m_r*}.
5. Apply the discreteness rule (§9.3). Set *c_watch* := min(*c_watch*, *c_look*).
6. Write `monitoring/out/thresholds.json` with:
   - `sap_tag_commit`, `eval_seed`, `r_null`;
   - thresholds for all three indicators and the ablation, with any *c* = −∞ flagged (§9.3);
   - the achieved in-sample rates and their MC SE;
   - the mean number of false Look flags per null study (`expected_false_look_flags_per_study`).

These thresholds are used **unchanged** for the committed study, the sensitivity analyses and every blind run. In-sample achieved rates match the nominal values by construction. The evidence is the out-of-sample check in §12.1.

### 9.3 Discreteness rule

For a statistic where lower means more extreme, null sample values *S*, and nominal rate α:

```math
c \;=\; \max\Bigl\{\, t \in S \;:\; \tfrac{1}{|S|}\textstyle\sum_{x \in S} \mathbf{1}[x \le t] \le \alpha \Bigr\}
```

A site is flagged when its statistic ≤ *c*. For continuous statistics this is the ⌊α·\|*S*\|⌋-th order statistic. For discrete statistics (simaerep classic *prob*), ties never push the achieved rate above α. If no *t* qualifies, *c* = −∞, so the tier is never assigned, and this is logged in `thresholds.json`.

---

## 10. Comparators on identical data

Both comparators and the ablation (§10.3) are computed on the same simulated study object as the discordance indicator (REQ-028) and calibrated by §9.2–9.3 on the same null studies. They use only the site AE log, so the coverage guard does not apply to them. They do apply `min_patients` = 10 and their own minimums. A planted site that an indicator cannot compute counts as **not flagged** for that indicator.

### 10.1 gsm-style AE-rate KRI

Modeled on gsm `kri0001`: AEs per day on study, Poisson normal approximation, overdispersion adjustment [9].

```math
\hat\lambda = \frac{\sum_{s \in C'} x_s}{\sum_{s \in C'} T_s}, \qquad
z_s = \frac{x_s / T_s - \hat\lambda}{\sqrt{\hat\lambda / T_s}}
```

- *x_s* = site-originated AE rows at site *s*, symptomatic or not, with `entered_on <= data_cut`.
- *T_s* = patient-days on study up to the data cut.
- *C'* = sites with *T_s* ≥ `comparators.rate_kri.min_days` = 30 and ≥ 10 patients.
- *λ̂* pools all sites in *C'*, including the site itself, as gsm does (not leave-one-site-out).
- *z\** = *z*/√*φ̂* when *φ̂* > 1: multiplicative overdispersion as in gsm [9], with *φ̂* winsorized as in §8.2 (Spiegelhalter [7, 8]; gsm itself does not winsorize). This keeps the comparator close to gsm.
- Look and Watch come from §9.2.

### 10.2 simaerep classic (legacy)

A Python port, under MIT, of the original simaerep algorithm [10, 11], labeled **"simaerep classic (legacy)"** everywhere. simaerep v1.0.0 changed its defaults to `inframe = TRUE, visit_med75 = FALSE` (NEWS.md) [11]. That inframe default is **not ported** (listed in `NOT_BUILT.md`). Version claims say: a port of the legacy algorithm, fixture-tested against the v1.0.0 repository.

| Step | Definition |
|---|---|
| Input | One row per patient visit, where visit = dose visit index 1, 2, … up to the data cut. `n_ae` = cumulative count of site-originated AE rows with AESTDTC ≤ visit date and `entered_on <= data_cut`. |
| Evaluation point | `visit_med75` per site, as simaerep computes it (`get_visit_med75`, method `med75_adj`, `min_pat_pool = 0.2`): ⌈0.75 × median over the site's patients of their last visit⌉, adjusted to the study's patient pool |
| Site mean | Mean `n_ae` at `visit_med75` over the site's patients who reached it |
| Bootstrap | `prob_low` = (1 + #{resampled mean ≤ site mean}) / (1 + *r*), over *r* resamples of \|site patients\| patients drawn with replacement from the pool (site plus study patients who reached the site's `visit_med75`). The +1 keeps `prob_low` above 0, so tail thresholds are not set by ties at 0; simaerep's own form (#/*r*) is used only in the fixture test. `prob_low` = 1 when the site mean exceeds the study mean (`under_only`). *r* = 1000 everywhere the statistic is calibrated or applied (null calibration, validation, grid, committed study, blind runs). If the §12 runtime budget is exceeded, simaerep is computed on fewer cells (§12 fallback 2), never with a smaller *r*. |
| Poisson test | Two-sample Poisson rate test of site vs study events, with time bases = patients × `visit_med75` (R `poisson.test` semantics) |
| Multiplicity | Benjamini-Hochberg across sites on `prob_low` and the *p*-value. `prob` = −(1 − BH-adjusted `prob_low`). |
| Statistic for tiers | `prob`, lower is more extreme; thresholds from §9.2 |
| Fixture | `monitoring/tests/fixtures/simaerep_pval_fixture.csv`, extracted from the regression data shipped in simaerep v1.0.0 (`R/sysdata.rda`), with the MIT notice. Site *p*-values must match with maximum relative difference < 1e-9. The bootstrap `prob` must match within the documented Monte Carlo tolerance. |

### 10.3 Ablation: AE-to-report ratio (validation only)

Shows whether episode-level matching adds anything beyond using the patient-reported stream as a case-mix denominator. Per site and primary term *t*: *U_s(t)* = site-originated rows mapping to *t* with `entered_on <= data_cut`; *N_s(t)* = evaluable non-paged episodes of *t*. Expected *E^U_s* = Σ_t *N_s(t)* · Σ_{s'≠s} *U_{s'}(t)* / Σ_{s'≠s} *N_{s'}(t)*; *z* = (*U_s* − *E^U_s*)/√*E^U_s*, with multiplicative *φ̂* as §10.1; tiers calibrated by §9.2–9.3; same guards as discordance. No matching. Reported in §12.4 and `report.md` only; it is not a column in the UI.

Cut rule (`docs/09`): if the fixture test is not green by 05:00, simaerep classic is dropped from the UI and from `summary.json` and listed in `NOT_BUILT.md`. The gsm-style KRI stays.

---

## 11. Simulation design

The design follows the ADEMP structure (aims, data-generating mechanisms, estimands, methods, performance measures) of Morris et al. [17].

### 11.1 Aims

1. Calibrate thresholds so the stated false-flag rates hold under an honest null (§9).
2. Estimate power at both tiers against planted capture loss, for discordance and both comparators, across study sizes.
3. Show where the method fails: the diligence-dominated failure case and a misspecified null.
4. Produce one committed illustrative study with drill-down evidence, a funnel, an answer key and an equity panel.

### 11.2 Data-generating mechanism

`monitoring/bvsignal/roster.py` and `simulate.py` follow these steps. Every number is in `params.yaml` with a citation or an `ASSUMPTION` tag.

1. **Roster.**
   - Sites `101`–`120` with fictional names. Patients per site are uniform integers over the range fixed in §11.5.
   - Enrollment day is uniform on [0, 84].
   - Each site draws a Spanish-speaking share from Beta(1.2, 3.0); each patient is Spanish-speaking with that probability.
   - Age is Normal(66, 10). Extra-time pace if age ≥ 75.
   - An optional Synthea-derived roster (`monitoring/cohort/roster.json`, task S10) supplies only a language and age mix, and only for a labeled sensitivity analysis (`make site-signal ARGS="--roster synthea"`). The committed study, calibration, validation and blind runs use the parametric roster frozen at `sap-v1`.
2. **Schedule.**
   - A dose every 21 days from enrollment until the data cut (day 252, a 36-week window).
   - Calls on days 1, 3 and 7 after each dose.
   - Each patient draws a completion probability *π_i* ~ Beta(17, 3) (mean 0.85, κ = 20). Each scheduled call is completed with probability *π_i*.
3. **Latent episodes.**
   - *N_i* ~ Poisson(*μ* · *m_s* · *F_i* · *x_i*), where *m_s* is site case mix, *F_i* ~ Gamma(2, 0.5) is patient frailty, and *x_i* = days on study ÷ 252.
   - Each episode draws a term from (Diarrhea 0.5, Fever 0.2, Dyspnea 0.3) and grade 3 with probability 0.25, otherwise grade 2.
   - The start day is uniform over the patient's days on study.
   - Duration is *K* ~ Geometric(1/2) consecutive scheduled calls (mean 2), starting at the first scheduled call on or after the start day.
   - Overlapping same-term episodes in one patient merge. The higher grade applies from its own start, which the episode builder sees as a `worsened` episode.
   - Latent episodes after the patient's end of AE collection (data cut in this design) are not generated.
4. **Answers.**
   - On each completed call, each primary term's answer set is drawn by enumerating the item domain, grading every candidate with `rules.grade()`, and sampling uniformly among candidates whose grade equals the latent grade on that call. Calls without an episode answer at the item's "none" level.
   - Numeric domains: stools per day 0–15 in steps of 1; highest temperature 36.5–40.8 °C in steps of 0.1. Baseline stools per day is 1 or 2.
   - Items that do not set the grade but can trigger a red flag (stool blood, dizziness on standing, dyspnea severity) are drawn from `answer_generation.secondary` (ASSUMPTION, §11.3). Secondary items are drawn independently on every completed call of the episode; on calls without an episode they are at their none level.
   - Non-primary items are answered at "none".
   - Candidate sets are enumerated once per run and cached.
5. **Mapping error.**
   - Each patient draws *ε_i* ~ Beta(2, 38) (mean 0.05).
   - Each recorded primary-term answer is independently replaced with probability *ε_i* by an adjacent value: for ordinal items the next option up or down, each with probability 1/2, or the only adjacent option at either end of the scale; the other value for yes/no; ±1 stool per day (+1 at 0) and ±0.5 °C, each sign with probability 1/2.
   - When an error changes a gate item, follow-ups follow `data/symptom_items.json` `followups`: a follow-up the new value no longer opens is dropped, and one it newly opens is answered `unknown` (so the term is null on that call).
   - This happens before grading, so errors can create, hide or re-band episodes. Rates are the same in both languages and paces (sensitivity in §12.6).
6. **Red flags and paging.** `rules.red_flags()` runs on the recorded answers with `active_ids` = `data/plan.json` `red_flag_ids` (as `plan_power.py` does, and as the live path passes the plan's red flags). An `urgent` or `emergency` level on a call puts every episode containing that call in the paged stratum.
7. **Site capture.** Each latent episode, not the recorded one, is entered by the site with probability:

   ```math
   p = \bigl(1 - f_s\bigr)\cdot \operatorname{expit}\!\Bigl(\operatorname{logit} p_0(t, b) + u_s + v_i + \delta_{s,i}\Bigr)
   ```

   - *p₀* is the base capture by term and band (§11.3).
   - *u_s* ~ N(0, 0.35²) is between-site honest variation.
   - *v_i* ~ N(0, 0.5²) is the patient effect.
   - *δ* is a planted offset (§11.4).
   - *f_s* is planted capture loss (0 for honest sites).

   A captured episode gives one site row (`origin = site`, `symptomatic = true`):
   - `aeterm` is a random synonym of the term;
   - `aetoxgr` is the latent grade;
   - AESTDTC = start day + round(N(0, 2²)) days;
   - `entered_on` = (first dose visit on or after AESTDTC) + ⌈lag⌉, lag ~ Gamma(shape 2, mean 8 days) (entry lag anchored to [20]). The first dose visit is the enrollment day when AESTDTC falls before it.
   - `aeseq` numbers each subject's site rows (symptomatic and other, step 8) 1, 2, … by AESTDTC, then `entered_on`, then symptomatic before other, then latent start day, then generation order. It is the §5 tie-break.

   Paged episodes get no capture boost (ASSUMPTION; they are descriptive only). This holds for the primary analysis and every scenario except SE15 (§12.6).
8. **Other AEs.** For each patient, Poisson(1.5 · *m_s* · *F_i* · *x_i*) non-symptomatic site rows, with AESTDTC uniform over time on study. Each other-AE row has `origin = site`, `symptomatic = false` and `entered_on` by the step 7 rule. At planted sites each is dropped with probability *f_s*. The comparators use these rows.
9. **Evidence.** Each simulated episode takes a quote from `monitoring/quote_bank.json` by term, band and language, with `source = synthetic`. The bank's phrasings and its English translations of Spanish quotes are AI-assisted, so `translation_is_ai` is true and the UI shows an `AiLabel`.
10. **Output.** A `Study` object, the answer key, and the episode, site-AE and site JSON, with `data_origin = SIMULATED` on every object.

Calendar dates: study day 0 = 2026-01-05 (`design.study_start_date`), so the data cut (day 252) is 2026-09-14.

### 11.3 Parameter table (mirrored by `monitoring/params.yaml`)

`params.yaml` must agree with this table at the tag; S1 includes that check. After the tag, the code reads `params.yaml`, and any disagreement found later is logged in §17.

| `params.yaml` key | Value | Source |
|---|---|---|
| `design.n_sites` | 20 (`site_ids` `101`–`120`; `live_site` `101`, always honest) | ASSUMPTION; ≥ 10 sites per [6] |
| `design.patients_per_site` | Uniform integer over the range chosen in §11.5, from 15–30, 20–40, 30–60, 40–80 | Design (planning gate) |
| `design.window_weeks`, `data_cut_day` | 36, 252 | ASSUMPTION |
| `design.study_start_date` | 2026-01-05 | Fictional calendar anchor |
| `design.enrollment_spread_days` | 84 | ASSUMPTION |
| `design.cycle_days` | 21 | Every-3-weeks dosing of the example study (`docs/05` §2) |
| `design.call_days_after_dose` | 1, 3, 7 | `data/plan.json` |
| `roster.spanish_share_by_site` | Beta(1.2, 3.0) (mean ≈ 0.29) | ASSUMPTION |
| `roster.extra_time` | Age ≥ 75; age Normal(66, 10) | ASSUMPTION |
| `episodes.mu_g2plus_per_patient_window` | 1.5 (grid also 0.5) | ASSUMPTION representing a combination regimen. Clinician-reported incidence under PD-1/PD-L1 monotherapy is lower [21] (not re-checked; UNVERIFIED). |
| `episodes.term_mix` | Diarrhea 0.5, Fever 0.2, Dyspnea 0.3 | ASSUMPTION |
| `episodes.g3_share` | 0.25 | ASSUMPTION |
| `episodes.mean_duration_calls` | 2 (geometric) | ASSUMPTION |
| `episodes.patient_frailty` | Gamma(shape 2.0, scale 0.5) | ASSUMPTION |
| `episodes.casemix_sd_log` | 0.35 (failure case 0.2) | ASSUMPTION |
| `answer_generation.method` | Enumerate the item domain and grade with `rules.py` | Rule 2: no thresholds re-coded |
| `answer_generation.numeric_domains` | `DIARRHEA_STOOLS_PER_DAY` [0, 15]; `TEMP_HIGHEST` [36.5, 40.8, 0.1] | Covers every band |
| `answer_generation.baseline_stools` | {1, 2}, equal probability | ASSUMPTION |
| `answer_generation.secondary` | Diarrhea episode: `STOOL_BLOOD` yes 0.05; `DIZZINESS_SEV` mild or worse with `DIZZY_ON_STANDING` yes 0.10. Dyspnea G2: `SOB_SEV` mild 0.30, moderate 0.50, severe 0.15, very_severe 0.05. Dyspnea G3: moderate 0.30, severe 0.50, very_severe 0.20. Secondary items are drawn independently on every completed call of the episode; on calls without an episode they are at their none level. | ASSUMPTION |
| `site_capture.base_p` | Diarrhea G2 0.56, G3 0.70; Fever G2 0.80, G3 0.90; Dyspnea G2 0.60, G3 0.75 | Anchored to Di Maio 2015: clinicians missed 40.7–74.4% of patient-reported symptomatic toxicities at any grade and 13–50% at the highest severity [1] (ranges from a secondary summary; per-term values ASSUMPTION). Fever G3 sits slightly above that range because temperature is measured. |
| `site_capture.between_site_sd_logit` | 0.35 (failure case 0.6) | ASSUMPTION |
| `site_capture.patient_re_sd_logit` | 0.5 | ASSUMPTION |
| `site_capture.aestdtc_noise_days_sd` | 2 | ASSUMPTION |
| `site_capture.entry_lag_days` | Gamma, mean 8, shape 2 | Tufts CSDD 2017, 8 days from visit to entry [20] |
| `site_capture.other_aes_per_patient_window` | 1.5 | ASSUMPTION |
| `patient_stream.call_completion` | Beta, mean 0.85, κ 20 | ASSUMPTION |
| `patient_stream.mapping_error_per_answer` | Beta(2, 38) per patient, symmetric across languages | ASSUMPTION. The text-mode evaluation (`eval/results/latest.json`, n = 20 simulated patients) is too small to estimate error by language and measured no speech error. |
| `patient_stream.mapping_error_step` | Ordinal ±1 option, up or down with probability 1/2 (the only neighbour at a scale end); yes/no flip; stools ±1 (+1 at 0); temperature ±0.5 °C; signs with probability 1/2 | ASSUMPTION |
| `calibration` | `r_null` 2000, `r_validation` 2000, `r_quick` 200 | Precision (§12.8) |
| `grid` | `n_sites` [12, 20]; `patients_per_site` [10, 20, 30, 40, 60, 80]; `f` [0.25, 0.50, 0.75, 0.85, 0.90]; `mu` [0.5, 1.5]; `reps` 300; `reps_quick` 40 | §12.2 |
| `failure_case` | `between_site_sd_logit` 0.6, `casemix_sd_log` 0.2; `r_null` 1000 null studies and `reps` 300 planted studies per grid *f* for (a); `r_null_b` 1000 null studies for (b) | §12.5; precision (§12.8) |
| `equity_validation` | `r` 500 null studies; `b` 1000 bootstrap resamples per validation replicate | §12.3; precision (§12.8) |
| `sensitivity` | §12.6 | — |
| `comparators` | `rate_kri` {patient-days, `min_days` 30}; `simaerep_classic` {r 1000, `visit_med75` true, BH true}; `ae_report_ratio` (ablation, §10.3) | [9, 10, 11] |
| `blind_run` | `planted_count` uniform integer 0–3; `f` = `planted.gross.f`; 10 `precomputed_labels` (short words such as `aurora`; the example label `demo-42` used in acceptance checks is deliberately not one of them) | §13 |
| `signal_rules_sha256` | sha256 of `data/signal_rules.json` at the tag | Freeze check |
| `frozen_inputs` | sha256 of: the canonical JSON (`sort_keys`, no spaces) of the `id`, `rule` and `level` fields of every entry in `data/red_flags.json`, in file order (sources, wording and citations excluded, so the D8 citation fix is allowed) (`red_flags_id_rule_level_sha256`); the canonical JSON of `data/plan.json` `red_flag_ids`, the active red flags that decide paging (§11.2, red flags and paging) (`plan_red_flag_ids_sha256`); the canonical JSON of the `kind`, `term`, `scale`, `unit` and `followups` fields of every item in `data/symptom_items.json` whose `term` is a primary term, with the `options`, `numeric` and `units` fields of the scales those items use (wording excluded; these define the answer domains, the follow-up structure and the mapping-error adjacency) (`symptom_items_logic_sha256`); the canonical JSON of the `rules` array of `data/ctcae_rules.json` (`ctcae_rules_sha256`); `backend/app/services/rules.py` (`rules_py_sha256`); `backend/app/content.py` (`content_py_sha256`; the loader through which rules.py selects items, grading rules and red flags); `backend/app/services/episodes.py` (`episodes_py_sha256`; if B16 has not landed at the tag, its hash is added by a §17 clarification when it lands, and §4–§6 is its specification) | `calibrate.py`, `run.py`, `validate.py` and `blind.py` refuse to run on a mismatch unless a §17 row cites the new hash |
| `seeds` | `dev` 20261011; `eval` derived (§1.3); beacon in `monitoring/seed_beacon.json` | §1.3 |
| Provenance | Every output records `numpy` and `scipy` versions; `monitoring/uv.lock` is committed in the tag commit | numpy does not promise identical random streams across versions |

### 11.4 Planted truth (committed study)

Roles go to distinct sites, drawn at random from the stream-0 generator among the non-101 sites. Site 101 is always honest. The remaining sites are honest.

| Label (`answer_key.json`) | Count | Planted mechanism | Honest by the key? | Confusion-matrix role |
|---|---|---|---|---|
| `gross_under` | 2 | *f* = gross *f* (§11.5) | No | Positive |
| `under_50` (**masked**) | 1 | *f* = 0.50 with case mix *m_s* := 2.0 (sicker patients). Its raw AE rate stays near the study average, which is the blind spot of a rate KRI. | No | Positive |
| `under_25` | 1 | *f* = 0.25 | No | Positive |
| `language_gap` | 1 | Spanish-speaking share fixed at 0.5; *δ* = ln 0.5 (capture odds ratio 0.5) for Spanish-speaking patients' episodes | No | Positive |
| `decoy_healthy_casemix` | 1 | Case mix *m_s* := 0.5; honest capture | Yes | Negative (the rate-KRI trap) |
| `honest_low_diligence` | 1 | *u_s* := −1.5 × 0.35 (the 7th percentile of honest sites) | **Yes.** Shows that discordance is not misconduct. | Negative |
| `low_coverage` | 1 | Call completion mean 0.50 | Yes | Must be `not_computed: low_coverage` for discordance |
| `small_site` | 1 | 6 patients | Yes | Must be `not_computed: insufficient_patients` |
| `honest` | Rest | — | Yes | Negative |

The 25% and 50% sites are the expected "mostly missed" cases at the Watch tier. They are planted so the limits show on screen. `answer_key.json` is committed for transparency, and the UI shows it only after "Reveal answer key".

### 11.5 Pre-tag planning: design feasibility gate and gross capture loss

`monitoring/planning/plan_power.py`, run with `make planning-grid` and the dev seed, uses a **simplified model**:

- Roster, schedule, completion, episodes, capture, AESTDTC noise, evaluability and the §5 match rule are as in §11.2 and §5.
- Paging is decided per cell from paged shares computed once by running `rules.red_flags()` over the enumerated candidate answers with the §11.3 secondary-item probabilities. Fever and grade 3 are always paged (§4.4).
- There is no mapping error and no comparator. Leaving out mapping error makes planning power somewhat optimistic; the final power is reported next to the planning value (§12.2).
- S2 may reuse `plan_power.py`'s roster and episode code instead of writing it twice.

Its output is `planning_grid.json`, labeled "planning only, not a result". It is never quoted as a result.

Two pre-registered rules run in this order.

**Rule P1, design feasibility.** Paging removes Fever and grade 3 episodes (§4.4), so evaluable episodes per site may be few. For each candidate range of patients per site, in order 15–30, 20–40, 30–60, 40–80, simulate 200 studies with the §11.4 composition (the `low_coverage` and `small_site` sites included; planted capture losses can be ignored for computability) at *μ* = 1.5. Choose the **first** range where both hold:

- the mean number of computed sites is ≥ 15 of the 18 sites that are not designed to be grey;
- the share of studies below the 10-site minimum (`study_below_min_sites`) is ≤ 0.02.

If none passes, choose 40–80 and record the shortfall below and in `planning_grid.json`. *μ* and the minimum-data rules are **not** levers: *μ* is a disease assumption, and the minimum-data values are product rules in `data/signal_rules.json`.

**Rule P2, gross capture loss.** At the chosen design:

1. calibrate planning Watch thresholds once from 1000 null studies;
2. for each *f* in {0.75, 0.80, 0.85, 0.90}, simulate 500 studies with one planted site at *f*, using common random numbers across *f* (the same honest-site draws; only the planted *f* changes);
3. estimate Watch-tier power and its one-sided 80% lower bound, *p̂* − 0.842 · √(*p̂*(1 − *p̂*)/500).

Choose the **smallest** *f* whose lower bound is ≥ 0.80. If none qualifies, choose 0.90 and record the shortfall.

`planning_grid.json` also records the mean evaluable non-paged episodes per site, the paged share of episodes and the share of captured episodes that fall outside the §5 window at the chosen design.

**Fallback (time box).** If the planning grid has not finished by 02:30 ET, the values are patients per site 30–60 and gross *f* = 0.90, the gate outcome reads "planning grid not run", and the tag proceeds.

| Value filled at tag time | Value | Gate outcome |
|---|---|---|
| `design.patients_per_site` | 40–80 | shortfall: no range passed rule P1, so the rule's fallback 40–80 applies. At 40–80 the share of studies below the 10-site minimum met its limit, but the mean number of computed sites stayed below 15 of 18 (`planning_grid.json` `.p1`, dev seed, planning only, not a result). |
| `planted.gross.f` | 0.90 | shortfall: no *f* in {0.75, 0.80, 0.85, 0.90} reached a one-sided 80% lower bound of 0.80 for Watch power, so the rule's fallback 0.90 applies. Watch power is capped by how often the planted site is computable at all (`planning_grid.json` `.p2`, dev seed, planning only, not a result). |

The same design and gross *f* are used for the committed study and the blind runs. If the committed study turns out below the 10-site minimum anyway, that result is reported as it is. It is never re-seeded.

---

## 12. Validation metrics (operating characteristics)

`monitoring/bvsignal/validate.py` writes `validation/site_signal/{summary.json, null_rate.json, power_grid.json, failure_case.json, sensitivity.json}`. The full run goes in the background (≤ 45 min). Two fallbacks apply, in order, if the runtime budget is exceeded, and each is logged in §17:

1. Grid and failure-case reps (`grid.reps`, `failure_case.reps`) drop, to no fewer than 200. The MC SE is reported either way.
2. simaerep classic is computed only for the `sap-v1` design row and the full mix.

CI runs `--quick --check` on the same replicate keys with fewer replicates. Quick replicates are an exact subset of the full run (§1.3), so `validate.py` writes the sha256 of the per-replicate results for the first `r_quick` replicates of each stream into `summary.json` (`quick_hashes`), and the check requires exact equality. Any difference means nondeterminism or a code change and fails CI. Agreement of the quick rates with the committed rates is reported as a secondary line, not a gate.

### 12.1 Null false-flag rates (stream 2, *R* = `r_validation` = 2000 fresh null studies, sap-v1 thresholds)

| Metric | Definition |
|---|---|
| Look per-site rate *α̂* | Σ*F_r* / Σ*K_r*, where *F_r* is the number of honest computed sites at Look or Watch in study *r* and *K_r* is the number of computed sites. Cluster-aware MC SE (§12.8). |
| Look per-site rate by site size | *α̂* within tertiles of *E_s* (pooled over studies), each with MC SE |
| Expected false Look flags per study | Mean of *F_r*, with SE = sd/√*R*; also by *K* bin (≤ 12, 13–16, ≥ 17 computed sites) |
| Watch family-wise rate | Share of null studies with ≥ 1 Watch flag, with MC SE and a Clopper-Pearson 95% CI [13]; also by *K* bin |
| Computability | Mean computed sites per study; share of studies below 10 computed sites; distribution of `not_computed_reason` |

All three indicators and the ablation are reported, at both tiers.

**Acceptance (REQ-023).** With SE_cal the MC SE of the threshold's achieved in-sample rate (`thresholds.json`) and SE_val the MC SE above, both one-sided, and every quantity unrounded (§15 rule 6):

- Look per-site rate ≤ 0.05 + 2·√(SE_cal² + SE_val²);
- Watch family-wise rate ≤ 0.10 + 2·√(SE_cal² + SE_val²).

A rate below nominal is reported as "conservative", not as a failure. **Size calibration:** every *E_s* tertile's unrounded Look rate is within 0.05 ± 0.02; a failure is reported in `report.md` and `WHAT_IT_GETS_WRONG.md`, never hidden.

Under a correctly specified null the first two hold by construction. The informative tests are the size check, §12.5 and §12.6.

### 12.2 Power grid (stream 3)

For each design (`n_sites` × `patients_per_site` (exact) × *μ*):

1. 1000 null studies at that design calibrate design-specific thresholds for each indicator by §9.2–9.3 (`role` 0 keys). Thresholds depend on design, not on *f*, and are reused across every *f*.
2. For each *f*, `reps` studies with **one** planted site at *f* among honest sites (`role` 1 keys), with common random numbers across *f*.
3. **Power** = P(planted site at tier ≥ Look) and P(planted site at Watch), with MC SE.
4. Also reported: P(planted site computed), and each design's achieved null Look and Watch rates on its own calibration sample. A not-computed planted site is a miss.

A separate row reports power at the `sap-v1` design using the committed `thresholds.json`. The `sap-v1` design row uses `grid.reps` planted studies for each grid *f* (stream 3, cell 25, `role` 1; the grid *f* values include the gross *f*), with common random numbers across *f*. Its gross-*f* row is shown next to the planning value from `planning_grid.json`, labeled "planning (simplified) vs final". Rows for *f* = 0.25 and 0.50 are always reported (never cut).

### 12.3 Full planted mix (stream 3, *R* = `r_validation`)

Studies at the `sap-v1` design with the complete §11.4 mix, with roles re-assigned in each replicate. Reported per indicator and tier:

- detection rate per label (gross, under_50 masked, under_25, language_gap);
- false-flag rate for `decoy_healthy_casemix` and `honest_low_diligence`;
- false-flag rate for plain honest sites;
- how often `low_coverage` and `small_site` are correctly not computed;
- per tier and indicator: mean number of flags per study, mean number of true-positive flags, and the empirical false discovery rate E[false flags / max(flags, 1)], each with MC SE;
- equity (§14), each with MC SE: (a) language-interval coverage = the share of the first `equity_validation.r` null studies of §12.1 (stream 2, cell 0, `role` 0, *i* < *r*), where no language gap is planted, whose primary 95% interval for the language *OR_MH* contains 1; studies with no included site are reported separately as not computed and are left out of the share; (b) the share of those null studies, and of the §12.3 full-mix studies, whose pace interval excludes 1, again among the studies where it is computed. Inside a validation replicate the §14 patient-cluster bootstrap uses *B* = `equity_validation.b` resamples drawn from `SeedSequence(eval_seed, spawn_key=(stream, cell_index, 2, i))`, the same *B* under `--quick`, so quick replicates stay an exact subset (§1.3).

This answers how the method behaves when several abnormal sites inflate *τ̂²*.

### 12.4 Comparator head-to-head

The **primary comparator assessment is the power grid** (§12.2): one planted site, no traps, honest case mix. For every grid cell, the paired difference in power (discordance minus comparator) is computed on the same replicates, with paired MC SE = sd(*d_r*)/√*R*. Achieved null rates of every comparator are reported per cell alongside, so each is assessed at its own achieved false-flag rate; cells where a comparator's threshold is −∞ (§9.3) are flagged.

Full-mix comparator rows (§12.3) are labeled "includes two scenarios constructed to defeat a rate-based KRI" (the masked `under_50` site and the `decoy_healthy_casemix` site). The ablation (§10.3) is reported in both, to separate the value of episode-level matching from the value of having a patient-reported denominator.

### 12.5 Failure case (stream 4)

The failure case is diligence-dominated heterogeneity: honest between-site capture SD 0.6 and case-mix SD 0.2. Two analyses:

- **(a)** Thresholds re-calibrated under the failure-case null; power of discordance vs rate KRI at the `sap-v1` design for every grid *f*. This shows whether the advantage disappears even with a correct null. Thresholds are re-calibrated by §9.2–9.3 from `failure_case.r_null` = 1000 failure-case null studies (stream 4, cell 27, `role` 0); power uses `failure_case.reps` = 300 studies per grid *f* with one planted site and common random numbers across *f* (cell 27, `role` 1).
- **(b)** `sap-v1` thresholds kept; achieved null false-flag rates on `failure_case.r_null_b` = 1000 failure-case null studies (stream 4, cell 28, `role` 0). This shows the cost of a wrong null.

Both are shown in the UI ("How well it works") and in `WHAT_IT_GETS_WRONG.md`.

### 12.6 Sensitivity analyses (stream 4)

Each scenario reports four things:

- (i) the committed study's tiers re-run under the change;
- (ii) achieved null Look and Watch rates at the `sap-v1` thresholds (300 null studies);
- (iii) full-mix detection by label at the `sap-v1` thresholds (300 studies);
- (iv) for match-window scenarios only, the count of matched episodes that change status.

| ID | Change |
|---|---|
| SE1, SE2 | Match window: upper bound 3 days with lower tolerance 0; upper bound 14 days with lower tolerance 7 |
| SE3–SE6 | Mapping error ×2 for English only; ×4 for English only; ×2 for Spanish only; ×4 for Spanish only (both languages tested the same way) |
| SE7, SE8 | Call completion mean 0.60; 0.95 (κ = 20 unchanged; the `low_coverage` site keeps mean 0.50) |
| SE9–SE11 | Misspecified null: data generated with between-site SD 0.2, 0.5 or 0.6 while the thresholds stay at `sap-v1` (the `honest_low_diligence` offset is −1.5 × the scenario SD) |
| SE12, SE13 | Misspecified null: patient random-effect SD 0.0 or 1.0 |
| SE14 | Page-proximal paged stratum: an episode is paged if any urgent or emergency page for the same subject falls within `paged.proximity_days` = 7 days of its date (§6.2) |
| SE15 | Capture boost: in each simulated study, rank sites by the share of their completed calls at an urgent or emergency level (§11.2 step 6; a site with no completed calls has share 0; ties: lower site id); at the 5 highest, every latent episode whose start day lies within 7 days (inclusive, either side) of the date of an urgent or emergency call of the same subject gets +1.0 on the capture logit of §11.2 step 7, whether or not its episode is paged; achieved null rates at the `sap-v1` thresholds |
| SE16 | Reporting propensity correlated across streams (Gaussian copula, marginals unchanged): per patient draw (*z_v*, *z_π*, *z_ε*) ~ N(0, Σ) with unit variances, corr(*z_v*, *z_π*) = corr(*z_v*, *z_ε*) = 0.5 and corr(*z_π*, *z_ε*) = 0.25; *v_i* = 0.5·*z_v*; *π_i* = F⁻¹ of the patient's completion Beta (§11.2 step 2; Beta(10, 10) at the `low_coverage` site) at Φ(*z_π*); *ε_i* = F⁻¹ of Beta(2, 38) at 1 − Φ(*z_ε*). The correlations are on the normal scale. |
| SE17 | One site, drawn uniformly from the replicate's generator among the non-101 sites labeled `honest` (in a null study, all non-101 sites), has entry lag Gamma(shape 2, mean 25 days) for its symptomatic and other-AE rows. |
| SE18 | 3 sites drawn uniformly without replacement from the replicate's generator among the non-101 sites, whatever their label; at each, one *ε_s* ~ Beta(2, 18) replaces *ε_i* for every patient of the site. |
| SE19 | Case-mix SD 0.6 |
| SE20 | Evaluability with next visit + 19 days (95th percentile of the entry-lag Gamma) |
| SE21 | Multiplicative overdispersion (*z*/√*φ̂*) instead of additive *τ̂²* (§8.2) |

### 12.7 Committed evaluation study (stream 0): illustration only

`make site-signal` writes `monitoring/out/*.json` and `validation/site_signal/report.md`, deterministically, in < 60 s. The confusion matrix for each indicator and tier uses the positives and negatives in §11.4. A positive that is not computed counts as a false negative, and the two must-be-grey sites are reported separately. With 5 positives these counts carry little information. They are labeled as an illustration and never as evidence of performance, because §12.1–12.6 are the evidence.

### 12.8 Monte Carlo precision and intervals

```math
\mathrm{SE}_{MC}(\hat p) = \sqrt{\hat p (1 - \hat p) / R}
\qquad\qquad
\mathrm{SE}_{MC}(\hat\alpha) = \frac{1}{\bar K}\sqrt{\frac{\sum_r (F_r - \hat\alpha K_r)^2}{R(R-1)}}
```

The second formula is the per-site rate with sites clustered within studies.

Maximum MC SE for any proportion, from √(0.25/*R*):

| *R* | Maximum MC SE |
|---|---|
| 2000 | 0.011 |
| 300 | 0.029 |
| 200 | 0.035 |
| 40 | 0.079 |

Every simulated rate is shown with its MC SE. Clopper-Pearson exact 95% intervals [13] go on every binomial proportion from a fixed sample: the Watch family-wise rate, evaluation-study counts, and `eval/results/latest.json` proportions on the report card.

```math
\text{lo} = B^{-1}\!\bigl(\tfrac{\alpha}{2};\, x,\, n - x + 1\bigr), \qquad
\text{hi} = B^{-1}\!\bigl(1 - \tfrac{\alpha}{2};\, x + 1,\, n - x\bigr)
```

Here lo = 0 when *x* = 0 and hi = 1 when *x* = *n*. For example, 8 of 8 gives [0.631, 1].

Zero-failure *N*, the number of consecutive red-flag cases with no miss needed to show recall ≥ *p* with one-sided 95% confidence [14]:

```math
n_{\min}(p) = \left\lceil \frac{\ln 0.05}{\ln p} \right\rceil
```

This gives 29 for *p* = 0.90, 59 for 0.95 and 299 for 0.99.

### 12.9 `summary.json` content

`summary.json` is the single source of every Site Signal number used anywhere. It stores unrounded values; rounding happens only where a number is displayed (§15 rule 6). It holds:

- `sap_tag_commit`, `eval_seed`, `beacon_round`, `code_commit`, `generated_at`, `numpy_version`, `scipy_version`;
- `design` (the chosen design, gross *f*, planning gate outcome);
- `null` (`look_per_site`, `look_per_study`, `watch_fwer`, each with `rate`, `mc_se` and `ci95` where applicable; `look_per_site_by_e_tertile`; `by_k_bin`; `r`; `computability`);
- `power` (rows: `indicator`, `tier`, `n_sites`, `patients_per_site`, `mu`, `f`, `power`, `mc_se`, `p_computed`, `null_rate_achieved`; the design row adds `planning_power`);
- `full_mix` (detection by label, false flags, FDR, and `equity`: the §12.3 language-interval coverage on null studies and pace-interval exclusion rates on null and full-mix studies, each with MC SE, the number of studies used and not computed, and *B*), `head_to_head` (grid and full mix, with the ablation), `failure_case`, `sensitivity`;
- `eval_study` (`confusion`, `caught`, `missed`, `not_computed`);
- `simaerep_fixture` (`rows`, `max_rel_diff`);
- `quick_hashes` (§12 CI check).

`docs/03` §5.3 serves this file; its schema is this list.

---

## 13. Blind run protocol (DEMO_MODE only)

The blind run lets any user test the method on a study nobody prepared in advance. It replaces "plant and recompute". The endpoints are `POST /api/site-signal/blind-run`, `GET …/{run_id}` and `POST …/{run_id}/reveal` (`docs/03` §5).

1. **Seed.** The user types any label of 1–64 characters, stored verbatim. `seed_int` = `int(sha256(("blind:" + label).encode()).hexdigest()[:8], 16)`.
2. **Hidden truth.** From `SeedSequence(seed_int)`, draw a planted count *K* uniform on {0, 1, 2, 3} and assign *K* distinct non-101 sites capture loss *f* = gross *f*. No other personalities are planted, so the reveal is a clean count. Everything else follows the `sap-v1` design.
3. **Analysis.** Run the full pipeline and all three indicators with **fixed** `sap-v1` thresholds from `thresholds.json`. Its sha256 is stored as `SignalRun.thresholds_sha256`. Nothing is recalibrated. *τ̂²* is estimated within the study, exactly as in calibration (§8.2).
4. **Response.** Ranked rows only. `blind.py` also outputs the answer key and the per-indicator confusion; the backend stores them and never serializes them before reveal (REQ-029). The target time is < 10 s. Creation writes `signal.blind_run.created`.
5. **Reveal.** An audited action (`signal.blind_run.revealed`, idempotent) returns the answer key and, for each indicator and tier, caught, missed and false flags. The UI states, from `thresholds.json` and `summary.json`:
   - with 0 planted, any Watch flag is a false flag, expected in at most 10% of studies under the pre-registered null;
   - the expected number of chance Look flags per study (`expected_false_look_flags_per_study`);
   - a missed gross site is a reported miss, not an error.
6. **Determinism.** The same label gives identical output at the same code commit. The 10 precomputed seeds in `monitoring/out/blind_precomputed/` must equal the subprocess output for the same label (`test_blind.py`). If the subprocess fails or exceeds `BLIND_RUN_TIMEOUT_S`, the API returns 503 with the precomputed labels, and the UI says so.
7. **Status.** One blind run is an illustration. Its outcome is never pooled into the operating characteristics or quoted as a result.

---

## 14. Equity analysis (`monitoring/bvsignal/equity.py`, task S9)

Question: **within the same site**, are Spanish-speaking patients' episodes (or extra-time patients' episodes) less often found in the site's AE log than other patients' episodes?

| Element | Definition |
|---|---|
| Data | Evaluable non-paged episodes (*A_s*), *Y_e* matched or not, by patient language (`es` vs `en`) and pace (`extra_time` vs `standard`) |
| Sites used | Sites with ≥ 5 evaluable episodes in **each** group, computed or not. `n_sites_used` is reported. With none, the block reads "not computed: insufficient data". |
| Pooled estimate | Mantel-Haenszel odds ratio across sites [15]. An odds ratio below 1 means lower capture for Spanish-speaking (or extra-time) patients within the same site. |
| Interval (primary) | Patient-cluster bootstrap: resample patients with replacement within each included site, *B* = 2000 in the committed study (stream 0, `role` 2 keys; inside a validation replicate, *B* and keys follow §12.3), percentile 95% CI of ln *OR_MH*. Language and pace are patient-level and episodes cluster within patients, so episode-level intervals are too narrow. |
| Interval (secondary) | Robins-Breslow-Greenland variance [16] |
| Heterogeneity | Breslow-Day test [27] and the per-site odds ratios on one plot. A gap planted at one site is diluted in a pooled common OR. |
| Per-site estimate | Odds ratio with the same within-site patient bootstrap interval, for sites meeting the inclusion rule; point estimate only when the site has < 10 evaluable episodes in either group. Zero cells: 0.5 added to every cell [23]. |
| Sensitivity | Strata = site × term instead of site, because term mix may differ by language |

With *a_k*, *b_k* = Spanish matched/unmatched and *c_k*, *d_k* = English matched/unmatched in stratum *k*, *n_k* = *a_k* + *b_k* + *c_k* + *d_k*, *R_k* = *a_k d_k / n_k*, *S_k* = *b_k c_k / n_k*, *P_k* = (*a_k* + *d_k*)/*n_k*, *Q_k* = (*b_k* + *c_k*)/*n_k*, *R* = Σ*R_k* and *S* = Σ*S_k*:

```math
\widehat{OR}_{MH} = \frac{R}{S}, \qquad
\widehat{\mathrm{Var}}\bigl(\ln \widehat{OR}_{MH}\bigr) =
\frac{\sum_k P_k R_k}{2R^2} + \frac{\sum_k (P_k S_k + Q_k R_k)}{2RS} + \frac{\sum_k Q_k S_k}{2S^2}
```

Pace uses the same formulas with extra-time and standard. In the simulation no pace effect is planted, so the pace odds ratio is a built-in negative control; §12.3 reports how often its interval excludes 1. The planted `language_gap` site is labeled "planted" only after reveal. Power is low, and the UI says so.

**Single-language counterfactual.** This asks what would happen with a single-language (English-only) collection tool instead of English and Spanish voice. Spanish-speaking patients get no calls, scheduled or completed. Guards (§7), episodes, *E*, *z\** and tiers are recomputed with the `sap-v1` thresholds, as an illustration. Reported per site: `tier_now`, `tier_if_english_only`, the reason (typically `insufficient_episodes`), and the share of the site's patients with no reference stream. The counterfactual shows which sites lose the indicator. It says nothing about the agent's accuracy by language, which is the report card's job (`docs/07`). A patient-stream error that differs by language would bias these odds ratios; §12.6 SE3–SE6 bound that.

---

## 15. Reporting rules

1. **No invented numbers.** Every Site Signal number in the UI, README, deck, video and `WHAT_IT_GETS_WRONG.md` is read from `validation/site_signal/summary.json`, `monitoring/out/*.json` or, for the evaluation study, `answer_key.json`. Planning-grid values and exploratory figures from before the SAP are never quoted. Numbers in this SAP are design parameters, not results.
2. **Labels.** Every view and every number is badged `SIMULATED` or `MEASURED` (§2.3). MEASURED live episodes at site 101 never pool with simulated episodes in any statistic.
3. **Uncertainty.** Every simulated rate carries its MC SE (§12.8). Every fixed-sample proportion carries a Clopper-Pearson 95% CI. Power is always reported at both tiers, including the *f* = 0.25 and 0.50 rows.
4. **Wording.** Say "capture discordance" and "a reason to look, not a finding". `none` reads "No signal at this sample size". Never "clean", never green. Never "detects under-reporting", "fraud" or "misconduct". The site query wording comes only from `data/site_queries.json`.
5. **Whole results.** If the committed study is unfavourable, for example a gross site not flagged or a false Watch flag, it is shown as it is. The failure case and the misspecified-null rows are reported next to the favourable rows, never instead of them.
6. **Rounding.** Proportions to 2 decimal places. MC SE and CI limits to 3. *z* to 2. O/E to 2. *E* and *V* to 1. Rounding applies only where a number is displayed (UI, `report.md`, README, deck, video). JSON outputs (`monitoring/out/*.json` including `thresholds.json`, `validation/site_signal/*.json`) store unrounded float64 values. Tier assignment, threshold calibration (§9.3), the REQ-023 inequalities and the §12.1 size-calibration check use those unrounded values.
7. **Provenance.** Every output carries `sap_tag_commit`, `eval_seed` and `code_commit`. `code_commit` is the last commit that changed an analysis input: `git log -1 --format=%H -- monitoring/bvsignal monitoring/params.yaml monitoring/uv.lock data/signal_rules.json data/ctcae_rules.json data/red_flags.json data/plan.json data/symptom_items.json backend/app/services/episodes.py backend/app/services/rules.py backend/app/content.py backend/app/config.py`. `generated_at` is that commit's time, so committing the outputs (or any later unrelated commit) does not change them. `report.md` links this SAP and states which §17 deviations, if any, apply.
8. **Next step.** Every results surface states that the only non-circular validation is retrospective analysis of trials with paired patient-reported and clinician-reported (CTCAE) data and site IDs.

---

## 16. Limitations

1. **Both streams are simulated.** Thresholds, power and the answer key all come from the same model family. The planted results show method and power under stated assumptions, not real-world validity.
2. **Thresholds come from an assumed null,** not one fitted to each study. Misspecification is quantified (§12.5, §12.6), not removed.
3. **The advantage over a rate KRI depends on assumptions.** It rests on case-mix variation being large relative to diligence variation among honest sites, and it shrinks in the failure case.
4. **Moderate gaps are mostly invisible at the Watch tier.** This is expected at these site sizes. The Look tier catches more, at the cost of the expected false Look flags per study in `thresholds.json`. Exact values are in `summary.json`.
5. **Moderate symptoms only.** Because of paging (§4.4), O/E covers non-paged grade 2 Diarrhea and Dyspnea, and the symptom-mix adjustment is an adjustment for the mix of those two. Fever and grade 3 capture are descriptive only.
6. **Three terms.** All other terms are reported but ungraded and excluded.
7. **Episode date = call date.** There is no onset item. The match window looks back to the previous call that reported the symptom below the episode's band (§5), with 2 days of tolerance; a site onset date earlier than that cannot match.
8. **Worsened episodes** need their own site row, which depends on sponsor conventions. Under the frozen red-flag rules every worsened (grade 3) episode is paged, so this matters only if those rules change.
9. **No MedDRA.** Matching uses CTCAE terms and our own synonyms. Real deployments need licensed coding by the sponsor.
10. **Patient-stream error is assumed, not measured.** The text-mode evaluation (n = 20) cannot estimate error by language or pace. Speech-recognition and accent error are unmeasured.
11. **The episode rate is an assumption.** *μ* = 1.5 represents a combination regimen. Power is lower at monotherapy-like rates (grid *μ* = 0.5).
12. **Discordance is not misconduct.** It includes baseline symptoms recorded as history, attribution decisions and grade conventions. The `honest_low_diligence` site is planted to show this.
13. **Independence holds only in shadow mode** (§2.4). Episodes on paged calls are separated, but a page may also raise the site's capture of the same subject's other episodes nearby; SE14 and SE15 bound this. Integrated mode is not supported and is guarded (`integrated_mode`).
14. **simaerep classic is the legacy algorithm.** The v1.0.0 inframe default is not ported.
15. **Regulatory questions are open (UNVERIFIED):**
    - investigator control of ePRO source data (EMA/INS/GCP/112288/2023 [22]);
    - the safety-awareness implications for a sponsor that receives an unfiltered patient stream.

    Shadow mode only.

---

## 17. Deviations

Empty at the `sap-v1` tag. Add one row per clarification or deviation (§1.4).

| ID | Date/time (ET) | Commit | SAP section | Type | Change | Reason | Eval outputs seen? | Expected effect |
|---|---|---|---|---|---|---|---|---|
| C1 | 2026-10-11 04:50 ET | Tag commit `68838978bb305e0f730d30e5cbf3c00bceca5a25` (annotated tag object `e5b4a7983c4a3f3b3bd5f46d8b6cdc65d9d4b1e6`, same sha on origin); row added in commit `WS5-S1: beacon round and evaluation seed` | §1.2 step 6, §1.3 | clarification | External timestamp of the `sap-v1` tag sha: GitHub Release https://github.com/feruzkarimovv/between-visits/releases/tag/sap-v1 (tag `sap-v1`, not a draft). Server `createdAt` 2026-10-11T08:37:58Z, which equals the tagger time because GitHub dates a release's `createdAt` from the git object it points to; server `publishedAt` 2026-10-11T08:38:10Z, the server's own publication time and the timestamp this plan relies on (git timestamps are author-set, §1.2). Tagger time of `sap-v1`: 2026-10-11T04:37:58-04:00 (08:37:58Z). Comparison: the external timestamp is **earlier** than the beacon round time 2026-10-11T08:48:00Z (drand round 6542582, row C2): `publishedAt` by 9 min 50 s, `createdAt` by 10 min 2 s. Pending human step: post the tag sha in the Devpost draft or the event's organizer channel; that link goes in a later §17 clarification. | §1.2 step 6 puts the external-timestamp links in a §17 clarification and requires the external timestamp to be earlier than the beacon round time. | No | None on any result; it shows that the tag existed before the beacon round. |
| C2 | 2026-10-11 04:50 ET | Commit `WS5-S1: beacon round and evaluation seed` (adds `monitoring/seed_beacon.json`) | §1.2 step 7, §1.3 | clarification | Beacon recorded by `uv run --project monitoring python -m bvsignal.seed --fetch-beacon --wait`. Source: drand mainnet, default chain `8990e7a9aaed2ffed73dbd7092123d6f289930540d7651336225dc172e51b2ce` (the pre-registered `params.yaml` `seeds.beacon.drand`). Round 6542582, round time 2026-10-11T08:48:00Z: the first round at or after the target 2026-10-11T08:47:58Z (tagger time + 10 min). URL https://api.drand.sh/public/6542582, fetched 2026-10-11T08:48:01Z. `B` = `3fc514414b1fb0df1e1d481dc41c23fcd9af60a03904016a12a0a5ebd77f61ac` (sha256 of the round signature, checked by `seed.py`; the same round read from https://drand.cloudflare.com/public/6542582 matches). `attempts`: `[]` (0 failed attempts; drand returned the round on the first try, 1 s after the round time), so neither the NIST fallback (allowed from 09:18:00Z) nor the empty `B` (from 09:48:00Z) was used. Evaluation seed derived by §1.3 (`--show`): `sap_tag_commit=68838978bb305e0f730d30e5cbf3c00bceca5a25 beacon_round=6542582 eval_seed=92794863`. | §1.2 step 7 commits the beacon file with a §17 clarification that cites its `attempts`. | No | No pre-specified choice changes; it fixes the evaluation seed for `calibrate.py`, `run.py`, `validate.py` and `blind.py --precompute`, none of which has been run with it. |
| C3 | 2026-10-11 06:00 ET | Commit `WS5-S4: indicators.py and calibrate.py` | §8.3, §9.2, §10.2, §10.3 | clarification | (1) simaerep classic orientation: calibration (§9.2–9.3) and tiers use the §10.2 statistic `prob` = −(1 − BH-adjusted `prob_low`), lower is more extreme. `thresholds.json` and the site rows serve it in simaerep's own orientation as `docs/03` §5.1 states it: `prob` = 1 − BH-adjusted `prob_low`, flagged when `prob` ≥ the served threshold, which is the calibrated threshold negated (a threshold of −∞ is served as null, never assigned). Both forms give every site the same tier. The row's `p_value` is the BH-adjusted two-sample Poisson *p*-value. (2) simaerep classic runs on every site of the study (resampling pool and BH family); the §10 `min_patients` guard decides only whether a site gets a tier. (3) Ablation (§10.3): the sum over primary terms, for both *U_s* and *E^U_s*, runs over the terms whose leave-one-site-out ratio is defined (Σ_{s'≠s} *N_{s'}(t)* > 0), so a term with no evaluable non-paged episode at the other sites contributes neither site rows nor expectation (under the frozen red-flag rules this is Fever, whose episodes are all paged, §4.4). A computed site with *E^U_s* = 0 is not computed for the ablation (`insufficient_episodes`). | `docs/03` §5.1 and SAP §10.2 state the simaerep direction in opposite orientations; the simaerep pool and BH family are not stated for a guarded site; the §10.3 expectation is undefined (0/0) for a term with no evaluable episodes elsewhere. | No | None on any discordance or rate-KRI result. (1) only changes a sign. (2) and (3) fix details the SAP leaves open, before any evaluation-seed run. |
| C4 | 2026-10-11 07:35 ET | Commit `WS5-S1: post-tag housekeeping (docs/11 §17 C4, HUMAN_TODO, number scan skips lockfiles)` | §1.2 steps 2, 3 and 5; REQ-022 | clarification | Where §1.2 (and `docs/09` § Pre-registration order) says "on `main`", it is read as the implementing session's working branch `site-signal-build`, as `docs/09` § Checkpoints and `docs/KICKOFF.md` (step 1, Branch: "Where the docs say 'on `main`', read it as your branch") allow. That branch is merged into `main` with a merge commit, never squashed or rebased (`HUMAN_TODO.md` item 1). Accordingly: (1) the annotated tag `sap-v1` is on commit `68838978bb305e0f730d30e5cbf3c00bceca5a25`, which was already pushed to `origin/site-signal-build` when it was tagged (the build machine's reflog records that push at 04:36:28 ET, before the tagger time 04:37:58 ET); it is not yet on `origin/main`. (2) The step 3 check ran on that commit: `git ls-tree -r 68838978bb305e0f730d30e5cbf3c00bceca5a25 --name-only` lists nothing under `monitoring/out/` or `validation/site_signal/`. (3) Commits that add evaluation outputs are made on `site-signal-build` after the tag and are never rebased, so the tag commit is their ancestor there, and the merge commit of `HUMAN_TODO.md` item 1 keeps that ancestry on `main` (REQ-022). | `docs/KICKOFF.md` forbids the implementing session to push to `main`, and `docs/09` § Checkpoints allows the working branch, merged into `main` with a merge commit. Without this row, §1.2 steps 2, 3 and 5 read as if the tag had to be on `origin/main`. | No | None on any result: the tag commit, the beacon round and the evaluation seed (rows C1, C2) are unchanged, and no pre-specified choice changes. |
| C5 | 2026-10-11 07:50 ET | Commit `WS5-S6: run.py and report.py (make site-signal), REQ-022/REQ-030 tests, Makefile, CI` | §15 rule 7, §8.3, §10.3, §12.7 | clarification | (1) `episodes.json` and `site_ae.json` are top-level arrays (`docs/02` § Files behind Site Signal), so the files cannot hold the §15 rule 7 provenance fields themselves: each element carries `data_origin`, and `signal_run.json` `run.outputs` records the sha256 of both files next to `sap_tag_commit`, `eval_seed` and `code_commit`. (2) The numbers that only `report.md` shows (the §8.3 calibrated *p*-values with BH *q*-values, the §10.3 ablation rows, the §6.2 paged stratum and the §4.1 ungraded primary-term reports per site) are written by `run.py` to `monitoring/out/report_only.json`, with the provenance fields, so that `report.py` renders `report.md` from JSON outputs only; nothing reads that file for a tier or a UI column. (3) §12.7 reports the two must-be-grey sites separately for every indicator: they are in no confusion cell of any indicator (including the comparators, for which the `low_coverage` site has no coverage guard) and `answer_key.json` `must_be_grey` lists each indicator's tier and reason for them. | §15 rule 7 asks every output to carry provenance, which a JSON array cannot; the SAP does not say where report-only numbers are stored or how the comparators treat the `low_coverage` site in the confusion. | No | None on any result or tier: no pre-specified choice changes; the confusion is an illustration only (§12.7). |
| C6 | 2026-10-11 08:15 ET | Commit `WS5-S9: equity.py (MH odds ratio, patient bootstrap, RBG, Breslow-Day, single-language counterfactual), REQ-031 test` | §14, §1.3, §12.3 | clarification | Choices §14 leaves open, fixed in `monitoring/bvsignal/equity.py` before any evaluation-seed run. (1) Bootstrap clusters are the patients with at least one *A_s* episode at a site used, sorted by subject id. Each site draws its *B* resamples as `Generator(PCG64(SeedSequence(entropy, spawn_key=(*key.spawn_key, site_index)))).integers(0, n, size=(B, n))`, where `key` is the §1.3 `role` 2 key and `site_index` the site's position in the study's site order, so a site's resamples do not depend on which other sites are used and the first *B'* resamples of a larger run equal a *B'* run (the §12.3 quick subset). Language, pace, the site × term sensitivity and the per-site intervals share these resamples. (2) A resample whose pooled *R* and *S* are both 0, or a per-site resample with an empty group, has no defined log odds ratio and is left out of the percentiles (reported as `n_undefined`); ln *OR* = ±∞ is kept; percentiles use `numpy.quantile` `linear` on the sorted values, taking the outer order statistic next to an infinite value; an infinite bound is served as null. (3) The 0.5 zero-cell correction applies to per-site tables, also inside each resample; the Mantel-Haenszel estimate, its RBG variance (Wald interval on the log scale with the normal 0.975 quantile) and Breslow-Day use the raw counts. (4) Breslow-Day is uncorrected and evaluated at *OR_MH*; strata whose margins fix *a_k* are left out; df = remaining strata − 1; no test with fewer than 2 such strata. (5) The site × term sensitivity keeps the §14 sites used (site-level ≥ 5 rule) and only splits their episodes by term. (6) Single-language counterfactual: Spanish-speaking patients' calls are removed (scheduled and completed); the patients stay enrolled at their site (§7 check 4 counts them) and the site AE log is unchanged; *τ̂²* is re-estimated within the counterfactual study; `reason` is the counterfactual `not_computed_reason`; `share_no_reference_stream` = Spanish-speaking patients ÷ patients at the site. | §14 does not fix the cluster set, the key layout of the per-site resamples, undefined resamples, how the zero-cell rule meets the bootstrap, the Breslow-Day variant or the counterfactual's patient count. | No | None on any other output: equity draws only from its own `role` 2 keys, and a dev-seed run gives outputs other than `equity.json` identical apart from `code_commit` and `generated_at`. No pre-specified choice changes. |
| C7 | 2026-10-11 08:30 ET | Commit `WS5-S7: validate.py operating characteristics (SAP §12), quick check, site-signal-validate` | §12, §12.1, §12.3, §12.8, §14 | clarification | Choices `monitoring/bvsignal/validate.py` makes where §12 leaves them open, fixed before any evaluation-seed validation run and independent of any evaluation output: (1) `quick_hashes` has one entry per stream (`committed_study`, `null_validation`, `power_grid`, `failure_and_sensitivity`): the sha256 of the canonical JSON of the threshold-free per-replicate results (per indicator and site the calibration statistic and §7 reason; discordance *E*, *φ̂*, *τ̂²*; planted labels; equity intervals; the committed study's episode statuses) of the first `calibration.r_quick` replicates of the two `r_validation`-sized sets (§12.1 null validation, §12.3 full mix), the first `grid.reps_quick` replicates of every other set (per-design and failure-case calibration, power, sensitivity), and every §12.6 (i) re-run of the committed study; `--quick` runs exactly those replicates. (2) §12.1 *E_s* tertiles: cut points at the linear 1/3 and 2/3 quantiles of discordance *E_s* over every discordance-computed site of the null studies; comparators and the ablation are reported on the sites that have such an *E_s*; *K* bins use each indicator's own number of computed sites. (3) §12.3 equity inside a replicate: the resampling unit is a patient with at least one *A_s* episode at an included site; one `integers(0, n_k, size=(B, n_k))` draw per included site in site order from the role-2 generator (language before pace); percentile interval by linear interpolation with ±∞ allowed; resamples with an undefined odds ratio (*R* = *S* = 0) are left out and counted; "contains 1" means lo ≤ 0 ≤ hi on the ln scale. (4) `look_per_site.ci95` is a normal interval from the cluster-aware MC SE; Clopper-Pearson intervals go on the Watch family-wise rates (§12.8). (5) A REQ-023 rate is `failure` above its bound, `conservative` below nominal and `pass` otherwise; the overall status is that of discordance, every indicator is reported. | §12 does not say which replicates the quick hashes cover, the *E_s* population for comparators, the bootstrap resampling unit and draw order, or how an undefined bootstrap odds ratio is treated. | No | None on any pre-specified quantity; it fixes details before the first evaluation-seed run of `validate.py`. |
| C8 | 2026-10-11 10:55 ET | Commit `WS5-S7: final review fix: run the quick check on macOS arm64 (own workflow, never cancelled); power_grid hash not reproduced on Linux is a stated limit` | §12 | clarification | Where §12 says "CI runs `--quick --check`", the check runs on macOS arm64, the platform of the committed evaluation runs (`validation/site_signal/run_log.jsonl`), in its own workflow `.github/workflows/site-signal-quick-check.yml` (`runs-on: macos-latest`; concurrency `cancel-in-progress: false`, so a newer push never cancels a running check). On ubuntu-latest (x86_64), CI run 38141286952 (commit 97eccb9) reproduced `committed_study`, `null_validation` and `failure_and_sensitivity` and printed `MISMATCH power_grid` (summary `24385678…b7f36d`, quick `ed251700…c5531`), then `quick check FAILED`; on macOS arm64 all four hashes equal `summary.json` (final review, 56 s). The step had run in the `ubuntu-latest` job `monitoring` of `ci.yml`, where every later run was cancelled by the next push, so the failure did not show. No analysis code, input or output changes: `validate.py`, `params.yaml`, `summary.json` and `quick_hashes` are as committed. | The per-replicate power-grid results are not bit-identical across platforms (the cause, most likely floating-point differences between the platform builds of the numerical libraries, was not investigated), so the §12 exact-equality gate can hold only on the platform of the committed run. Rounding before hashing would change `validate.py` and `quick_hashes` after the evaluation outputs exist. | Yes (the Linux hash mismatch) | None on any committed number. The limit is stated in `WHAT_IT_GETS_WRONG.md` §16: Linux reproduces three of the four quick hashes bit for bit, not `power_grid`. |
| C9 | 2026-10-11 11:30 ET | Commit `WS4-D13: final review fix: report the comparators' and the ablation's size-calibration failures (WHAT_IT_GETS_WRONG §2, docs/11 §17 C9)` | §12.1 | clarification | Where §12.1 says a size-calibration failure "is reported in `report.md` and `WHAT_IT_GETS_WRONG.md`", the size check of every indicator is reported in `WHAT_IT_GETS_WRONG.md` §2 (one table for discordance, one row per comparator and the ablation, rendered from `summary.json` `null.acceptance.by_indicator.<id>.size_calibration` by `validation/render_numbers.py`) and, for discordance, the rate KRI and simaerep classic, on the How well it works tab (the Size line of the null table), not in `validation/site_signal/report.md`. `summary.json` marks the check `failure` for `rate_kri`, `simaerep_classic` and `ae_report_ratio` and `pass` for discordance. | `report.md` is rendered by `run.py`/`report.py` from the committed-study outputs (§12.7) before `validate.py` writes `summary.json`, so it cannot hold the §12.1 size check; regenerating it would change a committed evaluation output. Until the final review, no document showed the three failures. | Yes (the failures were found in `summary.json` after the validation run) | None on any number or tier; the failures are now stated where §12.1 requires them to be visible. |
| | | | | | | | | |

---

## 18. Traceability

Status of every requirement below: **planned: add to `requirements.yaml` together with their tests.** The full list is in `docs/07` §6. `make validate ARGS=--check` fails CI for a listed requirement without a passing test, so each ID enters `validation/requirements.yaml` only in the commit that adds its test.

| SAP section | Requirement (planned) | Test |
|---|---|---|
| §1.1, §8, §9 | REQ-021 No LLM on the statistics path | `monitoring/tests/test_no_llm.py` |
| §1.2, §1.3 | REQ-022 Pre-registration order (tag ancestry, seed with beacon, run log) | `monitoring/tests/test_sap_order.py` |
| §9, §12.1 | REQ-023 Calibrated thresholds | `test_null_smoke.py`, `validate --quick --check` |
| §2.4, §5, §6 | REQ-024 Stream independence | `backend/tests/test_episodes.py`, `monitoring/tests/test_match.py` |
| §7 | REQ-025 Never green | `test_match.py`, `backend/tests/test_site_signal_api.py` |
| §2.1, §11.2 step 9 | REQ-026 Evidence on every flag | `backend/tests/test_site_signal_api.py` |
| §10 | REQ-028 Comparators and ablation on identical data | `monitoring/tests/test_simaerep_fixture.py` |
| §13 | REQ-029 Blind run is demo-only, hidden and audited | `backend/tests/test_blind_run.py` |
| §2.3, §15 | REQ-030 SIMULATED / MEASURED labeling | `monitoring/tests/test_labels.py`, API schema walk |
| §14 | REQ-031 Equity strata | `monitoring/tests/test_equity.py` |
| §8 | Hand-computed O, E, cluster-robust V, *z*, *φ̂*, *τ̂²*, *z\** to 1e-9 | `monitoring/tests/test_indicators.py` |
| §11 | Determinism (same seed gives the same output hash) | `monitoring/tests/test_determinism.py`, `test_simulate.py` |

---

## 19. References

Figures marked "secondary summary" or UNVERIFIED were not re-checked against the full text in this planning round.

1. Di Maio M, Gallo C, Leighl NB, et al. Symptomatic toxicities experienced during anticancer treatment: agreement between patient and physician reporting in three randomized trials. *J Clin Oncol* 2015;33(8):910–915. (Ranges via a secondary summary.)
2. Veitch ZW, Shepshelovich D, Gallagher C, et al. Underreporting of symptomatic adverse events in phase I clinical trials. *J Natl Cancer Inst* 2021;113(8):980–988.
3. Basch E, Jia X, Heller G, et al. Adverse symptom event reporting by patients vs clinicians: relationships with clinical outcomes. *J Natl Cancer Inst* 2009;101(23):1624–1632.
4. ICH E9(R1) Addendum on estimands and sensitivity analysis in clinical trials (Step 4, 20 Nov 2019).
5. ICH E6(R3) Guideline for Good Clinical Practice (Step 4, 6 Jan 2025), centralised monitoring. Paraphrase, UNVERIFIED against the PDF.
6. FDA CDER. "A Data Anomaly Detection Tool" (SMART) poster, in the HackRU Fall 2026 challenge kit reading list.
7. Spiegelhalter DJ. Funnel plots for comparing institutional performance. *Stat Med* 2005;24(8):1185–1202.
8. Spiegelhalter DJ. Handling over-dispersion of performance indicators. *Qual Saf Health Care* 2005;14(5):347–351.
9. Gilead-BioStats/gsm (Apache-2.0), KRI method vignette (`kri0001`, normal approximation, overdispersion). https://github.com/Gilead-BioStats/gsm
10. Koneswarakantha B, et al. *Ther Innov Regul Sci* 2024, doi:10.1007/s43441-024-00631-8 (as cited in the simaerep v1.0.0 DESCRIPTION file).
11. openpharma/simaerep v1.0.0 (MIT): source, NEWS.md (v1.0.0 defaults) and regression data `R/sysdata.rda`. https://github.com/openpharma/simaerep
12. Benjamini Y, Hochberg Y. Controlling the false discovery rate: a practical and powerful approach to multiple testing. *J R Stat Soc B* 1995;57(1):289–300.
13. Clopper CJ, Pearson ES. The use of confidence or fiducial limits illustrated in the case of the binomial. *Biometrika* 1934;26(4):404–413.
14. Hanley JA, Lippman-Hand A. If nothing goes wrong, is everything all right? Interpreting zero numerators. *JAMA* 1983;249(13):1743–1745.
15. Mantel N, Haenszel W. Statistical aspects of the analysis of data from retrospective studies of disease. *J Natl Cancer Inst* 1959;22(4):719–748.
16. Robins J, Breslow N, Greenland S. Estimators of the Mantel-Haenszel variance consistent in both sparse data and large-strata limiting models. *Biometrics* 1986;42(2):311–323.
17. Morris TP, White IR, Crowther MJ. Using simulation studies to evaluate statistical methods. *Stat Med* 2019;38(11):2074–2102.
18. NumPy documentation, `numpy.random.SeedSequence` (spawning independent streams).
19. NCI. Common Terminology Criteria for Adverse Events (CTCAE) v5.0, 2017. Grade text in `data/ctcae_rules.json`.
20. Tufts CSDD 2017 eClinical Landscape study (8 days from visit to data entry), as quoted in the HackRU Fall 2026 challenge kit; also `docs/00-overview.md`.
21. Wang Y, Zhou S, Yang F, et al. Treatment-related adverse events of PD-1 and PD-L1 inhibitors in clinical trials: a systematic review and meta-analysis. *JAMA Oncol* 2019;5(7):1008–1019. (Context only; UNVERIFIED, not re-checked.)
22. EMA. Guideline on computerised systems and electronic data in clinical trials, EMA/INS/GCP/112288/2023.
23. Haldane JBS. The estimation and significance of the logarithm of a ratio of frequencies. *Ann Hum Genet* 1956;20(4):309–311.
24. Woolf B. On estimating the relation between blood group and disease. *Ann Hum Genet* 1955;19(4):251–253.
25. drand, League of Entropy public randomness beacon, mainnet (`default` chain), HTTP API `https://api.drand.sh/public/{round}`. https://drand.love
26. NIST Randomness Beacon, version 2.0. https://beacon.nist.gov
27. Breslow NE, Day NE. *Statistical Methods in Cancer Research, Vol. I: The Analysis of Case-Control Studies.* IARC Scientific Publications No. 32, 1980.
