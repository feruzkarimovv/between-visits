# WS4 · Data, evaluation and story

Owner: teammate 4. Folders: `data/`, `eval/`, `validation/`, `README.md`, plus the deck and video.
Read first: `CLAUDE.md`, `docs/05-clinical-rules.md`, `docs/07-eval-and-validation.md`, `docs/08-demo-and-pitch.md`.

The clinical content and seed data are already written in `data/` (from the research done on Saturday afternoon). Your job: own their correctness, build the evaluation and validation tooling, and own the story (README, deck, video, Devpost).

## Kickoff prompt for Claude Code

> You are implementing workstream WS4 (data, evaluation, story) of Between Visits. Read CLAUDE.md, docs/05-clinical-rules.md, docs/07-eval-and-validation.md, docs/08-demo-and-pitch.md and docs/workstreams/WS4-data-eval-story.md. Start with task D1 (validate the data files), then D2 (evaluation harness). The harness must call the backend's real service functions in-process (backend/app/services/*), not reimplement them; if a function you need doesn't exist yet, write the harness against the interface described in docs/workstreams/WS2-backend.md and stub it until WS2 lands it. Use plan mode for each task. Commit each task as "WS4-Dn: <summary>". Only edit data/, eval/, validation/ and README.md.

## Tasks

### D0 · Local phone numbers (first 15 minutes)
- Create `data/patients.local.json` (gitignored) mapping patient IDs to teammates' verified phone numbers, and put the nurse and backup numbers in `.env`. Confirm every number is verified in Twilio.

### D1 · Validate the data files (target 6:00 PM)
- `data/validate_data.py` already exists and passes (cross-references between items, rules, red flags, scripts, tools, prompt and personas; licensed-content guards). Add it to `make test`, and extend it with Pydantic models for each file's shape. Run it after every content edit.
- Read every Spanish string out loud once. Fix anything awkward; keep "usted".
- **Accept:** script exits 0; add it to `make test`.

### D2 · Evaluation harness, text mode (target 3:30 AM, M3 gate)
- `eval/run_eval.py` per `docs/07-eval-and-validation.md` § Harness: in-process backend services on a temp DB; agent = Gemini with `agent/prompt.md` rendered exactly like a real call (same dynamic variables), tools declared as Gemini function declarations mirroring `agent/tools.json`; patient = Gemini persona; loop until `end_call` or 40 turns; post-call pipeline; scoring; `eval/results/latest.json` + `eval/results/transcripts/<id>.json`.
- `eval/score.py`: pure scoring functions with unit tests (expected vs actual escalation, AE terms, grades, CM, disclosure, approved wording similarity, pace checks).
- `eval/judge.py`: Gemini judge prompts for "no medical advice" and "read-back before recording" returning JSON `{"pass": bool, "evidence": "..."}`; temperature 0.
- Flags: `--personas P16,P04`, `--concurrency 2`, `--mode text|elevenlabs`, `--seed 7`.
- **Accept:** `make eval` completes all 20 personas and writes valid `latest.json`; the report card page renders it.

### D3 · Known misses and fixes (target 5:00 AM)
- Read every failing persona transcript. For each failure, decide: fix (tell WS1/WS2 what to change) or keep as an honest known miss with a planned fix in `latest.json`. Re-run after fixes. Keep at least one honest known miss if one exists; never hide failures.

### D4 · Validation pack (target 4:30 AM)
- `validation/requirements.yaml` (already written) and `validation/build_traceability.py` per `docs/07-eval-and-validation.md` § Validation pack. Coordinate with WS2 so every requirement has at least one tagged test.
- **Accept:** `make validate` writes `validation/traceability.md` and `validation/summary.json`; `--check` passes in CI.

### D5 · README (draft by 4:00 AM, final by 8:00 AM)
- Fill the skeleton in `README.md`: one-paragraph pitch, demo video link, screenshots/GIF, the problem with sources, how it works (diagram), safety design, evaluation results table (from `latest.json`), quickstart (demo mode in 3 commands, full mode with keys), configuration, data sources and licenses (CTCAE public domain, PRO-CTCAE terms, synthetic data statement), limitations, "not a medical device", team, MIT license.
- **Accept:** a teammate who hasn't seen the repo follows the README on a clean laptop and runs demo mode in under 10 minutes.

