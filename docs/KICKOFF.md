# Kickoff: Site Signal build (autonomous, no deadlines)

Paste everything below the line into a fresh Claude Code session on this repository. Tasks, order and acceptance checks are in `docs/09-timeline-and-workstreams.md` and the workstream files.

---

You are implementing the Site Signal plan for **Between Visits** (`feruzkarimovv/between-visits`, a private repo). You start cold, and the docs hold the whole plan. **The team lead is asleep and will not answer.** Work autonomously until every task is done and verified. Never stop to ask a question or wait for approval. When a step truly needs a human (accounts, API keys, real phone calls, recording, merging to `main`, Devpost), finish everything around it, write the exact remaining steps in `HUMAN_TODO.md`, and keep going.

**No deadlines.** Ignore every clock time, target time, time box and time-based cut rule in the docs (`docs/09`, `docs/11`, the WS files, `docs/backlog.md`). Checkpoints SAP → A → B → C → P are an order of work, not a schedule. Do not cut scope: build every task, including the optional ones (S10). Wherever the docs give a time-based fallback, take the full path instead: run the full planning grid, and tag `sap-v1` after your own review.

**Use workflows.** Orchestrate parallel agents: one task per agent, each in its own git worktree. A lead merges finished tasks, runs `make test` and pushes. Keep the critical path moving (SAP tag → statistics core → API → pages), and verify each task's acceptance check before you mark it done.

**1. Branch.** Work on the branch this session was given, or create `site-signal-build` if you have none. The plan is on `origin/claude/vibrant-fermi-6vwzie`. Merge it into your branch first, unless `git log origin/main --oneline -- docs/10-site-signal.md` shows it already on `main`. Push after every task.
- Never push to `main`, never force-push, and never rebase once `sap-v1` exists. Put the `sap-v1` tag on a commit that is already pushed.
- Add a first item to `HUMAN_TODO.md`: "merge `<branch>` into `main` with a merge commit (not squash or rebase)."
- Where the docs say "on `main`", read it as your branch.

**2. Read, in order:**
1. `CLAUDE.md`
2. `docs/00-overview.md`
3. `docs/09-timeline-and-workstreams.md` (section "Sat Oct 10, late")
4. `docs/10-site-signal.md`
5. `docs/11-site-signal-sap.md`
6. `docs/03-api-contracts.md` §5–6
7. `docs/02-data-model.md`
8. `docs/workstreams/WS0-readiness.md` and `WS5-site-signal.md`, plus the new task sections in `WS1`–`WS4`
9. `docs/07-eval-and-validation.md` §6
10. `docs/06-frontend.md` (§ Site Signal pages)
11. `docs/08-demo-and-pitch.md`

Background: `docs/decisions/ADR-001-site-signal.md`, `docs/research/*.md`, `docs/backlog.md`.

