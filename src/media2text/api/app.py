"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from media2text.api.cors import install_desktop_cors
from media2text.api.routes import (
    auth,
    chat,
    config,
    creators,
    daemon,
    events,
    health,
    live,
    media,
    sessions,
)
from media2text.api.services.state_event_drain import run_drain_loop
from media2text.core.config import AppConfig


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = AppConfig.load()
    stop = asyncio.Event()
    task = asyncio.create_task(run_drain_loop(cfg, stop))
    yield
    stop.set()
    await task


def create_app() -> FastAPI:
    app = FastAPI(title="media2text-desktop-api", version="0.1.0", lifespan=lifespan)
    install_desktop_cors(app)
    api = FastAPI()
    api.include_router(health.router)
    api.include_router(config.router)
    api.include_router(daemon.router)
    api.include_router(creators.router)
    api.include_router(auth.router)
    api.include_router(sessions.router)
    api.include_router(media.router)
    api.include_router(live.router)
    api.include_router(chat.router)
    api.include_router(events.router)
    app.mount("/api", api)
    return app
