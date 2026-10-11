# Between Visits API, production image (WS0 R5). Build context = repo root:
#   docker build -f backend/Dockerfile -t between-visits-backend .
# The root .dockerignore keeps .env, data/patients.local.json, data/local/, agent/agents.lock.json and the
# other local-only files out of the build context, so they can never be copied into this image.
# Configuration comes from environment variables at runtime (no .env inside the image). Without DEMO_MODE=1
# the API refuses to start unless TOOL_SHARED_SECRET is set to a long random value (docs/03 §6.3).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/backend/.venv \
    PATH=/app/backend/.venv/bin:$PATH \
    PORT=8000

WORKDIR /app/backend

# Locked runtime dependencies first (cached layer); no dev tools in the image.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# The app and the repo files it reads at runtime. Paths resolve from the repo root (/app, app/config.py).
COPY backend/ ./
COPY data/ /app/data/
COPY scenarios/ /app/scenarios/
COPY agent/variants.json /app/agent/variants.json
COPY eval/results/ /app/eval/results/
COPY validation/ /app/validation/
# From Checkpoint B (B19): also monitoring/ (the project and its committed out/).

# Run as an unprivileged user; only the database directory and replay audio are writable.
RUN useradd --system --uid 10001 --no-create-home --home-dir /app bv \
    && mkdir -p /app/backend/data /app/scenarios/audio \
    && chown -R bv:bv /app/backend/data /app/scenarios/audio
USER bv

EXPOSE 8000

# Seed only when the SQLite database file is absent (exit code 3 from the check), so a restart on a kept
# disk keeps its state; then serve on $PORT (set by the host, default 8000).
CMD ["sh", "-c", "python -c 'from pathlib import Path; from app.config import get_settings; u = get_settings().resolved_database_url; raise SystemExit(3 if u.startswith(\"sqlite:///\") and not Path(u[len(\"sqlite:///\"):]).exists() else 0)' || [ $? -ne 3 ] || python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
