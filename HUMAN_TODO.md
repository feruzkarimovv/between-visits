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
