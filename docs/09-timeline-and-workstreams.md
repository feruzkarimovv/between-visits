# 09 · Timeline, workstreams and risks

All times Eastern. Devpost submission is due **Sun 10:00 AM** (aim 9:30). Hacking ends 11:30 AM. Judging from 12:30 PM.

The current plan is the first section. The original Saturday plan (milestones M0–M5) is kept unchanged at the end as history; the state of the build is in `CLAUDE.md` § Status.

## Sat Oct 10, late: Site Signal plan

Decided by the team lead on Sat Oct 10, ~11:30 PM. **Direction: Between Visits + Site Signal.** The voice product stays the patient-facing core. Site Signal is additive and does not touch the safety path (`rules.py`, `interview.py`, `escalation.py`, `postcall.py`, `sae.py`, `agent/*`); the only Checkpoint A edits there are the ones a task names: B14 (`outcome_of` and narrative punctuation in `sae.py`), R3 (local-date fallback in `sae.py` and `export.py`), D8 (wording and citation fixes in `data/`) and V9 (`agent/variants.json` `llm` and `sync_agent.py --snapshot`; `prompt.md` and `tools.json` unchanged). First it is made correct, packaged and deployed (Checkpoint A). Then a sponsor-side, pre-registered statistical layer is added: for each site it compares the site's own AE log with what that site's patients reported to the agent, adjusted for symptom mix, with drill-down to verbatim quotes, a CRA-approved templated site query, a mock site inbox, a blind run, an equity panel and an honest "what it gets wrong".

| What | Where |
|---|---|
| Product requirements | `docs/10-site-signal.md` |
| Statistical analysis plan (frozen by the `sap-v1` tag) | `docs/11-site-signal-sap.md` |
| Interfaces (contracts first) | `docs/03-api-contracts.md` §5 (Site Signal) and §6 (readiness changes) |
| Tasks and acceptance checks | `docs/workstreams/WS0-readiness.md`, `WS5-site-signal.md`, and the new task sections in `WS1`–`WS4` |
| Planned requirements REQ-016..031 | `docs/07-eval-and-validation.md` §6 (added to `validation/requirements.yaml` only together with their passing tests) |
| Page layouts and components for the new and changed pages | `docs/06-frontend.md` § Site Signal pages |
| Demo script, video storyboard, deck outline | `docs/08-demo-and-pitch.md` |
| Kickoff prompt for the implementing session | `docs/KICKOFF.md` |
| Background (optional reading) | `docs/decisions/ADR-001-site-signal.md` (why this direction), `docs/research/site-signal-methods.md` (methods and verification status of cited figures), `docs/research/synthea.md` (roster options), `docs/backlog.md` (not-built items; source for the GitHub issues in R11) |

Facts at plan time:

- A real ElevenLabs browser call already works (confirmed by the team lead). Voice work in this plan is re-verification against the deployed backend, pinning and documenting the agent LLM, and recording the hero call.
- The GitHub repository stays **private**. The secret scan runs anyway. Changing visibility is a later human decision, not a step in this plan.
- The plan is implemented by one Claude Code session running parallel agents, started from `docs/KICKOFF.md`. Humans do the actions in [Human actions](#human-actions).

### Checkpoints

**No deadlines (team lead decision, Sun ~1:30 AM).** The clock times in this plan (here, in `docs/11`, the WS files and `docs/backlog.md`) are no longer binding: checkpoints SAP → A → B → C → P are an order of work, not a schedule. Time-based cut rules, time boxes and "if not done by HH:MM" fallbacks do not apply; build every task, including optional ones. Where a step waits on a human, do everything around it, record the remaining step in `HUMAN_TODO.md` and continue.

Every checkpoint leaves a shippable product on `main` (or on the session's working branch, merged to `main` with a merge commit, never squashed or rebased once `sap-v1` exists). Nothing new merges until `make test` is green.

| ID | Target (ET) | Tasks | What ships |
|---|---|---|---|
| **SAP** | Sun 02:45 | D11, S1 (B16 may start, `docs/11` §1.2) | No product change. The pre-registration exists before any evaluation output. |
| **A** | Sun 03:30 | R1–R9, V9–V11, B12–B15, F10, D8–D10 | Today's product, correct, packaged and deployed. |
| **B** | Sun 06:15 | S2–S9, B16, B16b, B17–B20, F11–F16, R10, D12 | A plus Site Signal end to end. |
| **C** | Sun 07:30 (code freeze) | B21, F17–F19, D13, R11, S10 (optional) | B plus equity panel, timeliness badge, polish, honest limits. |
| **P** (packaging) | Sun 07:30–09:30 | V12, D14–D16, R12 | Hero call, video, deck, final README, Devpost. |

#### Definitions of done

**SAP (Sun 02:45).**
- The SAP commit is pushed to `origin/main`, and the annotated tag `sap-v1` is created on that exact commit and pushed. The commit contains `docs/11-site-signal-sap.md` (design and gross planted capture loss *f* filled in from the planning grid, or the §11.5 fallback), `monitoring/params.yaml` (with `frozen_inputs`), `monitoring/uv.lock`, `data/signal_rules.json`, `data/site_queries.json`, `monitoring/planning/plan_power.py` and `monitoring/planning/planning_grid.json`.
- No file under `monitoring/out/` or `validation/site_signal/` exists at that commit: `git ls-tree -r sap-v1 --name-only | grep -E '^(monitoring/out|validation/site_signal)/'` prints nothing.
- The tag sha is published outside the team's control (GitHub Release on the tag, and the Devpost draft or organizer channel) within 10 minutes of the push.
- After the beacon round (`docs/11` §1.3), `monitoring/seed_beacon.json` is committed and `uv run --project monitoring python -m bvsignal.seed --show` prints the tag sha, the beacon round and the derived evaluation seed.

**A (Sun 03:30).**
- `make test` green, including new REQ-016..020.
- Secret scan clean (`make secret-scan`, `validation/secret-scan.md`); repo stays private.
- `.python-version` and `npm ci`: a fresh clone leaves `git status --porcelain` empty after `make setup`.
- Timezone fix with the frozen 23:30 ET test; default-secret refusal at startup; `/api/demo/*` only when `DEMO_MODE=1`; 403 `wrong_role`; audit hash chain plus `GET /api/audit/verify`; CSV/AEOUT fix with `validation/capa.md`.
- Spanish "del" fix and brand-name leaks removed from `data/` and `scenarios/`.
- Agent LLM pinned and documented, with `agent/deployed_snapshot.json` and the CI hash check.
- Production Dockerfiles; `render.yaml` with the public DEMO_MODE pair live and the private live API up. Replay → review → SAE → sponsor works in an incognito window on the public URL.
- 3 real browser calls against the deployed live backend paged ntfy and are logged in `eval/results/voice_checks.json` (hard box 03:30; fallback in [Cut rules](#cut-rules)).
- Report card shows Clopper-Pearson 95% intervals; `SECURITY.md` and `docs/privacy-security.md`; README reviewer path (3-minute walkthrough on the demo URL); traceability regenerated at HEAD.

**B (Sun 06:15).**
- `make site-signal` regenerates the committed outputs deterministically in < 60 s from the `sap-v1`-derived seed.
- Full `validate.py` run committed: power at both tiers for all three indicators, null false-flag rate with Monte Carlo SE, failure case, sensitivity, simaerep fixture result.
- `/api/sites*`, the site-query flow, blind run and reveal are live; `/sites`, `/sites/[id]`, `/site-inbox`, the CRA role, funnel and badges are deployed to the public URL.
- Playwright smoke clicks from a flagged site to a closed query.
- REQ-021..030 in `validation/requirements.yaml` with passing tests; `make types`; `make validate ARGS=--check` green.

**C (Sun 07:30, code freeze).**
- Equity panel and single-language toggle (REQ-031); days-before-next-visit badge; `/sae` list page polished; phone-width and sidebar fixes.
- `WHAT_IT_GETS_WRONG.md` and `NOT_BUILT.md` with numbers only from `validation/site_signal/summary.json` and `eval/results/latest.json`; one labeled GitHub issue per `docs/backlog.md` entry plus one per cut recorded in `NOT_BUILT.md`, linked from the README Roadmap.
- Final traceability regeneration; public instance redeployed at the freeze commit.
- After 07:00: only copy and data fixes behind tests. No new endpoints or pages.

**P (Sun 07:30–09:30).**
- Hero call recorded on the production build (07:40–08:00); 3:00 video recorded and uploaded by 08:30.
- 10-slide deck exported; README final (video, deck, demo URL, results, team).
- Final clean clone from the GitHub URL (authenticated; the repo is private) passes `make setup seed test demo` plus the smoke test at 09:00.
- 5 timed table rehearsals; Devpost submitted by 09:30.

### Workstreams (this round)

| WS | Folders and files | Task file | Tasks |
|---|---|---|---|
| **WS0 Readiness** (new) | Repo-root infra: `.gitleaks.toml`, `.python-version`, `render.yaml`, `docker-compose.prod.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `.dockerignore`, `SECURITY.md`, `e2e/`, CI jobs (gitleaks, quickstart, e2e), `docs/deploy.md`, `docs/privacy-security.md`, `validation/secret-scan.md`, README pass 1; plus the backend files named in R3 and R4 | `docs/workstreams/WS0-readiness.md` | R1–R12 |
| WS1 Voice | `agent/`, `scenarios/`, `eval/results/voice_checks.json` | `docs/workstreams/WS1-voice.md` | V9–V12 |
| WS2 Backend | `backend/`, `validation/capa.md` | `docs/workstreams/WS2-backend.md` | B12–B21 |
| WS3 Frontend | `frontend/` | `docs/workstreams/WS3-frontend.md` | F10–F19 |
| WS4 Data, eval, story | `data/`, `eval/`, `validation/` (except `validation/site_signal/`), README final, deck, video, `WHAT_IT_GETS_WRONG.md`, `NOT_BUILT.md` | `docs/workstreams/WS4-data-eval-story.md` | D8–D16 |
| **WS5 Site Signal statistics** (new) | `monitoring/` (separate uv project; numpy and scipy live only here), `validation/site_signal/`, the Deviations section of `docs/11` | `docs/workstreams/WS5-site-signal.md` | S1–S10 |

**Shared files, one writer at a time:** `Makefile`, `.github/workflows/ci.yml`, `README.md`, `CLAUDE.md`, `validation/requirements.yaml`, `docs/03-api-contracts.md`, `backend/app/{main,config,models,schemas}.py`, `frontend/src/lib/api.ts`, `frontend/src/components/shell/AppShell.tsx`. Change only the lines your task names, rebase, run `make test`, push, then release the file.

**Generated files:** `make validate ARGS=--check` rewrites `validation/summary.json` and `validation/traceability.md`. Commit them only in D12 and in the checkpoint regeneration commits; after any other check, run `git restore validation/summary.json validation/traceability.md`.

### Dependency order

1. **Start immediately, in parallel** (no dependencies): D11, R1, R2, R3, R4, B12, B13, B14, D8, D9, D10. V9 starts as soon as the LLM decision is made (human, 02:10).
2. **SAP gate:** D11 → S1 (`make planning-grid` picks the design and gross *f*, time box 02:30; docs/11 filled in) → SAP commit pushed to `main` → team lead reviews the diff → annotated tag `sap-v1` on the pushed commit (02:45; cut rule at 03:15) → tag sha published externally → beacon recorded (~03:00). B16 starts after D11 and may land before the tag.
3. **Rest of A:** R5 after R2 + R4. R6 after R5 and the human Render setup. R7 and B15 after R4. R9 after R2 + R4 + B15 (until B15 lands, `REPLAY_SPEED=4`). F10 after B14 + B15 + R4. V10 after R6 (or the tunnel fallback) + V9 + R3 + R4 + D8. V11 after V10 + B15. R8 after R6, V9 and D10.
4. **Statistics core (B):** B16 after D11. B16b after D11. S2 after the tag + S1 + B16. S3 after S2. S4 after S3. S5 after S1 (parallel with S2–S4). S6 after S4 (S5 optional). S7 and S9 after S6. S8 after S4.
5. **Backend and frontend (B):** F11 after B12. B17 after B12 + B16 + B16b (develops against the B16b fixtures; its acceptance runs on the committed outputs after S6). B18 after B17 + D11. B19 after S8 + B17. B20 after B17–B19. F12 after B17 + F11. F13 after F12 + B18. F14 after B18 + F11. F15 after B19 + F12. F16 after S7 + B17. R10 after F12–F14 + B18. D12 after S6 + B20.
6. **C:** B21 after R3. F17 after S9 + B17. F18 after B21 + V11. F19 after F10–F18. D13 after S7. R11 after D13. S10 (optional) after S2.
7. **P:** V12 after the C freeze + F19. D14 after B + D13 (drafting starts 05:50). D15 after V12 + F19. R12 after all C tasks. D16 after D14, D15 and R12.

The statistics core (step 4) does not depend on deployment, so it continues if Checkpoint A slips.

### Pre-registration order (never broken)

Details in `docs/11` §1.2–§1.3.

1. Commit `docs/11-site-signal-sap.md` (design and gross *f* filled in), `monitoring/params.yaml` (with `frozen_inputs`), `monitoring/uv.lock`, `data/signal_rules.json`, `data/site_queries.json` and the planning grid on `main`, rebase onto `origin/main` and push. The team lead reviews the diff. Then create the annotated tag `sap-v1` on that exact pushed commit (`git tag -a sap-v1 origin/main`) and push it. Never tag a worktree commit that is rebased later.
2. From the tag on, `main` is never rebased or force-pushed. Commits that add evaluation outputs are made on a checkout of `main` after rebasing and are never rebased afterwards.
3. No commit before the tag contains a file under `monitoring/out/` or `validation/site_signal/`. Before the tag only the S1 files (`seed.py`, `_backend.py`, `plan_power.py`, project skeleton) and B16 (episode builder and its table tests) may be written; simulation and analysis code (`simulate`, `match`, `indicators`, `calibrate`, `run`, `validate`, `blind`) is written after the tag.
4. The tag sha is published externally within 10 minutes; the evaluation seed is derived from the tag commit and the first public beacon round 10 minutes after the tag. The dev seed (20261011) is used only for development and the pre-tag planning grid. Every evaluation-seed run is logged in `validation/site_signal/run_log.jsonl`.
5. After the tag, `params.yaml`, `data/signal_rules.json`, the `frozen_inputs` (red-flag and grading rules, `rules.py`, `episodes.py`) and the SAP text change only with an entry in docs/11 "Deviations" (commit and reason).
6. REQ-022 (`monitoring/tests/test_sap_order.py`) checks the order, the seed and the run log in CI (checkout with `fetch-depth: 0` and tags).

### Working method

- One Claude Code session runs parallel agents, one task per agent, each in its own git worktree. The lead agent rebases each finished task onto `main`, runs `make test` and pushes.
- **Contracts first.** `docs/03` §5–6 define every new endpoint, model and error. If code needs a different interface, update the doc in its own commit first and tell the team.
- **One task per commit**, message `WSn-Xn: summary` (for example `WS5-S4: calibrate + indicators`). Pull/rebase before every push; `make test` before every push.
- A requirement enters `validation/requirements.yaml` only in the commit that adds its passing test, because `make validate ARGS=--check` fails on a requirement without one.
- At each checkpoint: post each task's acceptance output, the cuts applied and the open risks in the team chat; update `CLAUDE.md` § Status.

#### Keep CLAUDE.md current

`CLAUDE.md` describes what exists. Add these lines when the named task lands, not before:

| When | Add to `CLAUDE.md` |
|---|---|
| R1 | Rule 8: "The repository is private; changing visibility is a human decision after a fresh secret scan." Move `make secret-scan` into the main Commands block. |
| R2, S1, S6 | Commands: `make setup` uses `npm ci` and syncs `monitoring/`; `make test` includes the monitoring suite. |
| R3 | Conventions (backend): dates shown or exported as days use DISPLAY_TZ local dates (`timeutil.local_date`). |
| R5 | Commands: `make up` (production images); `make demo DEMO_PROD=1` serves the production frontend build (`next build && next start`, no dev badge). |
| R4 | Commands: `/api/demo/*` exists only under `make demo` (DEMO_MODE=1). |
| B12 | Conventions (backend): roles are coordinator, investigator, sponsor, cra; wrong role returns 403 `wrong_role`. |
| B13 | Rule 7: the audit log is a hash chain (`GET /api/audit/verify`). |
| B17, S6 | Rule 5: below minimum data, below coverage or on any error a site shows grey "not computed", never green; paging never waits on statistics. Rule 6: every site flag drills down to verbatim quotes; every Site Signal view is badged SIMULATED, MEASURED or MIXED. Conventions (monitoring): numpy/scipy only in `monitoring/`; the backend reads `monitoring/out/*.json` and shells out only for the blind run; evaluation seed from `sap-v1`; no edit to `params.yaml` or `data/signal_rules.json` after the tag without a Deviations entry; every output object carries `data_origin`. |
| B18, B19 | IDs add `sq_` (SiteQuery) and `sr_` (SignalRun). Rule 2: site-query wording comes only from `data/site_queries.json`. Rule 7: a CRA approves every site query; blind-run create and reveal are audited. |
| D8 | Rule 8: drug class names are anti-PD-1 (CD3 bispecific in roadmap context only). |
| D12 | Tests: monitoring tests live in `monitoring/tests`, carry `@pytest.mark.req` and are merged into traceability. |
| S10 | Rule 9: no SNOMED codes; Synthea raw output and jar are never committed. |
| B (any) | Don't: "Don't call capture discordance under-reporting, fraud or misconduct; say 'a reason to look'." and "Don't quote a Site Signal number that is not in `validation/site_signal/summary.json`." |
| Each task with a make target | Move the target from "Planned" into the main Commands block. |

### Human actions

The implementing session asks for these and does not block on them: it continues with other tasks and applies the cut rule if a human step misses its time.

| When (ET) | Human action |
|---|---|
| Before kickoff (~Sun 01:45) | Commit and push the planning docs to `claude/vibrant-fermi-6vwzie` and merge to `main`, so a fresh clone has them. |
| Sun 02:00 | Confirm ElevenLabs key, voice IDs, `ANTHROPIC_API_KEY` and `NTFY_TOPIC` in the local `.env` (the call already works); nurse phone subscribed to `NTFY_TOPIC` and `NTFY_BACKUP_TOPIC`. Give the D8 agent the sha256 of the study drug's generic name in lower case, computed locally with `printf %s '<name>' | sha256sum`, for the product-name guard (the name is never written to a file). Confirm that the public registry ID of the example study stays as `STUDYID` in exports (default: keep; it identifies the public protocol the plan is modeled on, and every export says "synthetic data"). |
| Sun 02:10 | Decide the agent LLM pin for V9: the evaluated model (`claude-sonnet-5-5`) or the model the working call uses (then the eval is re-run on it in the background). |
| Sun 02:10 | Create or confirm the Render account, grant its GitHub app access to the private repo, approve paid always-on instances (pricing UNVERIFIED), enter live secrets (`TOOL_SHARED_SECRET`, `ELEVENLABS_*`, `ANTHROPIC_API_KEY`, `NTFY_*`, `AGENTS_LOCK_JSON`, `BV_DASHBOARD_TOKEN`) as `sync: false` env vars on `bv-live-api`. After V10's `make sync-agent ARGS="--setup-webhook"`, re-enter `ELEVENLABS_WEBHOOK_SECRET` and `AGENTS_LOCK_JSON` and redeploy. |
| Sun 02:45 | The team lead (or a teammate the team lead names) reviews the SAP diff before `sap-v1` is pushed; the agent creates and pushes the tag after the OK. Confirm the design assumptions (20 sites, 36-week window, 1.5 grade ≥ 2 episodes per patient) and the patients-per-site range chosen by SAP §11.5 rule P1 (`planning_grid.json` `.chosen`): the reviewer approves the rule, not a fixed range. |
| Sun 02:45–02:55 | Publish the `sap-v1` tag sha outside the team: a GitHub Release on the tag and a line in the Devpost draft or the organizer channel (`docs/11` §1.2 step 6). |
| Sun 03:00–03:30 | A teammate plays the patient for 3 real browser calls on the live instance; the nurse acknowledges pages on the phone; the teammate gives written consent for use of the recorded audio. |
| Sun 05:50 | Review the deck draft; pick table-demo roles (patient, nurse, CRA, who answers questions). |
| Sun 07:40–08:30 | Record the hero call and the 3:00 video on the production build; upload unlisted. |
| Sun 09:00 | A teammate who did not build the product runs the final clean clone on a second laptop. |
| Sun 09:30 | Submit Devpost with all contributors and links; decide how reviewers access the private repo. |
| After the hackathon | Decide whether to make the repository public; if so, re-run `make secret-scan` on the final history first. |

No human action is scheduled between 03:30 and 05:50, so the team can sleep then. Anything that needs a human in that window waits or follows its cut rule.

### Cut rules

**Never cut:** `CLAUDE.md` rules 1–9; the red-flag path; SAP-before-data ordering; the null false-flag rate with Monte Carlo SE; SIMULATED/MEASURED labels; the 25% and 50% capture-loss rows; `WHAT_IT_GETS_WRONG.md`; the README.

| Time | If | Then |
|---|---|---|
| 02:30 | The planning grid (S1) has not finished | Use the `docs/11` §11.5 fallback (patients per site 30–60, gross *f* 0.90), record "planning grid not run" in §11.5, and continue to the tag. |
| 03:15 | No SAP review OK from the team lead | Push the tag anyway with the §1.5 change-log line "tagged without human review"; show the diff at the next human touchpoint; review findings become §17 entries. |
| 03:15 | Neither drand nor the NIST beacon is reachable | Derive the seed with an empty beacon value and record it in docs/11 §17 (`docs/11` §1.3). |
| 03:30 | V10 has not produced 3 logged real calls | Stop voice work. Label all demo calls "recorded" or "scripted"; limit ElevenLabs claims to what `voice_checks.json` shows; the video uses the recorded replay. |
| 03:30 | The Render demo/live pair is not up | Use the tunnel for live calls and `make up` locally; keep `render.yaml` and `docs/deploy.md` marked "verified locally only"; retry the deploy at C. |
| 03:55 | Checkpoint A is not done | Start B anyway on S2–S6 and B16–B17 (no deploy dependency); open A items move to C. |
| 05:00 | simaerep classic is not fixture-green | Drop it from the UI and summary (keep the gsm-style comparator); list it in `NOT_BUILT.md`. |
| 05:25 | B is behind | Ship `/sites` and `/sites/[id]` read-only plus `validation/site_signal/report.md`; move the query flow (B18, F13 compose, F14) and the blind run (B19, F15) to `NOT_BUILT.md`. |
| any | A blind run takes > 10 s on the host | Serve precomputed seeds only and say so in the UI. |
| 05:50 | Synthea roster (S10) not done | Parametric roster only. Deck drafting starts regardless. |
| 07:00 | Equity UI not done | Equity numbers in `report.md` and the "How well it works" tab only. |
| 07:30 | Code freeze | Only copy and data fixes behind tests; no new endpoints or pages. |
| any | Phone-width polish runs short | Fix Today, check-in, `/sites`, `/sites/[id]` first; anything else is a known limit. |

Every cut is recorded in `NOT_BUILT.md` with a linked GitHub issue.

### Risk register additions

| Risk | Likelihood | Mitigation |
|---|---|---|
| Evaluation outputs committed before `sap-v1`, or SAP parameters changed after it | Medium | Tag before outputs; `git ls-tree` check in S1; REQ-022 ancestry test in CI; post-tag changes only with a Deviations entry in docs/11. |
| SAP review by a human slips past 02:45 | Medium | B16 and the S1 files continue; at 03:15 the tag is pushed without review and says so (cut rule); review findings become §17 entries. |
| The tagged commit is rewritten by a rebase, so it is not an ancestor of the outputs | Medium | Tag only the commit already pushed to `origin/main`; never rebase or force-push `main` after the tag; REQ-022 ancestry check. |
| The evaluation seed could be chosen by re-making the tag | Low | Seed includes a public beacon value published after the tag; tag sha timestamped externally; every evaluation run logged (`docs/11` §1.2–§1.3). |
| Moderate capture gaps (25%, 50%) are mostly invisible at the Watch tier | High (expected by design) | Two tiers (Look shows its expected false flags per study from `thresholds.json`, stated on screen); the 25% and 50% rows are always shown; `WHAT_IT_GETS_WRONG.md`; numbers only from `validation/site_signal/summary.json`. |
| Advantage over a plain AE-rate indicator depends on the assumed case-mix vs diligence heterogeneity | Medium | Comparators on identical data with the same calibration; the diligence-dominated failure case is computed and shown. |
| Real false-flag rate above the stated rate because the null is misspecified | Medium | Null includes patient frailty and a (1\|patient) capture effect; cluster-robust variance and additive overdispersion; false-flag rate re-estimated on fresh seeds with Monte Carlo SE, also by site size; misspecification sensitivity reported. |
| Discordance read as an accusation of the site | Medium | Wording "capture discordance, a reason to look, not a finding"; banned-phrase check on `data/site_queries.json`; no green tier; non-leading, data-completeness-only templates; CRA approval. |
| Simulated results taken as real-world evidence | Medium | SIMULATED/MEASURED badge on every view (REQ-030); retrospective validation on paired patient- and clinician-reported data named as the next step. |
| Paged episodes reach site staff and inflate capture | Medium | Paged stratum excluded from O/E and reported separately (REQ-024). |
| Full `validate.py` run is too slow | Medium | Start it in the background as soon as S6 lands; `--quick --check` in CI; any reduction in repetitions is a logged deviation. |
| Evaluated and deployed agent LLM differ | High (known today) | V9: pin, `agent/deployed_snapshot.json`, CI hash check; README model line matches the snapshot. |
| Render deploy fails, billing not approved, or cold starts | Medium | 03:30 cut rule (tunnel + `make up`); retry at C; `docs/deploy.md` documents a Cloud Run alternative. |
| Reviewers cannot open a private repository | High | Team decides access before 09:30 (see Human actions); the public DEMO_MODE URL works without repo access. |
| Timezone bug shows wrong dates in recordings (UTC date differs from ET date from 8 PM to midnight ET) | High until R3 lands | R3 in Checkpoint A, before any recording, with the frozen 23:30 ET test. |
| Parallel agents conflict on shared files | Medium | One writer per shared file; separate worktrees; one task per commit; rebase and `make test` before every push. |
| Contract drift between `docs/03` §5 and the code | Medium | Contracts first; B20 route-conformance test; `make types`. |

## History: Saturday plan (written Sat Oct 10 afternoon)

Kept as written. Superseded for the remaining hours by the section above.

### Workstreams

| WS | Owner | Folders | Task file |
|---|---|---|---|
| WS1 Voice | teammate 1 | `agent/`, `scenarios/` (recording) | `docs/workstreams/WS1-voice.md` |
| WS2 Backend | teammate 2 | `backend/`, `Makefile`, `docker-compose.yml`, `.env.example`, `.github/` | `docs/workstreams/WS2-backend.md` |
| WS3 Frontend | teammate 3 | `frontend/` | `docs/workstreams/WS3-frontend.md` |
| WS4 Data, eval, story | teammate 4 | `data/`, `eval/`, `validation/`, `README.md`, deck, video | `docs/workstreams/WS4-data-eval-story.md` |

### Milestones (gates)

| Milestone | Target | Gate (demo it to the team before moving on) |
|---|---|---|
| **M0 Skeleton** | Sat 6:30 PM | `make dev` runs backend + frontend; `make seed` loads data; Today page lists patients from the API; `make sync-agent` creates the 4 agent variants; a browser call talks to the agent; tunnel URL reaches `/api/health`. |
| **M1 First red flag** | Sat 10:00 PM | A real English phone call: the agent asks the diarrhea question, `record_answer` hits the backend, the rules produce grade 3 and an urgent escalation, the nurse's phone gets the urgent push, tapping Acknowledge turns the escalation green, and the live page shows all of it. |
| **M2 Rosa works** | Sun 1:30 AM | Spanish + extra-time call end to end with follow-ups and read-back; caregiver and request-human paths; post-call webhook → transcript, extraction, safety net, labeled translations → drafts; review queue confirm/edit/reject with audit. |
| **M3 Closed loop + proof** | Sun 4:30 AM | Investigator seriousness + SAE report + 24-hour clock + sponsor inbox; `make eval` runs all 20 personas and writes `latest.json`; report card page renders it with the equity split; validation pack + CI green; `rosa_es_urgent` replay scenario works in `DEMO_MODE=1`. |
| **M4 Freeze** | Sun 7:00 AM | No new features. Bug bash, clean-clone test on a second laptop, README complete, record the 6 voice spot checks and the hero call, screenshots. |
| **M5 Ship** | Sun 9:30 AM | Video uploaded, deck exported, Devpost submitted with track + 2 superlatives + all contributors. |

Sleep: WS1 and WS3 sleep 1:30–4:00 AM; WS2 and WS4 sleep 4:00–6:30 AM. Whoever is awake owns the open escalation of the build.

### Dependency order (what unblocks what)

1. **WS2 B1–B3** (models, seed, rules engine) unblock everything. Target 6:00 PM.
2. **WS2 B4** (tool endpoints + interview engine) unblocks WS1's first real conversation. Target 7:30 PM. Until then WS1 tests with the browser widget and a prompt-only flow.
3. **WS3** builds against fixture JSON copied from `docs/03-api-contracts.md` until the endpoints exist, then switches to the real API and runs `make types`.
4. **WS4** starts immediately: data files are already in `data/`; build the eval harness against WS2's service functions as they land; README and deck in parallel.

### Working with Claude Code

- Each teammate works in their **own clone** of the GitHub repo, with their own Claude Code session. Start by pasting the kickoff prompt from your workstream file.
- Use **plan mode** for any task touching more than two files. Read the plan, then let it implement.
- One task = one commit: `WS2-B3: rules engine + tests`. Pull and rebase before every push. Push small and often.
- Never let Claude change a contract silently. If an endpoint, schema or data file format must change: update `docs/03-api-contracts.md` (or the data schema) first, tell the team, then implement.
- Each task file lists an acceptance check. Run it and paste the output in the team chat at each milestone.
- Keep `CLAUDE.md` current when you add a command or a convention.

### Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Twilio trial accounts don't work with ElevenLabs phone calls | Very high | **Upgrade Twilio in the first hour** (decide as a team now). |
| Outbound +1 calls blocked until Twilio's Primary Compliance Profile is approved (can take days) | High | Submit the profile in the first hour. Until cleared: browser calls for testing, and the inbound fallback (patient calls the study line) for the live demo. The nurse page uses ntfy push and never depends on Twilio. |
| Gemini free tier too small for the evaluation (reported ~20 requests/day on 3.8 Flash) | High | Link billing and prepay $5 (Tier 1) in the first hour. |
| Licensed content leaks into the public repo (PRO-CTCAE wording, MedDRA codes) | Medium | Our own question wording; local-only override folder; WS4's data validator fails on known licensed strings. |
| ElevenLabs credits run out | Medium | Claim the free Creator month now. Develop with short calls, run the eval in text mode, use replay for rehearsals. |
| Venue Wi-Fi or tunnel fails during judging | Medium | Phone hotspot; `DEMO_MODE` replay; practice the switch. |
| Gemini rate limits during eval | Medium | Concurrency 2, backoff, cache transcripts; run a 10-persona subset if needed; a paid key if available. |
| LLM paraphrases approved wording | Medium | Short `say` strings, explicit verbatim rule in the prompt, the approved-wording metric, and fix prompts until ≥ 95%. |
| Spanish speech recognition mishears numbers | Medium | Read-back confirmation before recording; numbers also stored with the verbatim quote. |
| Agent talks over slow speakers | Medium | Extra-time variant with slower voice and longer turn timeout; test with P06 and P16 by voice early (M2). |
| Scope creep | High | Cut list below; freeze at 7:00 AM. |
| Merge conflicts | Medium | Folder ownership; contracts first; small commits. |

### Cut list (cut from the top when a milestone slips)

1. Protocol-to-plan (already stretch)
2. Patient timeline sparklines
3. Re-page to backup contact (keep single re-page)
4. AI-drafted SAE narrative (use a template)
5. ElevenLabs simulate mode in the eval
6. Caregiver path (keep the persona, accept a known miss)

**Never cut:** disclosure line, approved wording, red-flag paging with acknowledgment, evidence on drafts, review confirm, the report card (even partial, with honest numbers), README, video.

### Stretch list (only between M3 and M4, only if ahead)

Protocol-to-plan with Gemini; warm transfer of the patient straight to the nurse (`transfer_to_number`); mid-call language switch; deployed demo URL in demo mode; Tiger Data and .tech domain extras (ask the MLH table first whether they count against the two-superlative limit).
