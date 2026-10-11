# Deploy

**Status: verified locally only (Sun Oct 11, 2026).** Nothing is deployed to Render yet. `render.yaml` parses, and each of its keys was checked against Render's published Blueprint schema (`render.com/schema/render.yaml.json`). The backend image ran locally in both the live-API and the demo-API configuration (§8). The Render account, the GitHub app access to the private repository, billing and the live secrets need a person (§3). Until the live instance is up, live calls use the tunnel (§7).

**UNVERIFIED** marks a statement we have not checked on a real Render (or Cloud Run) deploy.

## 1. What runs where

One Blueprint (`render.yaml`) defines three Docker web services. All of them build from the repository root as the build context and deploy on every push to `main`.

| Service | Image | Mode | Who uses it |
|---|---|---|---|
| `bv-demo-api` | `backend/Dockerfile` | `DEMO_MODE=1`: replay scenarios only, no external keys, console pager | the public demo dashboard |
| `bv-demo-web` | `frontend/Dockerfile` | production Next.js build (no dev badge), calls `bv-demo-api` | reviewers, the 3-minute reviewer path, the video |
| `bv-live-api` | `backend/Dockerfile` | `DEMO_MODE=0`, `APP_ENV=prod`: real ElevenLabs browser calls, Anthropic post-call pipeline, ntfy pages. Every `/api/*` request except `GET /api/health` needs `X-BV-Token` (`docs/03` §6.8). | ElevenLabs (agent tools, post-call webhook), the nurse's ntfy **Acknowledge** button, and a dashboard that runs **locally** on `http://localhost:3000` |

Shared settings:
- `plan: starter`, always on (the free plan sleeps when idle, which would stop the re-page loop). Pricing UNVERIFIED.
- `numInstances: 1`, `region: virginia` (Render cannot change the region after creation).
- `healthCheckPath: /api/health` for the APIs, `/` for the dashboard.
- `autoDeploy: true` from branch `main`, plus `autoDeployTrigger: commit`, the newer field with the same meaning. Merging to `main` is how each checkpoint reaches the public URL.
- **No build filters.** Every push to `main` rebuilds all three services, so the `commit` field of `/api/health` (read from `RENDER_GIT_COMMIT`, R5) always equals the head of `main`.

**Images contain no local secrets.** The root `.dockerignore` keeps `.env`, `data/patients.local.json`, `data/local/`, `agent/agents.lock.json` and `eval/results/*.local*` out of the build context (R5). The live secrets exist only as environment variables on `bv-live-api`, entered by a person in Render's dashboard.

## 2. Environment variables per service

Every variable is read by `backend/app/config.py` (`docs/03` §6.9). Render passes a service's environment variables to the Docker build as build arguments, so `NEXT_PUBLIC_API_BASE_URL` reaches `next build` and is inlined into the dashboard bundle.

Service URLs are not hard-coded. `fromService ... envVarKey: RENDER_EXTERNAL_URL` copies a service's own `https://<name>.onrender.com` URL. Render adds a suffix to that URL when the name is already taken. Render's own tutorial uses this pattern for a service's own URL. Using it to copy *another* service's URL, and having that value at Docker build time, is UNVERIFIED. Check both after the first deploy (§3, step 6).

### `bv-demo-api`

