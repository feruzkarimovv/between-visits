# HUMAN_TODO

Steps that need a person. Everything around them is done; each item says exactly what to run or click. Ordered by priority (re-ordered at the end of the build).

1. **Merge `site-signal-build` into `main` with a merge commit (not squash or rebase).** The `sap-v1` tag must stay an ancestor of the evaluation outputs (REQ-022), so the branch history must be kept as is:
   ```bash
   git fetch origin
   git checkout main && git pull --ff-only
   git merge --no-ff origin/site-signal-build -m "Merge site-signal-build: Site Signal + readiness"
   make test && git push origin main
   ```
   Or on GitHub: open a pull request from `site-signal-build` to `main` and use **Create a merge commit** (not "Squash and merge", not "Rebase and merge").

2. **Set a real `TOOL_SHARED_SECRET` on every machine or deploy that runs with `DEMO_MODE=0` (R4).** Outside demo mode the backend now refuses to start (exit 1, one-line message) when `TOOL_SHARED_SECRET` is empty, still `change-me-long-random-string`, or shorter than 24 characters. The main checkout's `.env` already passes. On any other machine (or a fresh `cp .env.example .env`):
   ```bash
   python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
   # paste the output into .env as TOOL_SHARED_SECRET=<value>, then:
   make dev
   ```
   If the value changes, push it to the ElevenLabs workspace secret too, so the agent's tools keep authenticating:
   ```bash
   make sync-agent
   ```
   `make demo` (`DEMO_MODE=1`) starts with any secret and needs none of this.

3. **Record the deployed agent config so CI goes green (V9).** CI's step "Deployed agent config matches git" (`python3 agent/check_config_hash.py`) fails until `agent/deployed_snapshot.json` is committed. The two Spanish agents were deployed before D8's wording fix, so sync first, then snapshot. In the main checkout (`.env` with `ELEVENLABS_API_KEY`):
   ```bash
   git checkout site-signal-build && git pull --ff-only
   make sync-agent                          # pushes the D8 Spanish wording to es-standard and es-extra_time
   make sync-agent ARGS=--snapshot          # read-only (GET only): writes agent/deployed_snapshot.json
   jq -r '[.variants[].llm]|unique|.[]' agent/deployed_snapshot.json   # expect: claude-sonnet-5-5
   python3 agent/check_config_hash.py; echo exit=$?                     # expect: OK ... and exit=0
   git add agent/deployed_snapshot.json
   git commit -m "WS1-V9: deployed snapshot"
   git push origin site-signal-build
   ```
   From now on, any edit to `agent/prompt.md`, `agent/tools.json`, `agent/agent.template.json`, `agent/variants.json` or the agent-facing files in `data/` (scripts, red flags, plan, study) needs the same `make sync-agent` → `make sync-agent ARGS=--snapshot` → commit of the new snapshot, or CI fails.

4. **Reseed every SQLite database built before B13 (audit hash chain).** `AuditEvent` gained `seq`, `prev_hash` and `hash` columns and there is no migration (docs/02). Until an old database is reseeded, each audit row is dropped (the hook logs `audit_chain_failed`; the caller's own write still commits) and `GET /api/audit` returns 500. Reseeding deletes the local demo data in that database. In each checkout or deploy that has a database:
   ```bash
   git checkout site-signal-build && git pull --ff-only
   make seed                                  # or: make demo (reseeds with DEMO_MODE=1, then starts backend + frontend)
   # with the backend running on :8000:
   curl -s localhost:8000/api/audit/verify    # expect {"ok":true,...}
   ```
   For a deployed instance, run the same seed command in its shell (`cd backend && uv run python -m app.seed`, with `DEMO_MODE=1` for a demo deploy) and restart the service.
