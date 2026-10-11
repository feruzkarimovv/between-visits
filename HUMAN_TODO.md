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

5. **Optional: make `make up` (R5 production images) run from this laptop's docker CLI.** The host `docker` has no working `compose` or `buildx` plugin: `~/.docker/cli-plugins/docker-compose` and `docker-buildx` are symlinks into `/Applications/Docker.app`, which is not installed (colima is the engine). Install Compose and point both symlinks at the Homebrew binaries (`docker-buildx` is already installed by Homebrew):
   ```bash
   brew install docker-compose
   ln -sfn /opt/homebrew/opt/docker-compose/bin/docker-compose ~/.docker/cli-plugins/docker-compose
   ln -sfn /opt/homebrew/opt/docker-buildx/bin/docker-buildx ~/.docker/cli-plugins/docker-buildx
   docker compose version && docker buildx version     # both print a version
   cd ~/hackru/between-visits && git checkout site-signal-build && git pull --ff-only
   make up                                             # foreground; API :8000, dashboard :3000 (API_PORT/WEB_PORT to change)
   # in another terminal:
   curl -fsS localhost:8000/api/health | jq -e '.ok and .demo_mode'   # expect: true
   curl -fsS localhost:3000 | grep -q 'Between Visits' && echo web-ok  # expect: web-ok
   # Ctrl-C, then:
   docker compose -f docker-compose.prod.yml down
   ```
   Without this, the same stack runs through the compose inside the colima VM: `colima ssh -- env GIT_COMMIT=$(git rev-parse --short HEAD) docker compose --project-directory "$PWD" -f "$PWD/docker-compose.prod.yml" up --build -d` (stop with the same command and `down`).

6. **Freeze the SAP: review, tag `sap-v1`, publish the timestamp, fetch the beacon (S1; docs/11 §1.2 steps 4-7).** S1 is integrated on `site-signal-build`: §11.5 filled (patients per site 40-80 and gross *f* 0.90, both "shortfall" from the planning grid), `monitoring/params.yaml` frozen-input hashes written, §17 empty. Nothing below can be undone once the tag is pushed (the tag is never moved or deleted), so do the steps in order:
   1. Review the SAP diff (`git diff 607d213..origin/site-signal-build -- docs/11-site-signal-sap.md monitoring/params.yaml`). If the review OK has not arrived by 03:15, tag anyway and write "tagged without human review" in the change-log line.
   2. Fill the docs/11 §1.5 change-log row for `sap-v1` (replace "at the tag" with today's date, and keep either "reviewed by the team lead" or "tagged without human review", whichever applies), then commit and push it:
      ```bash
      cd ~/hackru/between-visits && git checkout site-signal-build && git pull --ff-only
      # edit docs/11-site-signal-sap.md §1.5, then:
      git commit -am "SAP v1: change log" && git push origin site-signal-build
      uv run --project monitoring python -m bvsignal.seed --check-frozen          # expect: frozen inputs: OK
      git ls-tree -r origin/site-signal-build --name-only | grep -E '^(monitoring/out|validation/site_signal)/'   # must print nothing
      ```
   3. Tag exactly that pushed commit and push the tag:
      ```bash
      git fetch origin && git tag -a sap-v1 origin/site-signal-build -m 'Site Signal SAP v1'
      git push origin sap-v1
      git rev-parse 'sap-v1^{commit}'      # the tag sha to publish
      ```
   4. Within 10 minutes of the push, publish the tag sha outside the team's control: on GitHub, Releases > Draft a new release > choose tag `sap-v1` > title "Site Signal SAP v1" > Publish release (or `gh release create sap-v1 --title "Site Signal SAP v1" --notes "sap-v1 = <tag sha>"`), and post the sha in the Devpost draft or the event's organizer channel. Keep both links for the §17 row.
   5. After the beacon round (the first drand round at least 10 minutes after the tagger time), fetch it and record the seed:
      ```bash
      uv run --project monitoring python -m bvsignal.seed --fetch-beacon --wait   # writes monitoring/seed_beacon.json; never overwrites an existing one
      uv run --project monitoring python -m bvsignal.seed --show                  # tag sha, beacon round, evaluation seed
      ```
   6. Add a docs/11 §17 clarification row (Release link, Devpost/organizer link, beacon round; say so if the external timestamp is not earlier than the beacon round) and commit it with the beacon file:
      ```bash
      git add monitoring/seed_beacon.json docs/11-site-signal-sap.md
      git commit -m "SAP v1: beacon round and external timestamp (docs/11 §17)" && git push origin site-signal-build
      ```
   Only after this may S6/S7/S8 produce evaluation output (`monitoring/out/`, `validation/site_signal/`).
