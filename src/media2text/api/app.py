"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from media2text.api.cors import install_desktop_cors
from media2text.api.routes import (
    agent,
    agent_profiles,
    agent_stream,
    auth,
    chat,
    config,
    creators,
    daemon,
    events,
    health,
    live,
    media,
    monitor_tasks,
    playback,
    post_process,
    runtime,
    sessions,
)
from media2text.api.services.runtime_health_loop import run_runtime_health_loop
from media2text.api.services.notify_event_drain import run_notify_drain_loop
from media2text.api.services.state_event_drain import run_drain_loop
import structlog

from media2text.core.config import AppConfig
from media2text.core.runtime.supervisor import MonitorSupervisor

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from media2text.core.playwright_env import ensure_playwright_browsers_path

    ensure_playwright_browsers_path()
    cfg = AppConfig.load()
    from media2text.core.logging import enable_monitor_log_sink

    enable_monitor_log_sink(cfg.ensure_workspace())
    supervisor = MonitorSupervisor()
    app.state.supervisor = supervisor
    # Mounted ``/api`` sub-app does not inherit parent ``app.state``.
    api_app = getattr(app.state, "api_app", None)
    if api_app is not None:
        api_app.state.supervisor = supervisor
    if cfg.desktop.auto_start_monitor:
        from media2text.core.runtime.monitor_startup import prepare_embedded_monitor_startup

        prepare_embedded_monitor_startup(cfg, supervisor)
    stop = asyncio.Event()
    drain_task = asyncio.create_task(run_drain_loop(cfg, stop, supervisor=supervisor))
    notify_drain_task = asyncio.create_task(
        run_notify_drain_loop(cfg, stop, supervisor=supervisor)
    )
    health_task = asyncio.create_task(run_runtime_health_loop(app, cfg, stop))
    yield
    stop.set()
    supervisor.stop(cfg)
    await asyncio.gather(drain_task, notify_drain_task, health_task)


def create_app() -> FastAPI:
    app = FastAPI(title="media2text-desktop-api", version="0.1.0", lifespan=lifespan)
    install_desktop_cors(app)
    api = FastAPI()
    api.include_router(health.router)
    api.include_router(config.router)
    api.include_router(daemon.router)
    api.include_router(runtime.router)
    api.include_router(creators.router)
    api.include_router(auth.router)
    api.include_router(sessions.router)
    api.include_router(playback.router)
    api.include_router(media.router)
    api.include_router(live.router)
    api.include_router(post_process.router)
    api.include_router(monitor_tasks.router)
    api.include_router(agent.router)
    api.include_router(agent_profiles.router)
    api.include_router(agent_stream.router)
    api.include_router(chat.router)
    api.include_router(events.router)
    app.state.api_app = api
    app.mount("/api", api)
    return app
