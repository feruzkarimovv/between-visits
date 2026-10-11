"""FastAPI app factory: CORS, dashboard token, error envelope, lifespan (tables, re-page loop), routers."""

import asyncio
import contextlib
import hmac
import logging
import os
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import ROOT, assert_safe_startup, get_settings
from app.db import create_all
from app.errors import ApiError

VERSION = "0.1.0"
log = logging.getLogger("bv")


# Commit for /api/health when there is no .git (container images), first match wins, shortened to 7 characters:
# GIT_COMMIT (docker-compose.prod.yml, from `make up`), then RENDER_GIT_COMMIT (set by Render on every service at
# build time and runtime, "The commit SHA for a service or deploy": render.com/docs/environment-variables,
# checked Oct 11 2026).
COMMIT_ENV_VARS = ("GIT_COMMIT", "RENDER_GIT_COMMIT")


def git_commit() -> str:
    for var in COMMIT_ENV_VARS:
        value = os.environ.get(var, "").strip()
        if value:
            return value[:7]
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=2
        ).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


# Optional dashboard token (docs/03 §6.8, R6). Only the dashboard API is gated: /agent/tools/* and /webhooks/* keep
# their own checks (tool secret, HMAC, ack tokens), and the platform health check needs GET /api/health.
DASHBOARD_TOKEN_HEADER = "X-BV-Token"
TOKEN_EXEMPT = {("GET", "/api/health")}


def needs_dashboard_token(method: str, path: str) -> bool:
    """True for every /api/* request except GET /api/health."""
    if not (path == "/api" or path.startswith("/api/")):
        return False
    return (method.upper(), path) not in TOKEN_EXEMPT


class DashboardTokenMiddleware:
    """401 `invalid_token` for a gated request without the right X-BV-Token; everything else passes untouched.

    Added inside CORSMiddleware, so CORS preflights are answered before this check (a browser never sends custom
    headers on a preflight) and a 401 still carries the CORS headers the dashboard needs to read the error code.
    The token keeps casual traffic off a private instance; it is not authentication.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not needs_dashboard_token(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return
        sent = Headers(scope=scope).get(DASHBOARD_TOKEN_HEADER, "").strip().encode()
        if hmac.compare_digest(sent, self.token):
            await self.app(scope, receive, send)
            return
        log.warning("dashboard_token_rejected method=%s path=%s header_present=%s",
                    scope["method"], scope["path"], bool(sent))
        response = JSONResponse(
            status_code=401,
            content={"error": {"code": "invalid_token",
                               "message": f"This instance needs the dashboard token in the {DASHBOARD_TOKEN_HEADER} header."}},
        )
        await response(scope, receive, send)


def create_app(start_background: bool = True) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    assert_safe_startup(settings)  # exits non-zero outside DEMO_MODE with an unsafe TOOL_SHARED_SECRET

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        create_all()
        task = None
        if start_background:
            from app.services.escalation import repage_loop

            task = asyncio.create_task(repage_loop())
        log.info("startup demo_mode=%s pager=%s dashboard_token=%s", settings.demo_mode,
                 settings.effective_pager_channel, "on" if settings.dashboard_token else "off")
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Between Visits API", version=VERSION, lifespan=lifespan)
    app.state.commit = git_commit()
    if settings.dashboard_token:
        # Added first, so it runs inside CORSMiddleware (the middleware added last is the outermost).
        app.add_middleware(DashboardTokenMiddleware, token=settings.dashboard_token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-BV-Note", "Content-Disposition"],  # read by the dashboard's download helper (docs/03 §6.5)
    )

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            body = {"error": {"code": exc.detail["code"], "message": exc.detail.get("message", "")}}
        else:
            body = {"error": {"code": f"http_{exc.status_code}", "message": str(exc.detail)}}
        return JSONResponse(status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"error": {"code": "validation_error", "message": str(exc.errors())[:1000]}}
        )

    from app.routers import agent_tools, api, demo, site_signal, webhooks

    app.include_router(api.router)
    app.include_router(site_signal.router)
    app.include_router(agent_tools.router)
    app.include_router(webhooks.router)
    app.include_router(demo.router)
    return app


app = create_app()