### D6 · Deck and video (deck draft 5:00 AM, video recorded by 8:30 AM)
- Deck: 11 slides per `docs/08-demo-and-pitch.md`, built from real screenshots and real numbers.
- Video: follow the script table exactly; record the hero call with WS1 at about 7:30 AM in a quiet room; add Spanish subtitles; export 1080p; upload unlisted to YouTube.
- **Accept:** video ≤ 3:15, deck ≤ 12 slides, both linked in the README.

### D7 · Devpost (submit by 9:30 AM)
- Text from the README; track Social Good; superlatives Regeneron and ElevenLabs; all four contributors; links to repo, video, deck. Screenshot the confirmation.

---

## Site Signal plan (Sat Oct 10, late)

Added in the planning round on Sat Oct 10, late. Tasks D0–D7 above are the original Saturday plan and stay as history. This section continues the D series. Times are Sun Oct 11, ET. Checkpoints and cut rules: `docs/09-timeline-and-workstreams.md`. Human actions: `docs/workstreams/WS0-readiness.md` § Human actions.

WS4 owns three things in this plan: the data files that are frozen with the Site Signal SAP (`data/signal_rules.json`, `data/site_queries.json`), the corrections in `data/` and the evaluation numbers at Checkpoint A, and the story (traceability, `WHAT_IT_GETS_WRONG.md`, `NOT_BUILT.md`, deck, video, README, Devpost).

Rules for the story in this plan:
- **Every number has a source file.** Site Signal numbers come only from `validation/site_signal/summary.json` (or `monitoring/out/*.json` for the committed study); evaluation numbers from `eval/results/latest.json`; real-call numbers from `eval/results/voice_checks.json`. Every chart and number is labeled SIMULATED or MEASURED; every proportion shows its interval.
- **Wording:** "capture discordance", "a reason to look, not a finding". Never "detects under-reporting", "fraud" or "misconduct". The patient stream is a reference, not the truth.
- **Rule 8:** the drug by class only (anti-PD-1; CD3 bispecific in roadmap context). No product brand name, product code or generic name anywhere in git; the D8 guard enforces it.
- **Neutral voice:** product and engineering facts with sources; unverified claims marked UNVERIFIED.

### Kickoff prompt for this section

> You are continuing workstream WS4 (data, evaluation, story) of Between Visits. Read CLAUDE.md, docs/05-clinical-rules.md, docs/07-eval-and-validation.md (including §6, Site Signal validation), docs/08-demo-and-pitch.md, docs/10-site-signal.md, docs/11-site-signal-sap.md §1–§7 and §15, and the section "Site Signal plan (Sat Oct 10, late)" at the end of docs/workstreams/WS4-data-eval-story.md. Do D11 and D8 first (D11 must be committed before the sap-v1 tag at 02:45 ET), then D9 and D10 for Checkpoint A (03:30). Never write a product brand name, product code or generic name into any file, and never invent clinical wording or thresholds. Use plan mode per task, run each acceptance check exactly as written, show the output, and commit as "WS4-Dn: <summary>".

