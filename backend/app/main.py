"""FastAPI app factory: routers, CORS, rate limit, error shape (PRD §11.1)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import coordinator, health, scenarios, voice
from app.config import get_settings
from app.services import jobs, scenario, sitrep  # noqa: F401 - register worker handlers
from app.sim import volunteer_bot  # noqa: F401 - registers the bot job
from app.util.errors import AppError
from app.util.logging import get_logger, setup_logging
from app.voice import sessions as voice_sessions  # noqa: F401 - registers kill-switch hook

log = get_logger(__name__)


def client_ip(request: Request) -> str:
    """Client IP for rate limiting (Cloud Run puts the caller first in X-Forwarded-For)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        n = await scenario.recover_on_startup()
        if n:
            log.info("startup recovery", extra={"job": f"{n} cases re-enqueued"})
    except Exception:  # noqa: BLE001 - never block startup
        log.exception("startup recovery failed")
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    s = get_settings()
    setup_logging(s.LOG_LEVEL)
    app = FastAPI(title="LastMile API", version=s.VERSION, lifespan=lifespan)

    limiter = Limiter(
        key_func=client_ip, default_limits=[f"{s.RATE_LIMIT_PER_MIN}/minute"], application_limits=[]
    )
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.allowed_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Demo-Passcode"],
    )

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return _error(
            422,
            "VALIDATION_ERROR",
            "Invalid request",
            {"errors": [e.get("msg") for e in exc.errors()]},
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limited(_: Request, exc: RateLimitExceeded):
        return _error(429, "RATE_LIMITED", "Too many requests")

    @app.exception_handler(Exception)
    async def internal(_: Request, exc: Exception):
        log.exception("unhandled error")
        return _error(500, "INTERNAL", "Internal error")

    app.include_router(health.router)
    app.include_router(scenarios.router)
    app.include_router(coordinator.router)
    app.include_router(voice.router)
    app.include_router(voice.ws_router)
    return app


app = create_app()
