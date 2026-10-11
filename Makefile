# Between Visits dev commands. Run from the repo root.
SHELL := /bin/bash
UV := uv run --project backend
# .env is read by the backend itself (pydantic-settings); only `tunnel` peeks at it here.
ENV_GET = $$(grep -E "^$(1)=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed -E "s/[[:space:]]+\#.*//; s/[[:space:]]+$$//")

# Pinned gitleaks release (WS0 R1); the CI job `gitleaks` downloads and checksum-verifies exactly this version.
GITLEAKS_VERSION := 8.30.1

.PHONY: setup dev backend frontend seed test test-backend test-frontend test-monitoring lint tunnel sync-agent types eval validate demo secret-scan up planning-grid site-signal

# Clean setup (WS0 R2): Python 3.12 from .python-version; `npm ci` installs exactly frontend/package-lock.json
# and never rewrites it, so the tree stays clean. Add or upgrade frontend deps with `npm install` in frontend/.
# monitoring/ (Site Signal statistics) is its own uv project with its own lock.
setup:
	cd backend && uv sync
	cd frontend && npm ci
	cd monitoring && uv sync

dev:
	@trap 'kill 0' EXIT; \
	(cd backend && uv run uvicorn app.main:app --reload --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

seed:
	cd backend && uv run python -m app.seed

test: test-backend test-frontend test-monitoring

test-backend:
	cd backend && uv run ruff check app tests && uv run pytest -q
	$(UV) python data/validate_data.py
	python3 agent/test_sync_agent.py
	python3 agent/test_export_scenario.py
	python3 agent/test_voice_check.py

test-frontend:
	cd frontend && npm run typecheck && npm run lint

# Site Signal statistics suite (WS5): ruff + pytest in the separate monitoring/ uv project
test-monitoring:
	cd monitoring && uv run ruff check . && uv run pytest -q

lint:
	cd backend && uv run ruff check app tests --fix

tunnel:
	ngrok http 8000 --url https://$(call ENV_GET,NGROK_DOMAIN)

sync-agent:
	$(UV) python agent/sync_agent.py $(ARGS)

types:
	cd frontend && npx openapi-typescript http://localhost:8000/openapi.json -o src/lib/api-types.ts

eval:
	$(UV) python eval/run_eval.py --mode text --out eval/results/latest.json $(ARGS)

validate:
	$(UV) python validation/build_traceability.py $(ARGS)

# gitleaks over the full history of every ref (primary check), then the real-phone-number grep. validation/secret-scan.md
secret-scan:
	@command -v gitleaks >/dev/null 2>&1 || { echo "secret-scan: gitleaks not found; install the pinned $(GITLEAKS_VERSION) release (validation/secret-scan.md)" >&2; exit 1; }
	@v="$$(gitleaks version)"; case "$$v" in $(GITLEAKS_VERSION)|v$(GITLEAKS_VERSION)) ;; *) echo "secret-scan: gitleaks $$v found, pinned $(GITLEAKS_VERSION); install the pinned release (validation/secret-scan.md)" >&2; exit 1;; esac
	gitleaks git --redact --log-opts="--all" -v . && python3 validation/scan_numbers.py

# `make demo DEMO_PROD=1` serves the production frontend build (next build && next start), so screenshots and
# recordings have no Next.js dev badge. next start prints a notice about output: "standalone" (that setting is for
# the image); it serves the same production build.
ifeq ($(DEMO_PROD),1)
DEMO_FRONTEND := npm run build && npm run start
else
DEMO_FRONTEND := npm run dev
endif

# S1: pre-tag planning grid (docs/11 §11.5), dev seed only; planning only, not a result
planning-grid:
	uv run --project monitoring python monitoring/planning/plan_power.py --seed dev --out monitoring/planning/planning_grid.json

# S6: the committed study from the sap-v1 evaluation seed (stream 0) -> monitoring/out/*.json and
# validation/site_signal/{report.md,funnel.svg}; logged in validation/site_signal/run_log.jsonl; < 60 s.
# Refuses a dirty tree. Development: ARGS="--seed dev --out <scratch dir>" (never monitoring/out/).
site-signal:
	uv run --project monitoring python -m bvsignal.run $(ARGS)

# S7: Site Signal operating characteristics (docs/11 §12): evaluation seed, logged, refuses a dirty tree; full run in
# the background (validation/site_signal/*.json). CI: ARGS="--quick --check". Development: ARGS="--seed dev --scale 0.02 --out $$TMPDIR/val"
.PHONY: site-signal-validate
site-signal-validate:
	uv run --project monitoring python -m bvsignal.validate $(ARGS)

demo:
	@trap 'kill 0' EXIT; \
	(cd backend && DEMO_MODE=1 uv run python -m app.seed && DEMO_MODE=1 uv run uvicorn app.main:app --port 8000) & \
	(cd frontend && $(DEMO_FRONTEND)) & \
	wait

# Production images (WS0 R5): docker-compose.prod.yml, both services, DEMO_MODE=1 by default (BV_DEMO_MODE=0 runs
# the live API). Host ports API_PORT (8000) and WEB_PORT (3000). COMPOSE=docker-compose for the standalone binary.
COMPOSE ?= docker compose
up:
	GIT_COMMIT=$$(git rev-parse --short HEAD 2>/dev/null) $(COMPOSE) -f docker-compose.prod.yml up --build