### D8 · Spanish "del" fix and product-name leak removal (target 02:20, Checkpoint A)
- `data/study.json`: `study_team_name.es` becomes `equipo de investigación de Hillside`; remove `registry_title` (or replace it with a class-only paraphrase, "a phase 2 study of an anti-PD-1 monoclonal antibody").
- `data/scripts.json`: Spanish templates say `del {study_team_name}` (no "de el" anywhere). The Spanish disclosure and the offer of a human stay otherwise identical (rule 4).
- `data/red_flags.json`: every source citation names the class only, e.g. "US Medication Guide of an approved anti-PD-1 antibody (class only), section on intestinal problems".
- `scenarios/rosa_es_urgent.json`: regenerate the first-message line (coordinate with WS1/WS2, who own `scenarios/`).
- `docs/05-clinical-rules.md` §1 licensing table: the row that names the brand becomes "US Medication Guide of an approved anti-PD-1 antibody (class only)" (the planning round already made this edit; D8 confirms the guard finds nothing there).
- `data/validate_data.py` gains a **product-name guard** that never writes the names into git: it lowercases every text file from `git ls-files -co --exclude-standard` (skipping binaries and lockfiles), splits it into `[a-z0-9]+` tokens, and fails with `file:line` when a token's sha256 is in a short denylist of hashes. The denylist has three hashes, computed locally and committed as hashes only: the brand token from the `data/red_flags.json` citations and the product-code token from `data/study.json` `registry_title` (both read before this task removes them), and the generic-name hash the team lead supplies at 02:00 (`docs/09` § Human actions; if it has not arrived, ship two hashes and add the third when it does). It prints `product names: 0 hits in N files`. A self-test swaps in the hash of a dummy token and checks that a temp file containing it fails.
- Backend test: the Spanish first message contains "del equipo" (`backend/tests/test_disclosure.py`).
- **Files:** `data/study.json`, `data/scripts.json`, `data/red_flags.json`, `data/validate_data.py`, `scenarios/rosa_es_urgent.json`, `backend/tests/test_disclosure.py`, `docs/05-clinical-rules.md` (§1, only if a hit remains).
- **Accept:**
  ```bash
  uv run --project backend python data/validate_data.py; echo "exit=$?"
  grep -rn 'de el ' data/ scenarios/
  cd backend && uv run pytest -q tests/test_disclosure.py
  ```
  The validator prints `product names: 0 hits in N files` and `exit=0`; the grep prints nothing; the disclosure tests pass.

### D9 · Grade-band boundary tests, contiguity check, mutation probe (target 03:00, Checkpoint A)
- `backend/tests/test_rule_boundaries.py`: the six boundaries read from `data/ctcae_rules.json` (Diarrhea G1/G2 and G2/G3, Fever G1/G2 and G2/G3, Dyspnea G1/G2 and G2/G3): the value at each edge and one unit either side gets the expected grade from `rules.grade()`. Tag REQ-004. No threshold is written in the test; it reads them from the data file.
- `data/validate_data.py`: per term, the grade bands are contiguous and do not overlap.
- `data/mutation_probe.py`: copies `data/` to a temp directory, shifts each numeric threshold by ±1 unit one at a time, runs the boundary tests against the copy, and prints `killed N/N`.
- **Files:** `backend/tests/test_rule_boundaries.py`, `data/validate_data.py`, `data/mutation_probe.py`.
- **Accept:**
  ```bash
  cd backend && uv run pytest -q tests/test_rule_boundaries.py
  cd .. && uv run --project backend python data/mutation_probe.py
  ```
  The boundary tests pass; the probe prints `killed N/N` with N equal to the number of generated mutants (26 expected).

### D10 · Clopper-Pearson intervals on the report card (target 03:15, Checkpoint A)
- `eval/score.py`: exact Clopper-Pearson 95% intervals in pure Python for every proportion metric (overall, `by_language`, `by_pace`); `zero_failure_n: {"0.90": 29, "0.95": 59, "0.99": 299}`; `--rescore <file>` recomputes from the stored per-persona results without any LLM call.
- `eval/results/latest.json`: rescored (no new evaluation run).
- Report card (`frontend/src/app/report-card/page.tsx`, coordinate with WS3): every proportion shows its interval; the zero-failure note ("8/8 is consistent with up to a 37% miss rate; 59 consecutive catches are needed to show at least 95% recall at one-sided 95% confidence"), with its numbers rendered from the file; a separate MEASURED "Real voice calls" row from `GET /api/eval/voice-checks` when present, never pooled with text mode; a line stating whether the evaluated agent model equals the deployed one.
- `docs/07` §6: the traceability note that the 8/8 red-flag evidence covers the `report_red_flag` and live paging path, while the threshold rules are covered by unit tests, is already drafted; update it only if the rescored file says otherwise.
- **Files:** `eval/score.py`, `eval/results/latest.json`, `backend/tests/test_eval_score.py`, `frontend/src/app/report-card/page.tsx`, `docs/07-eval-and-validation.md`.
- **Accept:**
  ```bash
  uv run --project backend python eval/score.py --rescore eval/results/latest.json
  jq -c '.overall.red_flag_recall_ci95, .zero_failure_n' eval/results/latest.json
  cd backend && uv run pytest -q tests/test_eval_score.py
  ```
  Prints `[0.631,1]` (3 dp) and the zero-failure map; the test also checks 19/20 → [0.751, 0.999]; the report card shows the intervals.

