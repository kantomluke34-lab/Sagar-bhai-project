"""FastAPI booking and CRM application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import build_router
from .auth import hash_password
from .config import Settings
from .storage import BotStore

LOGGER = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    settings.validate_web()
    settings.ensure_directories()
    store = BotStore(settings.bot_database)
    if store.get_user_by_username(settings.admin_username) is None:
        store.create_admin_if_missing(
            settings.admin_username,
            hash_password(settings.admin_password),
        )
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            store.close()

    app = FastAPI(title="Mechman CRM", version="2.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_private_network=True,
    )
    app.include_router(build_router(settings, store))
    app.state.settings = settings
    app.state.store = store

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
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    uvicorn.run(create_app(settings), host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
