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

6. **Freeze the SAP: review, tag `sap-v1`, publish the timestamp, fetch the beacon (S1; docs/11 §1.2 steps 2-7).** S1 is integrated on `site-signal-build`: §11.5 filled (patients per site 40-80 and gross *f* 0.90, both "shortfall" from the planning grid), `monitoring/params.yaml` frozen-input hashes written, §17 empty. **Update:** the §1.5 `sap-v1` row is now filled (commit 9c6e84a), so follow item 11 instead of sub-steps 1-2 here, then sub-steps 3-6. Nothing below can be undone once the tag is pushed (the tag is never moved or deleted), so do the steps in order:
   1. Review the SAP diff (`git diff 607d213..origin/site-signal-build -- docs/11-site-signal-sap.md monitoring/params.yaml`). If the review OK has not arrived by 03:15, tag anyway and write "tagged without human review" in the change-log line.
   2. Fill the docs/11 §1.5 change-log row for `sap-v1` (replace "at the tag" with today's date, and keep either "reviewed by the team lead" or "tagged without human review", whichever applies). Commit it on `site-signal-build`, check it, push it, then fast-forward `main` to exactly that commit. docs/11 §1.2 steps 2-3 put the frozen commit on `main` and the tag on `origin/main`, so a later squash or rebase of the branch can never drop the tag commit (part of the seed) from `main`'s history:
      ```bash
      cd ~/hackru/between-visits && git checkout site-signal-build && git pull --ff-only
      # edit docs/11-site-signal-sap.md §1.5, then:
      git commit -am "SAP v1: change log"
      uv run --project monitoring python -m bvsignal.seed --check-frozen          # expect: frozen inputs: OK
      git push origin site-signal-build
      git push origin site-signal-build:main      # fast-forward only: never add --force, -f or a leading +
      git fetch origin
      test "$(git rev-parse origin/main)" = "$(git rev-parse HEAD)" && echo main-is-the-sap-commit   # expect: main-is-the-sap-commit
      git ls-tree -r origin/main --name-only | grep -E '^(monitoring/out|validation/site_signal)/'   # must print nothing
      ```
      If `git push origin site-signal-build:main` is rejected (non-fast-forward: `main` has commits that are not on `site-signal-build`), stop: do not force it and do not tag. Bring `main` into the branch with a merge commit, then repeat this step from the `--check-frozen` line:
      ```bash
      git fetch origin && git merge --no-ff origin/main -m "Merge main into site-signal-build before sap-v1" && git push origin site-signal-build
      ```
      If `git push origin site-signal-build` is rejected because the branch moved, run `git pull --rebase origin site-signal-build` (only the unpushed change-log commit moves; nothing is tagged yet) and repeat from the `--check-frozen` line.
   3. Tag exactly the commit `origin/main` now points to, and push the tag:
      ```bash
      git fetch origin && git tag -a sap-v1 origin/main -m 'Site Signal SAP v1' && git push origin sap-v1
      git rev-parse 'sap-v1^{commit}'                                       # the tag sha to publish
      git merge-base --is-ancestor sap-v1 origin/main && echo tag-on-main   # expect: tag-on-main
      ```
      From now on `main` is never rebased, squashed or force-pushed (on GitHub never "Squash and merge" or "Rebase and merge" into `main`), and the commits from the tag onwards on `site-signal-build` are never rebased either. Later work reaches `main` only by fast-forward or a merge commit (item 1), so the tag commit stays an ancestor of `main` and of every commit that adds evaluation outputs (REQ-022).
   4. Within 10 minutes of the push, publish the tag sha outside the team's control: on GitHub, Releases > Draft a new release > choose tag `sap-v1` > title "Site Signal SAP v1" > Publish release (or `gh release create sap-v1 --title "Site Signal SAP v1" --notes "sap-v1 = <tag sha>"`), and post the sha in the Devpost draft or the event's organizer channel. Keep both links for the §17 row.
   5. Fetch the beacon (docs/11 §1.3: the first drand round at least 10 minutes after the tagger time) and record the seed. Start it right after the tag push and leave it running:
      ```bash
      uv run --project monitoring python -m bvsignal.seed --fetch-beacon --wait   # writes monitoring/seed_beacon.json once; never overwrites it
      uv run --project monitoring python -m bvsignal.seed --show                  # tag sha, beacon round, evaluation seed
      ```
      `--wait` sleeps until the round time (it prints it), then tries drand every 30 s. It asks NIST only from round time + 30 min and writes the empty value only from round time + 60 min, so with drand down it can run up to an hour: let it finish. The file records `source`, the `selection` times and every failed attempt (`attempts`). If you stop it (Ctrl-C) or it exits with an error, rerun the same command: the failed attempts so far are kept in `monitoring/seed_beacon_attempts.jsonl` and go into the beacon file. Never delete either file.
   6. Add a docs/11 §17 clarification row (Release link, Devpost/organizer link, beacon round and `source`; say so if the external timestamp is not earlier than the beacon round; if `attempts` is not empty, cite how many there were, the first and last UTC times and the errors) and commit it with the beacon file:
      ```bash
      git add monitoring/seed_beacon.json docs/11-site-signal-sap.md
      git commit -m "SAP v1: beacon round and external timestamp (docs/11 §17)" && git push origin site-signal-build
      ```
   Only after this may S6/S7/S8 produce evaluation output (`monitoring/out/`, `validation/site_signal/`).

7. **Deploy to Render: public demo pair and private live API (R6; `render.yaml`, full guide in `docs/deploy.md`).** R6 is integrated on `site-signal-build` and verified locally only (token tests, a live-config container returning 401 without `X-BV-Token`, `render.yaml` parses to the three services). Dashboard labels are as of Oct 2026 and may have moved (UNVERIFIED). Never type a secret into a file in the repository.
   1. **`render.yaml` must be on `main`**: the Blueprint and every auto-deploy read `main`. Do item 1 (merge `site-signal-build` into `main`) first.
   2. **Billing.** Sign in at https://dashboard.render.com with GitHub → **Workspace Settings → Billing** → add a payment method, and approve three always-on `starter` instances (`bv-demo-api`, `bv-demo-web`, `bv-live-api`; pricing UNVERIFIED).
   3. **GitHub app access.** Render dashboard → **New → Blueprint → Connect a repository** → on GitHub's Render app page choose the account that owns `feruzkarimovv/between-visits` → **Only select repositories** → add `between-visits` → **Install** (or **Save**). Do not change the repository's visibility.
   4. **Create the Blueprint.** Select `between-visits`; Blueprint name `between-visits`, branch `main`, Blueprint path `render.yaml`. When Render asks for the `sync: false` values of `bv-live-api`, paste:
      - `TOOL_SHARED_SECRET` = the exact value in the local `.env` (it must equal the ElevenLabs workspace secret `bv_tool_secret`);
      - `BV_DASHBOARD_TOKEN` = a new value; keep a copy for sub-step 8:
        ```bash
        python3 -c 'import secrets; print(secrets.token_urlsafe(32), end="")' | pbcopy
        ```
      - `ELEVENLABS_API_KEY`, `ELEVENLABS_WEBHOOK_SECRET`, `ANTHROPIC_API_KEY`, `NTFY_TOPIC`, `NTFY_BACKUP_TOPIC` = the local `.env` values;
      - `AGENTS_LOCK_JSON` = the lock file on one line, copied without printing it (run in the repo root):
        ```bash
        python3 -c 'import json; print(json.dumps(json.load(open("agent/agents.lock.json")), separators=(",", ":")))' | pbcopy
        ```
      Then click **Deploy Blueprint** (or **Apply**).
   5. **After three green deploys, check the cross-service URLs** on each service's **Environment** tab: `bv-demo-api` `CORS_ORIGINS` = the `bv-demo-web` URL; `bv-demo-web` `NEXT_PUBLIC_API_BASE_URL` = the `bv-demo-api` URL; `bv-live-api` `PUBLIC_BASE_URL` = its own URL. If any is empty or wrong, set the `https://….onrender.com` URL by hand. For `bv-demo-web`, then use **Manual Deploy → Clear build cache & deploy** (the URL is inlined at build time).
   6. **Point the agents at the live API**, from a laptop with the full `.env`:
      ```bash
      LIVE_API=https://bv-live-api.onrender.com     # the real URL from sub-step 5
      PUBLIC_BASE_URL=$LIVE_API make sync-agent ARGS="--setup-webhook"
      ```
      If it warns that the webhook points at an old tunnel, edit the webhook URL in ElevenLabs (workspace **Settings → Webhooks**) to `$LIVE_API/webhooks/elevenlabs/post-call`. If a new `ELEVENLABS_WEBHOOK_SECRET` is printed or `agent/agents.lock.json` changed, update those two values in **`bv-live-api` → Environment → Save**, then rebuild and deploy.
   7. **Acceptance**, with `main` checked out at the deployed commit:
      ```bash
      DEMO_API=https://bv-demo-api.onrender.com   # the real URLs from sub-step 5
      DEMO_WEB=https://bv-demo-web.onrender.com
      LIVE_API=https://bv-live-api.onrender.com
      curl -fsS $DEMO_API/api/health | jq -e '.demo_mode==true and .commit=="'$(git rev-parse --short HEAD)'"'   # true
      curl -fsS $LIVE_API/api/health | jq -e '.demo_mode==false and .browser_calls_enabled'                       # true
      curl -s -o /dev/null -w '%{http_code}\n' $LIVE_API/api/patients                                               # 401
      ```
      Then, in an incognito window on `$DEMO_WEB`: **Replay** a scenario → confirm the drafts → switch to Investigator → assessment → SAE sign → send → the report appears in the sponsor inbox.
   8. **Live calls** run from a local dashboard against `bv-live-api`. Put these in `frontend/.env.local` (gitignored), then start it:
      ```bash
      # frontend/.env.local
      NEXT_PUBLIC_API_BASE_URL=https://bv-live-api.onrender.com
      NEXT_PUBLIC_BV_DASHBOARD_TOKEN=<the BV_DASHBOARD_TOKEN from sub-step 4>
      ```
      ```bash
      cd frontend && npm run dev      # http://localhost:3000
      ```
      Do not merge to `main` during the calls: each deploy resets the live SQLite state. You can also turn off **`bv-live-api` → Settings → Build & Deploy → Auto-Deploy** for the session. Known gap (F10): the SAE JSON export link is a plain link and cannot send `X-BV-Token`, so it returns 401 on the live instance (`docs/deploy.md` §5).
   9. **Once it works:** put the `bv-demo-web` URL into the README (R8 replaced the old "**Live demo:** not deployed yet" line; the exact edits are item 9 below), and remove "verified locally only" from `docs/deploy.md`; commit and push.

8. **Timed README walkthrough (R8 acceptance).** A teammate who did not build the product follows only the README section "Reviewer path (3 minutes)" and must reach the Sponsor inbox in under 3 minutes. Do not help them; start a stopwatch when they open the dashboard.
   - Once `bv-demo-web` is deployed (item 7): open the `bv-demo-web` URL in an incognito window.
   - Until then, on a laptop with uv, Node 22 and make, from the repo root:
     ```bash
     cp .env.example .env                  # leave every key empty
     make setup && make seed && make demo  # backend :8000 + dashboard :3000, DEMO_MODE=1
     ```
     then open http://localhost:3000.
   - They follow the table: **Today** → Speed **4x** → **Replay scenario** → Check-in (Urgent panel, "Acknowledged in N s") → **Review 3 drafts** → **Confirm** Diarrhea → role **Investigator · Dr. Patel** → tick **Requires or prolongs hospitalization**, pick a relatedness, **Sign as Dr. Patel** → **Open report** → **Sign as Dr. Patel** → **Send to sponsor** → **Sponsor inbox** shows 101-007 *On time*. Stop the clock there.
   - Record the time and where they got stuck (if anywhere) in the R8 row of `PROGRESS.md` (Acceptance output), then commit and push:
     ```bash
     git add PROGRESS.md && git commit -m "R8: timed README walkthrough" && git push origin site-signal-build
     ```
   - If it took 3 minutes or more, note the step that cost the time; the README path gets fixed before submission (D16).

9. **Put the public demo URL into the README after the Render deploy (R8; after item 7).** The README says "the public demo URL (pending deploy, …)" in two places. With the real `bv-demo-web` URL (from item 7, sub-step 5):
   - README line 13 (starts with "**Public demo:**"): replace the words from "the public demo URL (pending deploy" through the closing parenthesis after the `docs/deploy.md` link with the `bv-demo-web` URL, and change "Until it is live, run" to "To run"; keep the `make demo` and Quickstart link.
   - README line 17 (first line under "Reviewer path (3 minutes)"): replace the same words, "the public demo URL (pending deploy" through the closing parenthesis after the `docs/deploy.md` link, with the `bv-demo-web` URL.
   - README "Deploy" section: remove the sentence "So far it is verified locally only." (and the same words at the top of `docs/deploy.md`, as in item 7 sub-step 9; `docs/deploy.md` §4 step 8 still names the old "**Live demo:** not deployed yet" line, update it to say README lines 13 and 17).
   - Check, then commit and push:
     ```bash
     grep -n 'pending deploy' README.md    # prints nothing
     git add README.md docs/deploy.md && git commit -m "README: public demo URL" && git push origin site-signal-build
     ```
   - The demo video and deck lines (`_TODO_ (added at submission)`, README lines 9 and 11) are filled by D16 at submission, not here.

10. **Export the real V10 calls as recorded replay scenarios (V11; after V10).** V11 is integrated on `site-signal-build`: `agent/export_scenario.py` and the demo-only route `GET /api/demo/scenarios/{id}/audio`. No recorded scenario exists yet (the demo lists 0 recorded scenarios until this item is done).
   1. **Consent first.** Confirm that the teammate who played each synthetic patient agrees to the call being recorded and exported as a transcript. Use `--audio` only with that consent. Serving the audio from the public demo also needs their written consent; without it, ship transcript-only (leave out `--audio`, or keep the mp3 off the public instance).
   2. **Setup.** After the V10 calls are logged in `eval/results/voice_checks.json`, work from the main checkout root and take each call's `conversation_id` and `checkin_id` from that file. `ELEVENLABS_API_KEY` must be in `.env`. If the live instance uses a dashboard token, `BV_DASHBOARD_TOKEN` must be set in `.env` or the shell.
      ```bash
      export LIVE_API=<live API base URL the calls ran against>   # falls back to PUBLIC_BASE_URL
      ```
   3. **Call 1** (en-standard, James, grade 2, no page):
      ```bash
      uv run --project backend python agent/export_scenario.py --conversation-id <conv_ of call 1> --checkin-id <ci_ of call 1> --id rec_en_g2 --title "James, English, standard, grade 2 diarrhea (recorded)"
      ```
   4. **Call 3** (es-extra_time, Rosa, red flag). Leave out `--audio` if there is no consent:
      ```bash
      uv run --project backend python agent/export_scenario.py --conversation-id <conv_ of call 3> --checkin-id <ci_ of call 3> --id rec_es_g3_flag --title "Rosa, Spanish, extra time, urgent diarrhea (recorded)" --audio
      ```
      If call 3 failed, export call 2 instead with `--id rec_en_g3_flag --title "James, English, standard, urgent diarrhea (recorded)"`.
   5. **Read every warning the script prints.** "link check" or "no whitelisted argument left" means stop and investigate. Do not pass `--skip-link-check` unless you are sure the conversation and the check-in are the same call.
   6. **RULE: a person reviews before `git add`.** Read the whole transcript (`events[-1].transcript`) and every tool argument (`events[].body`) in each `scenarios/<id>.json`, looking for a real name, phone number or other identifier spoken off-script. If one appears, do not commit the file as is: re-record the call, or replace the words with `[redacted]` and say so in the commit message. Do not edit the file in any other way.
   7. **Verify.**
      ```bash
      python3 agent/test_export_scenario.py      # also checks every committed recorded scenario against the whitelist
      make demo                                  # then, in another terminal:
      curl -s localhost:8000/api/demo/scenarios | jq '[.[]|select(.recorded)]|length'   # expect 2
      ```
   8. **Fidelity check** for each exported scenario (example for `rec_es_g3_flag`; repeat with `rec_en_g2`):
      ```bash
      cid=$(curl -s -X POST 'localhost:8000/api/demo/replay/rec_es_g3_flag?speed=4' | jq -r .checkin_id)
      # wait for the replay to finish, then:
      curl -s localhost:8000/api/checkins/$cid | jq '[.findings[]|{term,provisional_grade,rule_id}]'
      ```
      The result must equal the grade and `rule_id` of that call in `eval/results/voice_checks.json`.
   9. **Commit** only `scenarios/rec_*.json`, then push. Never commit `scenarios/audio/*.mp3` (gitignored); copy the mp3 to the demo machine's `scenarios/audio/` by hand.
      ```bash
      git add scenarios/rec_*.json && git commit -m "WS1-V11: recorded scenarios rec_en_g2 rec_es_g3_flag" && git push origin site-signal-build
      ```

11. **Finish the `sap-v1` freeze: the §1.5 row is filled, the tag is not made (S1 final; docs/11 §1.2 steps 2-7).** Commit 9c6e84a on `site-signal-build` sets the docs/11 Status line to "frozen by the annotated tag `sap-v1` (§1.5)" and fills the §1.5 `sap-v1` row (2026-10-11; §11.5 P1 shortfall, P2 shortfall; reviewed by agent with a statistician's lens, 4 rounds; "team lead review pending"). This replaces item 6 sub-steps 1-2 (do not add a second change-log commit). `--check-frozen` passes and nothing under `monitoring/out/` or `validation/site_signal/` exists. Nothing is tagged or released yet.
   1. **Review the SAP diff** (team lead):
      ```bash
      cd ~/hackru/between-visits && git checkout site-signal-build && git pull --ff-only
      git diff 607d213..origin/site-signal-build -- docs/11-site-signal-sap.md monitoring/params.yaml
      ```
   2. **Optional, only if you signed off before tagging:** before sub-step 3, change the phrase "team lead review pending" in the docs/11 §1.5 `sap-v1` row to "reviewed by the team lead", and commit it before anything goes to `main`:
      ```bash
      sed -i '' 's/team lead review pending; frozen\./reviewed by the team lead; frozen./' docs/11-site-signal-sap.md
      grep -n '^| `sap-v1` |' docs/11-site-signal-sap.md       # check the row
      git commit -am "SAP v1: team lead review in change log"
      ```
      Without a sign-off, leave the row as it is (docs/KICKOFF.md wording).
   3. **Land the frozen commit on `main`** (docs/11 §1.2 steps 2-3; same rejection handling as item 6 sub-step 2: never force):
      ```bash
      uv run --project monitoring python -m bvsignal.seed --check-frozen; echo exit=$?   # expect: frozen inputs: OK, exit=0
      git push origin site-signal-build
      git push origin site-signal-build:main      # fast-forward only: never add --force, -f or a leading +
      git fetch origin
      test "$(git rev-parse origin/main)" = "$(git rev-parse HEAD)" && echo main-is-the-sap-commit   # expect: main-is-the-sap-commit
      git ls-tree -r origin/main --name-only | grep -E '^(monitoring/out|validation/site_signal)/'   # must print nothing
      ```
   4. **Tag the pushed commit** (docs/11 §1.2 step 5; tag `origin/main`, never a worktree sha):
      ```bash
      git fetch origin && git tag -a sap-v1 origin/main -m 'Site Signal SAP v1' && git push origin sap-v1
      git rev-parse 'sap-v1^{commit}'                                       # the tag sha to publish
      git merge-base --is-ancestor sap-v1 origin/main && echo tag-on-main   # expect: tag-on-main
      ```
   5. **External timestamp within 10 minutes** (docs/11 §1.2 step 6): GitHub > Releases > Draft a new release > tag `sap-v1` > title "Site Signal SAP v1" > Publish release (or `gh release create sap-v1 --title "Site Signal SAP v1" --notes "sap-v1 = <tag sha>"`), and post the tag sha in the Devpost draft or the organizer channel. Keep both links.
   6. **Beacon** (docs/11 §1.2 step 7), started right after the tag push and left running until it exits:
      ```bash
      uv run --project monitoring python -m bvsignal.seed --fetch-beacon --wait   # writes monitoring/seed_beacon.json once
      uv run --project monitoring python -m bvsignal.seed --show                  # tag sha, beacon round, evaluation seed
      ```
   7. **Commit the beacon file with a §17 clarification** (Release link, Devpost/organizer link, beacon round and `source`, and the `attempts` summary if not empty), exactly as item 6 sub-step 6:
      ```bash
      git add monitoring/seed_beacon.json docs/11-site-signal-sap.md
      git commit -m "SAP v1: beacon round and external timestamp (docs/11 §17)" && git push origin site-signal-build
      ```
   Only after this may S6/S7/S8 produce evaluation output.

12. **Post the `sap-v1` tag sha outside the team's control and log the link in docs/11 §17 (S1 follow-up; docs/11 §1.2 step 6).** Done on `site-signal-build` in commit 5e1849e ("WS5-S1: beacon round and evaluation seed"): tag `sap-v1` on commit `68838978bb305e0f730d30e5cbf3c00bceca5a25` (tag object `e5b4a7983c4a3f3b3bd5f46d8b6cdc65d9d4b1e6`, same on origin), GitHub Release https://github.com/feruzkarimovv/between-visits/releases/tag/sap-v1 published 2026-10-11T08:38:10Z, beacon drand round 6542582 (round time 08:48:00Z, no failed attempts) in `monitoring/seed_beacon.json`, evaluation seed 92794863, docs/11 §17 rows C1 (Release timestamp) and C2 (beacon and seed). This finishes item 6 sub-steps 3-6 and item 11 sub-steps 3-7, except the Devpost/organizer post. Do not rerun `--fetch-beacon` and never edit or delete `monitoring/seed_beacon.json`. The tag exists now, so do not edit the docs/11 §1.5 `sap-v1` row (item 11 sub-step 2 no longer applies); a later team lead sign-off goes in its own §17 clarification row.
   1. Post this text in the Devpost draft (project description or an update) or in the event's organizer channel, then copy the post's link (Devpost URL or message permalink) and note the post time in UTC:
      ```
      Between Visits Site Signal SAP v1 is frozen: sap-v1 = 68838978bb305e0f730d30e5cbf3c00bceca5a25
      https://github.com/feruzkarimovv/between-visits/releases/tag/sap-v1
      ```
   2. In `docs/11-site-signal-sap.md` §17, add row C4 directly below C3 (S4 took C3; if more rows landed since, use the next free number below the last C row) and above the empty placeholder row `| | | | | | | | | |` (keep the placeholder last: `monitoring/tests/test_seed.py` replaces it in a test). Fill in `<HH:MM>`, `<post link>` and `<UTC time>`. The post is later than both the 10-minute window and the beacon round time, and §1.2 step 6 requires §17 to say so:
      ```
      | C4 | 2026-10-11 <HH:MM> ET | Commit `SAP v1: organizer timestamp link (docs/11 §17)` | §1.2 step 6 | clarification | Tag sha `68838978bb305e0f730d30e5cbf3c00bceca5a25` and the Release link posted at <post link> at <UTC time>. This post is later than the 10-minute window after the tag push and later than the beacon round time 2026-10-11T08:48:00Z (row C2); the GitHub Release in row C1 (`publishedAt` 08:38:10Z) is the external timestamp that is earlier than the round. | §1.2 step 6 puts both external-timestamp links in a §17 clarification and requires §17 to say when one is not earlier than the beacon round. | No | None on any result. |
      ```
   3. Check, commit and push:
      ```bash
      cd ~/hackru/between-visits && git checkout site-signal-build && git pull --ff-only
      grep -c '^| C[1234] |' docs/11-site-signal-sap.md                     # expect: 4
      uv run --project monitoring python -m bvsignal.seed --check-frozen     # expect: frozen inputs: OK
      uv run --project monitoring python -m bvsignal.seed --show             # expect: sap_tag_commit=68838978bb305e0f730d30e5cbf3c00bceca5a25 beacon_round=6542582 eval_seed=92794863
      make test
      git add docs/11-site-signal-sap.md && git commit -m "SAP v1: organizer timestamp link (docs/11 §17)" && git push origin site-signal-build
      ```
   4. Optional (docs/workstreams/WS5-site-signal.md, S1 step 7): post the seed line in the team chat:
      ```
      sap_tag_commit=68838978bb305e0f730d30e5cbf3c00bceca5a25 beacon_round=6542582 eval_seed=92794863
      ```

13. **Run the committed evaluation-seed calibration once (S4; WS5 sequence step 9, docs/11 §9.2).** S4 (`monitoring/bvsignal/calibrate.py`, `indicators.py`) is integrated on `site-signal-build` in commit 666c618; no evaluation-seed run has been made and `monitoring/out/` does not exist. Run it once, on a clean checkout, after S5 is green (it is) and before S6's `make site-signal`. The first evaluation-seed run of a code commit is the one committed: never rerun it to get different numbers, never commit a `--seed dev` output, and do not quote any threshold until it is in `validation/site_signal/summary.json`.
   ```bash
   cd ~/hackru/between-visits && git checkout site-signal-build && git pull --ff-only
   git status --porcelain                                                 # expect: nothing (the run refuses a dirty tree)
   uv run --project monitoring python -m bvsignal.seed --check-frozen     # expect: frozen inputs: OK
   time uv run --project monitoring python -m bvsignal.calibrate          # evaluation seed (default), R = 2000; about 22 s on 14 cores
   jq '{r_null, discordance, rate_kri, simaerep_classic, achieved}' monitoring/out/thresholds.json
   git status --porcelain   # expect exactly: monitoring/out/thresholds.json, monitoring/out/null_pool.json, validation/site_signal/run_log.jsonl
   git add monitoring/out/thresholds.json monitoring/out/null_pool.json validation/site_signal/run_log.jsonl
   git commit -m "WS5-S4: evaluation-seed calibration (thresholds.json, null_pool.json, run log)"
   git push origin site-signal-build                                      # never rebase or amend this commit afterwards
   ```
   If the run refuses or fails, do not edit any output by hand; record the error and stop.