### D11 · Signal rules and site query data files (target 02:20, checkpoint SAP)
Frozen by the `sap-v1` tag (WS5 S1). After the tag, any change needs a row in `docs/11` §17.
- `data/signal_rules.json`: exactly the schema and key names in `docs/02` § Files behind Site Signal (the JSON block there): `primary_terms`, `min_grade`, `episode`, `ungraded_terms_policy`, `match` (upper window 7, `lower_anchor: "last_negative_call"`, `lower_tolerance_days` 2, sensitivity windows SE1/SE2, one-to-one, `exclude_origins`, `term_synonyms` in lower case, our own list, no MedDRA), `evaluability`, `paged` (with `proximity_days` for SE14), `minimum_data`, `integrated_mode`, `tiers`, `overdispersion` (additive, winsor [0.10, 0.90]), and English `labels` (tiers, footer, `footer_expected_false_look` template, one sentence per `not_computed` reason including `integrated_mode`, and `answer_key` display labels that never call a site an under-reporter).
- `data/site_queries.json`: template `SQ_UNMATCHED_EPISODES` (`title_en`, `body_en`, `episode_line_en`), `response_codes` (`entered_now`, `recorded_as_medical_history`, `recorded_under_other_term`, `not_an_ae_per_investigator`, `other`, each with `label_en`), `banned_phrases_en`. Starting draft of the body, for WS4 to finalize: "Site {site_id}: between-visit calls recorded the symptom reports listed below. We could not find a matching entry in the AE log. Please review the source documents for each listed subject and date, and either enter the event or tell us why no entry is needed. {episode_lines} This is a data-completeness request only. It is not a finding about the site and does not concern clinical management." Episode line: "- {subject_id}: {term}, reported on the call of {episode_date} (provisional grade {grade}, rule-graded)". Data completeness only, non-leading, subject IDs only.
- `data/validate_data.py`: schemas for both files (every `not_computed` reason and every answer-key key has a label; no banned phrase in any label); placeholders limited to `{site_id}`, `{episode_lines}`, `{subject_id}`, `{term}`, `{episode_date}`, `{grade}`; no banned phrase in any template; no name placeholder; every primary term has G2 and G3 rules in `data/ctcae_rules.json`; synonyms lower-case and unique across terms.
- **Files:** `data/signal_rules.json`, `data/site_queries.json`, `data/validate_data.py`.
- **Accept:**
  ```bash
  uv run --project backend python data/validate_data.py; echo "exit=$?"
  ```
  `exit=0`; the validator's self-test (a temp copy with a banned phrase inserted into the body) exits 1.

