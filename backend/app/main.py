"""FastAPI app factory: CORS, error envelope, lifespan (create tables, re-page loop), routers."""

import asyncio
import contextlib
import logging
import os
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import ROOT, assert_safe_startup, get_settings
from app.db import create_all
from app.errors import ApiError

VERSION = "0.1.0"
log = logging.getLogger("bv")


def git_commit() -> str:
    if os.environ.get("GIT_COMMIT"):
        return os.environ["GIT_COMMIT"][:7]
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=2
        ).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


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
        log.info("startup demo_mode=%s pager=%s", settings.demo_mode, settings.effective_pager_channel)
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Between Visits API", version=VERSION, lifespan=lifespan)
    app.state.commit = git_commit()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
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

    from app.routers import agent_tools, api, demo, webhooks

    app.include_router(api.router)
    app.include_router(agent_tools.router)
    app.include_router(webhooks.router)
    app.include_router(demo.router)
    return app


app = create_app()
