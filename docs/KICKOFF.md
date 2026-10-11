# Kickoff: Site Signal build (Sun Oct 11)

Paste everything below the line into a fresh Claude Code session at the repo root. Timeline, tasks and cut rules are in `docs/09-timeline-and-workstreams.md`.

---

You are implementing the Sun Oct 11 plan for **Between Visits** (`feruzkarimovv/between-visits`, private). You start cold; the docs hold everything. Times (ET), assuming kickoff ~01:45: SAP tag 02:45, Checkpoint A 03:30, B 06:15, C 07:30 (code freeze), Devpost submission 09:30. If you start later, shift the targets by the delay, but never freeze later than 08:00 and never move the 09:30 submission; apply the cut rules against those limits (docs/09 § Checkpoints).

**Use a workflow.** Orchestrate parallel agents: one task per agent, each in its own git worktree; the lead rebases finished tasks onto `main`, runs `make test` and pushes. Keep the critical path (SAP tag → statistics core → API → pages) moving.

**1. Get the plan.** It is on branch `claude/vibrant-fermi-6vwzie` unless it has been merged to `main` (check: `git log origin/main --oneline -- docs/10-site-signal.md`). If not, ask me to merge it (or to approve your merge). Then work on `main` like the existing history. If your session can only push to its own branch, work there instead and tell me; I merge it to `main` with a merge commit (never squash or rebase once `sap-v1` exists), and the `sap-v1` tag goes on a commit of that branch that is already pushed.

**2. Read, in order:** `CLAUDE.md`; `docs/00-overview.md`; `docs/09-timeline-and-workstreams.md` (section "Sat Oct 10, late"); `docs/10-site-signal.md`; `docs/11-site-signal-sap.md`; `docs/03-api-contracts.md` §5–6; `docs/02-data-model.md`; `docs/workstreams/WS0-readiness.md`, `WS5-site-signal.md` and the new task sections in `WS1`–`WS4`; `docs/07-eval-and-validation.md` §6; `docs/06-frontend.md` (§ Site Signal pages); `docs/08-demo-and-pitch.md`. Optional background: `docs/decisions/ADR-001-site-signal.md`, `docs/research/*.md`, `docs/backlog.md` (source list for the R11 issues).

**3. Execute** (definitions of done are in docs/09):
- SAP gate (D11, S1; B16 may start), in parallel with Checkpoint A.
- Checkpoint A: R1–R9, V9–V11, B12–B15, F10, D8–D10.
- Checkpoint B: S2–S9, B16, B16b, B17–B20, F11–F16, R10, D12.
- Checkpoint C: B21, F17–F19, D13, R11, S10 (optional).
- Packaging support: V12, D14–D16, R12.

Follow the docs/09 dependency order. Apply its cut rules on time without waiting for me; record every cut in `NOT_BUILT.md`.

**4. Rules you never break**
- `CLAUDE.md` rules 1–9. Never change a grade, threshold, red-flag rule or escalation level: leave `rules.py`, `interview.py`, `escalation.py`, `postcall.py`, `agent/prompt.md`, `data/ctcae_rules.json` and the red-flag logic alone. The only edits near the safety path are the ones a task names: B14 (`outcome_of` and narrative punctuation in `sae.py`), R3 (local-date fallback in `sae.py` and `export.py`), D8 (wording and citation fixes in `data/`), V9 (`agent/variants.json` `llm` and `sync_agent.py --snapshot`; `prompt.md` and `tools.json` unchanged).
- No LLM anywhere in `monitoring/`, `episodes.py`, `site_signal.py` or `site_queries.py`.
- **Contracts first.** `docs/03` §5–6 are the interface. If code needs a change, update the doc in its own commit first and tell me.
- **One task per commit**, message `WSn-Xn: summary` (e.g. `WS5-S4: calibrate + indicators`). Pull/rebase and run `make test` before every push. Add a REQ to `validation/requirements.yaml` only in the commit that adds its passing test; CI's `make validate ARGS=--check` fails otherwise.
- **SAP ordering** (`docs/11` §1.2). Run `make planning-grid` (fallback at 02:30), fill the design and gross capture loss into docs/11 and `params.yaml`, commit the SAP files on `main`, push, show me the diff, and after my OK (or at 03:15 without it, saying so in §1.5) create the annotated tag `sap-v1` on the pushed commit and push it. Never tag a commit that will be rebased; never rebase or force-push `main` after the tag. Ask me to publish the tag sha externally, then record the beacon. Before the tag only the S1 files and B16 may be written; no commit before the tag may contain a file under `monitoring/out/` or `validation/site_signal/`. Use the dev seed (20261011) until the tag. After it, any change to `params.yaml`, `data/signal_rules.json`, the `frozen_inputs` or the SAP needs a Deviations entry in docs/11, and every evaluation-seed run is logged.
- **Wording.** Say "capture discordance" and "a reason to look, not a finding"; never call it "under-reporting", "fraud" or "misconduct". Every Site Signal number comes from `validation/site_signal/summary.json`. Label every view SIMULATED or MEASURED (MIXED only for the site 101 card and mixed queries). Name the drug by class only. No competitor content. No secrets or real phone numbers in git.
- Never change repository visibility.

**5. Ask me for these** (times in docs/09 § Human actions):
- Merge the planning docs to `main` before kickoff (~01:45).
- Confirm `.env` keys and the nurse phone; give the generic-name hash for D8; confirm the STUDYID decision (02:00).
- LLM pin decision for V9 (02:10).
- Render account, GitHub access, billing and live secrets (02:10).
- SAP diff review before the tag (02:45), then publishing the tag sha externally (02:45–02:55).
- A teammate as patient, plus the nurse acknowledging pages, for the 3 real calls, with recording consent (03:00–03:30).
- Deck review (05:50).
- Recording the hero call and the video (07:40–08:30).
- Clean clone on a second laptop (09:00).
- Devpost submission and reviewer access to the private repo (09:30).

Don't block on me: keep working, and apply the cut rule if a human step misses its time.

**6. At each checkpoint**, report each task's acceptance output, cuts applied and open risks; update `CLAUDE.md` § Status and add the lines from docs/09 "Keep CLAUDE.md current" as their tasks land.

**Done looks like:**
- `make test` green; `make validate ARGS=--check` passes REQ-001..031 (or the REQs of any cut feature are listed in `NOT_BUILT.md`); `make secret-scan` clean.
- On the public DEMO_MODE URL: replay → review → SAE → sponsor, and /sites → flagged site → query approved → answered → closed.
- `eval/results/voice_checks.json` holds 3 MEASURED real calls, or the 03:30 fallback is applied and labeled.
- `sap-v1` precedes every evaluation output; `WHAT_IT_GETS_WRONG.md`, `NOT_BUILT.md`, README and deck agree with `summary.json`.
- The freeze commit is deployed.
