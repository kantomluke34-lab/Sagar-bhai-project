"""FastAPI application for the production Mechman CRM and WABA webhook."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .api import build_router
from .auth import hash_password
from .campaigns import CampaignScheduler
from .config import Settings
from .database import Database
from .logging_config import configure_logging
from .notifications import NotificationScheduler
from .repository import CRMRepository
from .waba import WABAClient
from .webhook import WebhookProcessor, build_webhook_router

LOGGER = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    settings.validate_web()
    database = Database(settings)
    repository = CRMRepository(database)
    waba = WABAClient(settings)
    processor = WebhookProcessor(settings, repository, waba)
    scheduler = NotificationScheduler(repository, waba, settings.notification_poll_seconds)
    campaign_scheduler = CampaignScheduler(
        repository, waba, settings.media_root, settings.campaign_poll_seconds
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await database.create_schema()
        await repository.seed(settings.admin_username, hash_password(settings.admin_password))
        scheduler.start()
        campaign_scheduler.start()
        if not waba.configured:
            LOGGER.warning("WABA is not fully configured; outbound messaging is disabled")
        try:
            yield
        finally:
            await campaign_scheduler.stop()
            await scheduler.stop()
            await database.dispose()

    app = FastAPI(title="Mechman Sales Meeting CRM", version="3.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.perf_counter()
        event = {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host if request.client else None,
        }
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            LOGGER.exception(
                "request_failed", extra={**event, "duration_ms": duration_ms, "status": 500}
            )
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        level = logging.WARNING if duration_ms >= settings.slow_request_ms else logging.INFO
        logging.getLogger("mechman.access").log(
            level,
            "request_completed",
            extra={**event, "duration_ms": duration_ms, "status": response.status_code},
        )
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(build_router(settings, repository, waba))
    app.include_router(build_webhook_router(settings, processor, waba))
    app.state.settings = settings
    app.state.database = database
    app.state.repository = repository
    app.state.waba = waba

    @app.get("/readyz", include_in_schema=False)
    async def readiness() -> JSONResponse:
        try:
            async with database.session_factory() as session:
                await session.execute(text("SELECT 1"))
            return JSONResponse({"status": "ready", "database": "ok"})
        except Exception:
            LOGGER.exception("readiness_check_failed", extra={"event": "readiness_check"})
            return JSONResponse({"status": "not_ready", "database": "unavailable"}, status_code=503)

    dist = Path(__file__).resolve().parent.parent / "portal" / "dist"
    if dist.exists():
        assets = dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            candidate = dist / path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


def run() -> None:
    settings = Settings.from_environment()
    configure_logging(settings.log_level, settings.log_format)
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run()