**3. Execute, in this order** (each task's acceptance check must pass):

| Step | Tasks |
|---|---|
| SAP gate | D11, S1 (B16 may start), run in parallel with Checkpoint A |
| A | R1–R9, V9, V11, B12–B15, F10, D8–D10 |
| B | S2–S9, B16, B16b, B17–B20, F11–F16, R10, D12 |
| C | B21, F17–F19, D13, R11, S10 |
| P | D14–D16 and R12; V10 and V12 as far as they go without a human (below) |

**4. Steps that would normally wait on the team lead** (decide, record the decision in the task commit, continue):
- **V9 (LLM pin):** take the default in WS1 V9. If the live sync can't be run here, make the offline parts pass and add "run `make sync-agent` and `--snapshot` locally" to `HUMAN_TODO.md`.
- **D8 (product-name hash):** compute it yourself from the study's anti-PD-1 generic name (public registry entry NCT02760498). Never write the name in any file, commit message or log. STUDYID: use the default recorded in the docs.
- **SAP review:** have a separate reviewer agent with a statistician's lens review the SAP diff. Fix what it finds, then tag. Record "reviewed by agent; team lead review pending" in `docs/11` §1.5.
- **External timestamp and beacon:** create a GitHub Release for `sap-v1` if your tools allow, otherwise add it to `HUMAN_TODO.md`. Fetch the beacon with `bvsignal.seed --fetch-beacon --wait`; the NIST and empty-`B` fallbacks apply only after the deadlines of docs/11 §1.3 (round time + 30 and + 60 min), and the §17 row cites the attempts recorded in `seed_beacon.json`.
- **R6 (deploy):** write and locally verify the Dockerfiles, `render.yaml` and `docs/deploy.md` (build and run the images if Docker is available). The actual Render deploy and its secrets go in `HUMAN_TODO.md`.
- **V10 and V12 (real calls, hero call):** you can't make real calls. Prepare the scripts, checklist and `voice_checks.json` structure, with rows marked pending. Keep every voice claim limited to what's verified, label replays "scripted" or "recorded", and put the call steps in `HUMAN_TODO.md`.
- **R11 (issues):** create the issues from `docs/backlog.md` if your GitHub tools allow, otherwise leave a ready list.
- **Deck and video:** write the deck (D14) and the final storyboard. Recording and the Devpost submission go in `HUMAN_TODO.md`.
- **R12 (final clean clone):** do it yourself from a fresh clone of your pushed branch.

**5. Rules you never break**
- `CLAUDE.md` rules 1–9.
- Never change a grade, threshold, red-flag rule or escalation level. Leave `rules.py`, `interview.py`, `escalation.py`, `postcall.py`, `agent/prompt.md`, `data/ctcae_rules.json` and the red-flag logic alone. The only edits near the safety path are the ones a task names: B14, R3, D8 and V9.
- No LLM anywhere in `monitoring/`, `episodes.py`, `site_signal.py` or `site_queries.py`.
- **Contracts first.** If code needs an interface change, update `docs/03` in its own commit first.
- **One task per commit**, with the message `WSn-Xn: summary`. Run `make test` before every push.
- Add a REQ to `validation/requirements.yaml` only in the commit that adds its passing test.
- **SAP ordering** (`docs/11` §1.2):
  - Before the tag, only the S1 files and B16 may be written, and no commit may contain anything under `monitoring/out/` or `validation/site_signal/`.
  - Use the dev seed until the tag.
  - After the tag, any change to the frozen inputs needs a Deviations entry, and every evaluation run is logged.
- **Wording:** say "capture discordance" and "a reason to look, not a finding". Every Site Signal number comes from `validation/site_signal/summary.json`, and every view is labeled SIMULATED or MEASURED. Name the drug by class only. No competitor content. No secrets or real phone numbers in git.
- Never change repository visibility.

**6. Keep going until it is fully done**
- Keep `PROGRESS.md` at the repo root: one row per task with status, commit, a summary of the acceptance output, and any blocker. Update it and push it after every task.
- If your context is reset or compacted, re-read `PROGRESS.md` and `HUMAN_TODO.md` and continue where you left off.
- Do not end while any task that doesn't need a human remains.
- When every task is done, run a final verification round:
  - **Fresh clone** of your pushed branch: `make setup seed test`, `make validate ARGS=--check` (REQ-001..031), `make secret-scan`, `make site-signal` twice with identical outputs, the Playwright smoke test, and the demo walkthrough with screenshots (replay → review → SAE → sponsor, and `/sites` → flagged site → query approved → answered → closed).
  - **Adversarial review** of the full diff against the `CLAUDE.md` rules, the contracts and the SAP.
  - Fix everything found and repeat until a round comes back clean.
- **Finish** by putting a final report at the top of `PROGRESS.md`: what was built, the verification results, and the known limits (with `WHAT_IT_GETS_WRONG.md` and `NOT_BUILT.md` consistent with `summary.json`). Order `HUMAN_TODO.md` by priority, each item with exact commands or clicks.