| Variable | Value | Set by |
|---|---|---|
| `DEMO_MODE` | `1` | `render.yaml` |
| `APP_ENV` | `demo` | `render.yaml` |
| `CORS_ORIGINS` | the `bv-demo-web` URL | `render.yaml` (`fromService`) |
| `PUBLIC_BASE_URL` | its own URL | `render.yaml` (`fromService`) |
| `TOOL_SHARED_SECRET` | random 256-bit value that nobody knows (nothing calls the demo API's agent tools) | Render (`generateValue: true`) |
| `PORT`, `RENDER_GIT_COMMIT`, `RENDER_EXTERNAL_URL` | set by Render. `PORT` defaults to 10000 and the image listens on `$PORT`. If Render does not set it, Render detects the image's default port 8000 (UNVERIFIED). | Render |

Not set: API keys, ntfy topics, `AGENTS_LOCK_JSON` (demo mode makes no external calls), and `BV_DASHBOARD_TOKEN` (the demo is public). `REPLAY_SPEED` is optional; unset means 2× in demo mode.

### `bv-demo-web`

| Variable | Value | Set by |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | the `bv-demo-api` URL. It is a build argument, inlined by `next build`, so a change needs a rebuild. | `render.yaml` (`fromService`) |
| `PORT` | set by Render; the standalone server listens on `$PORT` | Render |

Never set `NEXT_PUBLIC_BV_DASHBOARD_TOKEN` on a hosted dashboard: every `NEXT_PUBLIC_` value is readable in the browser bundle.

### `bv-live-api`

| Variable | Value | Set by |
|---|---|---|
| `DEMO_MODE` | `0` | `render.yaml` |
| `APP_ENV` | `prod` | `render.yaml` |
| `PUBLIC_BASE_URL` | its own URL. Agent tools, the post-call webhook, ntfy ack links and Twilio signatures use it. | `render.yaml` (`fromService`) |
| `CORS_ORIGINS` | `http://localhost:3000` (the dashboard for live calls runs locally, WS1 V10) | `render.yaml` |
| `TOOL_SHARED_SECRET` | **the same value as the local `.env`.** `make sync-agent` stores it in the ElevenLabs workspace secret `bv_tool_secret`, which every agent tool sends as `X-BV-Tool-Secret`. With a different value, every tool call returns 401. The backend refuses to start with an empty, placeholder or < 24-character value (`docs/03` §6.3). | person (`sync: false`) |
| `BV_DASHBOARD_TOKEN` | a new random value (§5) | person (`sync: false`) |
| `ELEVENLABS_API_KEY` | from the local `.env` | person (`sync: false`) |
| `ELEVENLABS_WEBHOOK_SECRET` | from the local `.env` (printed once by `make sync-agent ARGS="--setup-webhook"` when the webhook is created) | person (`sync: false`) |
| `AGENTS_LOCK_JSON` | `agent/agents.lock.json` on one line (§4) | person (`sync: false`) |
| `ANTHROPIC_API_KEY` | from the local `.env`. Without it, `LLM_PROVIDER=auto` falls back to Gemini, then to the deterministic fake. | person (`sync: false`) |
| `NTFY_TOPIC`, `NTFY_BACKUP_TOPIC` | from the local `.env`; the nurse's phone is subscribed to both | person (`sync: false`) |
| `PORT`, `RENDER_GIT_COMMIT`, `RENDER_EXTERNAL_URL` | set by Render | Render |

Optional extras, added by hand under **Environment** only if needed: `ELEVENLABS_PHONE_NUMBER_ID` (phone calls, which are not connected for the hackathon), `PAGER_CHANNEL` (default `ntfy`), `NTFY_SERVER`, `ONCALL_NURSE_NAME`, `BACKUP_INVESTIGATOR_NAME`, `DISPLAY_TZ` (default `America/New_York`), `ACK_TIMEOUT_SECONDS` (default 90), `LLM_PROVIDER`, `CLAUDE_MODEL_FAST`, `CLAUDE_MODEL_LONG`. `ELEVENLABS_LLM` defaults to the evaluated model (V9). The voice IDs are used only by `make sync-agent` on a laptop, not by the host. Whether a Blueprint sync keeps variables that were added in the dashboard but are missing from `render.yaml` is UNVERIFIED; check after the next sync.

Render asks for `sync: false` values **only when the Blueprint is first created**. Later syncs ignore them, so change them under the service's **Environment** tab.

## 3. Render steps (a person does these)

Dashboard labels were current as of Oct 2026 and may have moved (UNVERIFIED).

1. **`render.yaml` must be on `main`.** The Blueprint and every auto-deploy read `main`. Merge `site-signal-build` into `main` first (`HUMAN_TODO.md` item 1).
2. **Account and billing.** Sign in at `dashboard.render.com` with GitHub. Under **Workspace Settings → Billing**, add a payment method; the `starter` plan is paid. Approve the spend for three always-on instances (pricing UNVERIFIED).
3. **GitHub access to the private repository.** Go to **New → Blueprint → Connect a repository**. Render opens GitHub's app install page. Choose the account that owns `feruzkarimovv/between-visits`, then **Only select repositories**, add `between-visits`, and click **Install** (or **Save**). Later changes are under GitHub **Settings → Applications → Render → Configure**.
4. **Create the Blueprint.** Select `between-visits`. Blueprint name: `between-visits`; branch: `main`; Blueprint path: `render.yaml`. Render lists the three services and asks for each `sync: false` value of `bv-live-api`. Paste them as described in §2, §4 and §5; never type them into a file in the repository. Click **Deploy Blueprint** (or **Apply**).
5. **Wait for three green deploys.** Each API seeds its database on first start. Read the URLs from each service's page (top left, `https://….onrender.com`).
6. **Check the cross-service values.** On `bv-demo-api → Environment`, `CORS_ORIGINS` must equal the `bv-demo-web` URL. On `bv-demo-web → Environment`, `NEXT_PUBLIC_API_BASE_URL` must equal the `bv-demo-api` URL. On `bv-live-api`, `PUBLIC_BASE_URL` must equal its own URL. If one is empty or wrong, set the URL by hand. For `bv-demo-web`, then use **Manual Deploy → Clear build cache & deploy**, because the URL is inlined at build time. To keep that fix through later syncs, replace the `fromService` entry in `render.yaml` with `value: https://…onrender.com` and merge.
7. **Acceptance** (R6). On a laptop, with `main` checked out at the deployed commit:
   ```bash
   DEMO_API=https://bv-demo-api.onrender.com   # the real URLs from step 5
   DEMO_WEB=https://bv-demo-web.onrender.com
   LIVE_API=https://bv-live-api.onrender.com
   curl -fsS $DEMO_API/api/health | jq -e '.demo_mode==true and .commit=="'$(git rev-parse --short HEAD)'"'
   curl -fsS $LIVE_API/api/health | jq -e '.demo_mode==false and .browser_calls_enabled'
   curl -s -o /dev/null -w '%{http_code}\n' $LIVE_API/api/patients     # 401 (no X-BV-Token)
   ```
   The first two print `true` and the third prints `401`. Then, in an incognito window on `$DEMO_WEB`: Today → Replay scenario → review and confirm the drafts → switch the role to Investigator → assessment → SAE sign → send → the report appears in the sponsor inbox. `browser_calls_enabled` is `false` until `ELEVENLABS_API_KEY` and a 4-variant `AGENTS_LOCK_JSON` are set; `browser_calls_note` says which one is missing.
8. When everything works, change the README line "**Live demo:** not deployed yet" to the `bv-demo-web` URL, and remove "verified locally only" from the top of this page.

## 4. Point the voice agents at `bv-live-api` (`PUBLIC_BASE_URL`, webhook, `AGENTS_LOCK_JSON`)

The ElevenLabs agent tools and the post-call webhook are workspace-wide, so they point at one backend at a time. On a laptop with the full `.env` (the same `TOOL_SHARED_SECRET` as `bv-live-api`):

```bash
PUBLIC_BASE_URL=$LIVE_API make sync-agent ARGS="--setup-webhook"
```

- The variable on the command line overrides `.env`. Tools now call `$LIVE_API/agent/tools/*`, and the post-call webhook targets `$LIVE_API/webhooks/elevenlabs/post-call`.
- If the script warns that the existing webhook points at an old tunnel URL, change the URL in the ElevenLabs dashboard (workspace **Settings → Webhooks**). The signing secret then stays the same. If you delete the webhook and rerun, the script prints a new `ELEVENLABS_WEBHOOK_SECRET`. Put that value in the local `.env` and on `bv-live-api`.
- Agents are upserted by name, so `agent/agents.lock.json` usually keeps the same IDs. If they change, update `AGENTS_LOCK_JSON`.

**Copy the lock file into `AGENTS_LOCK_JSON`** without printing it:

```bash
python3 -c 'import json; print(json.dumps(json.load(open("agent/agents.lock.json")), separators=(",", ":")))' | pbcopy
```

Paste the clipboard into `bv-live-api → Environment → AGENTS_LOCK_JSON` and choose **Save, rebuild, and deploy** (or **Save and deploy**). The backend reads `agent/agents.lock.json` when the file exists and `AGENTS_LOCK_JSON` otherwise (`backend/app/services/elevenlabs.py`). `make sync-agent ARGS=--snapshot` uses the same fallback. A value that is not a JSON object counts as "not synced": calls stay off, the dashboard shows the reason, and the value is never logged.

After a re-sync with `--setup-webhook`, re-enter `ELEVENLABS_WEBHOOK_SECRET` (only if it changed) and `AGENTS_LOCK_JSON`, then redeploy (`docs/09` § Human actions).

**Back to the tunnel:** run `make tunnel`, then `make sync-agent` with the tunnel URL in `.env` as `PUBLIC_BASE_URL`, and fix the webhook URL as above.

## 5. Dashboard token and the local dashboard for live calls

`BV_DASHBOARD_TOKEN` (`docs/03` §6.8) is set **only on `bv-live-api`**. When it is set, every `/api/*` request except `GET /api/health` (Render's health check) needs `X-BV-Token` with that value; otherwise the API returns 401 `invalid_token`. `/agent/tools/*` and `/webhooks/*` are not affected: they keep the tool secret, the HMAC signature and the ack tokens. The token keeps casual traffic off a private instance. It is not authentication.

Generate a token into the clipboard, paste it into Render, and keep it in the local dashboard config:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' | pbcopy
```

Run the dashboard locally against the live API on port 3000, the only origin its CORS allows. Put both values in `frontend/.env.local` (gitignored), not on the command line:

```bash
# frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=https://bv-live-api.onrender.com
NEXT_PUBLIC_BV_DASHBOARD_TOKEN=<the token>
```

```bash
cd frontend && npm run dev     # http://localhost:3000
```

`apiFetch()` sends `X-BV-Token` when `NEXT_PUBLIC_BV_DASHBOARD_TOKEN` is set (`frontend/src/lib/api.ts`). Plain links that bypass `apiFetch()` cannot send the header and return 401 on the live instance. Today that is the SAE JSON export link on the SAE page; use the demo instance for it. Command-line checks pass the header: `curl -H "X-BV-Token: $BV_DASHBOARD_TOKEN" $LIVE_API/api/escalations`.

## 6. State: SQLite, one instance, ephemeral disk

- The database is a SQLite file inside the container (`/app/backend/data/app.db`). Run **one instance per API** (`numInstances: 1`). Never scale out: each instance would have its own database and its own re-page loop.
- **The container disk is ephemeral.** Every deploy, which means every push to `main`, and every restart starts from a fresh seed, so escalations, drafts, SAE reports and the audit chain reset. The image seeds only when the database file is absent (R5).
- **During live calls (V10), do not merge to `main`.** Alternatively, pause auto-deploy for the session: `bv-live-api → Settings → Build & Deploy → Auto-Deploy: Off`. Turn it back on afterwards. A later Blueprint sync may restore the `render.yaml` value (UNVERIFIED).
- **Optional persistent disk** (pricing UNVERIFIED). Add it to `bv-live-api` in `render.yaml`:
  ```yaml
      disk:
        name: bv-live-data
        mountPath: /app/backend/data
        sizeGB: 1
  ```
  Render cannot scale a service that has a disk, which is fine here. Deploys then stop the old instance before starting the new one, so expect a short gap (UNVERIFIED). The image runs as the unprivileged user `bv` (uid 10001). Whether that user can write to the mounted disk is UNVERIFIED: check the first deploy log for a seed error. A kept database survives deploys, so a schema change needs a manual reseed in the service's **Shell**: `cd /app/backend && python -m app.seed`. Do this after any change like B13's audit chain (`HUMAN_TODO.md`).

## 7. Fallbacks

- **Tunnel for live calls** (no deploy needed): `make tunnel` exposes the local backend at `PUBLIC_BASE_URL`, then `make sync-agent` (`docs/04-voice-agent.md`). Record `"backend": "tunnel"` in `eval/results/voice_checks.json` (V10).
- **Local production images:** `make up` runs both images in demo mode. `BV_DEMO_MODE=0 make up` runs the live API with the secrets from `.env` (R5).
- **Cloud Run** (not tried; every command below is UNVERIFIED). This is the same backend image as one always-on, single instance. `--min-instances 1 --max-instances 1` keeps one SQLite database and one re-page loop. `--no-cpu-throttling` keeps the CPU on between requests, because the re-page loop and the replay threads run outside requests. The container file system is in memory, so state resets with every new revision or instance (as in §6).
  ```bash
  PROJECT=<gcp-project>; REGION=us-east4
  REPO=$REGION-docker.pkg.dev/$PROJECT/bv
  gcloud artifacts repositories create bv --repository-format=docker --location=$REGION
  gcloud auth configure-docker $REGION-docker.pkg.dev
  IMAGE=$REPO/backend:$(git rev-parse --short HEAD)
  docker build --platform linux/amd64 -f backend/Dockerfile -t $IMAGE . && docker push $IMAGE

  # Secrets once, each read from your .env without echoing it (repeat for every secret in §2).
  # The Cloud Run service account needs roles/secretmanager.secretAccessor.
  grep '^TOOL_SHARED_SECRET=' .env | cut -d= -f2- | sed 's/[[:space:]]*#.*//' | tr -d '\n' \
    | gcloud secrets create bv-tool-shared-secret --data-file=-

  gcloud run deploy bv-live-api --image $IMAGE --region $REGION \
    --min-instances 1 --max-instances 1 --no-cpu-throttling --allow-unauthenticated \
    --set-env-vars DEMO_MODE=0,APP_ENV=prod,CORS_ORIGINS=http://localhost:3000,GIT_COMMIT=$(git rev-parse --short HEAD) \
    --set-secrets TOOL_SHARED_SECRET=bv-tool-shared-secret:latest,BV_DASHBOARD_TOKEN=bv-dashboard-token:latest,ELEVENLABS_API_KEY=bv-elevenlabs-api-key:latest,ELEVENLABS_WEBHOOK_SECRET=bv-elevenlabs-webhook-secret:latest,AGENTS_LOCK_JSON=bv-agents-lock-json:latest,ANTHROPIC_API_KEY=bv-anthropic-api-key:latest,NTFY_TOPIC=bv-ntfy-topic:latest,NTFY_BACKUP_TOPIC=bv-ntfy-backup-topic:latest
  LIVE_API=$(gcloud run services describe bv-live-api --region $REGION --format 'value(status.url)')
  gcloud run services update bv-live-api --region $REGION --update-env-vars PUBLIC_BASE_URL=$LIVE_API
  ```
  - `--allow-unauthenticated` is required because ElevenLabs and the nurse's ack button call the service. The dashboard token gates `/api/*`.
  - Cloud Run sets `PORT` (8080), and both images listen on `$PORT`. `GIT_COMMIT` replaces Render's `RENDER_GIT_COMMIT` for `/api/health`.
  - **Demo pair:** deploy the same backend image as `bv-demo-api` with `DEMO_MODE=1,APP_ENV=demo` and a random `TOOL_SHARED_SECRET` (no other secrets). Then build the dashboard with that URL: `docker build --platform linux/amd64 -f frontend/Dockerfile --build-arg NEXT_PUBLIC_API_BASE_URL=$DEMO_API -t $REPO/web:<sha> .`, push it, and deploy it as `bv-demo-web` with the same instance flags. Finally, set the demo API's `CORS_ORIGINS` to the web URL with `gcloud run services update ... --update-env-vars`.

## 8. Local verification (Sun Oct 11, 2026)

`render.yaml` parses with three services:

```bash
python3 -c "import yaml; print([s['name'] for s in yaml.safe_load(open('render.yaml'))['services']])"
# ['bv-demo-api', 'bv-demo-web', 'bv-live-api']
```

The backend image ran in the **live-API configuration**. The settings were `DEMO_MODE=0`, `APP_ENV=prod` and `PORT=10000` (as on Render), with generated `TOOL_SHARED_SECRET` and `BV_DASHBOARD_TOKEN` values, a 4-variant `AGENTS_LOCK_JSON` of fake IDs and a fake `ELEVENLABS_API_KEY`. The env file was a throwaway outside the repository, and nothing secret was printed.

```bash
docker build -f backend/Dockerfile -t bv-backend:local .
docker run -d --env-file <throwaway live env> -p 8118:10000 bv-backend:local
curl -fsS localhost:8118/api/health | jq -e '.demo_mode==false'                          # true
curl -fsS localhost:8118/api/health | jq -e '.demo_mode==false and .browser_calls_enabled' # true: agent IDs from AGENTS_LOCK_JSON (the image has no lock file)
curl -s -o /dev/null -w '%{http_code}\n' localhost:8118/api/patients                      # 401 ({"error":{"code":"invalid_token",...}})
curl -s -o /dev/null -w '%{http_code}\n' -H "X-BV-Token: $BV_DASHBOARD_TOKEN" localhost:8118/api/patients   # 200
```

Other checks:
- The startup log said `dashboard_token=on`.
- `/agent/tools/record_answer` without the tool secret returned `bad_tool_secret`, and `/webhooks/elevenlabs/post-call` with a bad signature returned `bad_signature`. Neither route involves the token.
- A CORS preflight from `http://localhost:3000` that asked for `x-bv-token` returned 200.
- `/api/demo/scenarios` returned 404 `demo_disabled`.

The same image in the **demo-API configuration** (`DEMO_MODE=1`, `APP_ENV=demo`, no token) answered `/api/health` with `demo_mode: true` and `commit` taken from `RENDER_GIT_COMMIT`, and both `/api/patients` and `/api/demo/scenarios` returned 200.

The token rules are covered by `backend/tests/test_dashboard_token.py` and the `AGENTS_LOCK_JSON` fallback by `backend/tests/test_agents_lock_env.py` (`make test`). The dashboard image was built and run in R5. Not yet verified: a real Render deploy, the cross-service `RENDER_EXTERNAL_URL` references, a persistent disk, and Cloud Run.
