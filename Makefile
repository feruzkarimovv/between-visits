# Between Visits dev commands. Run from the repo root.
SHELL := /bin/bash
UV := uv run --project backend
# .env is read by the backend itself (pydantic-settings); only `tunnel` peeks at it here.
ENV_GET = $$(grep -E "^$(1)=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed -E "s/[[:space:]]+\#.*//; s/[[:space:]]+$$//")

.PHONY: setup dev backend frontend seed test test-backend test-frontend lint tunnel sync-agent types eval validate demo

setup:
	cd backend && uv sync
	cd frontend && npm install

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

demo:
	@trap 'kill 0' EXIT; \
	(cd backend && DEMO_MODE=1 uv run python -m app.seed && DEMO_MODE=1 uv run uvicorn app.main:app --port 8000) & \
	(cd frontend && npm run dev) & \
	wait
