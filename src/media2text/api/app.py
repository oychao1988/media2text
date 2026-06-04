"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from media2text.api.routes import auth, config, creators, daemon, health, live, media, sessions


def create_app() -> FastAPI:
    app = FastAPI(title="media2text-desktop-api", version="0.1.0")
    api = FastAPI()
    api.include_router(health.router)
    api.include_router(config.router)
    api.include_router(daemon.router)
    api.include_router(creators.router)
    api.include_router(auth.router)
    api.include_router(sessions.router)
    api.include_router(media.router)
    api.include_router(live.router)
    app.mount("/api", api)
    return app