### D12 · Traceability covers monitoring tests; regenerate at HEAD (target 06:05, Checkpoint B)
- `validation/build_traceability.py` also runs `uv run --project monitoring pytest -p req_plugin` (with `validation/req_plugin.py`) and merges the results; `monitoring/tests/conftest.py` registers the `req` marker. From this commit, requirements whose tests live only in `monitoring/tests/` can enter `requirements.yaml`.
- `.github/workflows/ci.yml`: the job that runs `build_traceability.py --check` checks out with `fetch-depth: 0` and `fetch-tags: true` (REQ-022 needs the history and the tag) and runs `uv sync --project monitoring` first (numpy and scipy live there).
- Regenerate `validation/traceability.md` and `validation/summary.json` at HEAD in a commit that changes nothing outside `validation/`.
- **Files:** `validation/build_traceability.py`, `validation/req_plugin.py`, `monitoring/tests/conftest.py`, `.github/workflows/ci.yml`, `validation/requirements.yaml`, `validation/traceability.md`, `validation/summary.json`.
- **Depends on:** S6, B20.
- **Accept:**
  ```bash
  make validate ARGS=--check; echo "exit=$?"
  jq -r .commit validation/summary.json; git rev-parse --short HEAD~1
  git show --stat --format= HEAD | grep -v '^ validation/'
  ```
  `exit=0` with REQ-001..030 PASS; the stamped commit equals the parent of the regeneration commit; the last command prints only the summary line; the CI job that runs the traceability check is green on the D12 commit.

### D13 · WHAT_IT_GETS_WRONG.md and NOT_BUILT.md (target 07:00, Checkpoint C)
- `WHAT_IT_GETS_WRONG.md`: moderate capture gaps are mostly invisible at the Watch tier (values from `summary.json`, both tiers, the *f* = 0.25 and 0.50 rows with MC SE); the diligence-dominated failure case; both streams simulated; thresholds from an assumed null (misspecification rows); the episode-rate assumption; ungraded terms; episode date = call date; no MedDRA; speech-recognition error unmeasured; the P19 known miss; paged episodes as a separate stratum; discordance includes legitimate clinical judgment; the non-circular next step (retrospective analysis of trials with paired patient-reported and clinician-reported data). Footer: how every number was checked against its source file.
- `NOT_BUILT.md` (repository root): one line per `docs/backlog.md` entry (BL-01..BL-20) plus one per cut applied tonight (titles in `docs/backlog.md` §5), each later linked to its issue (WS0 R11). README links both.
- **Files:** `WHAT_IT_GETS_WRONG.md`, `NOT_BUILT.md`, `README.md`.
- **Depends on:** S7; `docs/backlog.md`.
- **Accept:** every number in `WHAT_IT_GETS_WRONG.md` matches `validation/site_signal/summary.json`, `eval/results/latest.json` or `voice_checks.json` (checked by the method stated in its footer); `uv run --project backend python data/validate_data.py` still reports 0 product-name hits.

### D14 · 10-slide deck (draft from 05:50, final 08:45, Packaging)
- Ten slides per the deck outline in `docs/08-demo-and-pitch.md`; screenshots from the production build (F19); every number traceable to `summary.json`, `latest.json` or `voice_checks.json`; SIMULATED or MEASURED on every chart; intervals on every proportion; the drug by class only. Export `docs/pitch/deck.pdf`.
- **Files:** `docs/pitch/deck.pdf`, `docs/08-demo-and-pitch.md` (final slide list).
- **Depends on:** Checkpoint B, D13.
- **Accept:** 10 slides; a second teammate ticks every number against its source file; the PDF is linked from the README.

### D15 · 3:00 video (recorded 07:40–08:10, uploaded by 08:30, Packaging)
- Follow the storyboard in `docs/08`. Recorded on the production build (no dev badge); opens with the real call (V12) and the nurse phone; every data view badged; the limits beat uses numbers from `summary.json` and the report-card intervals. Upload unlisted.
- **Files:** README link; `docs/08` storyboard (final).
- **Depends on:** V12, F19, the 07:30 freeze.
- **Accept:** length ≤ 3:00; uploaded by 08:30; the README link plays in an incognito window.

### D16 · README final and Devpost (by 09:30, Packaging)
- README: video, deck, public demo URL, Results (evaluation with intervals, real voice calls, Site Signal summary with MC SE, all labeled), Roadmap (issues), team.
- Devpost: text from the README, links to the repository, video, deck and demo; all contributors; reviewer access to the private repository arranged as the team lead decides (open question).
- **Files:** `README.md`.
- **Depends on:** D14, D15, R12.
- **Accept:** `grep -n '_TODO_' README.md` prints nothing; every link resolves in an incognito window; Devpost confirmation captured by 09:30.
