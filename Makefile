# Between Visits dev commands. Run from the repo root.
SHELL := /bin/bash
UV := uv run --project backend
# .env is read by the backend itself (pydantic-settings); only `tunnel` peeks at it here.
ENV_GET = $$(grep -E "^$(1)=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed -E "s/[[:space:]]+\#.*//; s/[[:space:]]+$$//")

# Pinned gitleaks release (WS0 R1); the CI job `gitleaks` downloads and checksum-verifies exactly this version.
GITLEAKS_VERSION := 8.30.1

.PHONY: setup dev backend frontend seed test test-backend test-frontend lint tunnel sync-agent types eval validate demo secret-scan

# Clean setup (WS0 R2): Python 3.12 from .python-version; `npm ci` installs exactly frontend/package-lock.json
# and never rewrites it, so the tree stays clean. Add or upgrade frontend deps with `npm install` in frontend/.
setup:
	cd backend && uv sync
	cd frontend && npm ci

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

test: test-backend test-frontend

test-backend:
	cd backend && uv run ruff check app tests && uv run pytest -q
	$(UV) python data/validate_data.py
	python3 agent/test_sync_agent.py

test-frontend:
	cd frontend && npm run typecheck && npm run lint

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

demo:
	@trap 'kill 0' EXIT; \
	(cd backend && DEMO_MODE=1 uv run python -m app.seed && DEMO_MODE=1 uv run uvicorn app.main:app --port 8000) & \
	(cd frontend && npm run dev) & \
	wait
