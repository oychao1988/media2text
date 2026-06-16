import pytest
from fastapi.testclient import TestClient

from media2text.api.app import create_app
from media2text.api.deps import get_cfg, get_db
from media2text.api.services.health import clear_health_cache
from media2text.core.config import AppConfig
from media2text.core.workspace import open_db


@pytest.fixture
def api_client(workspace, monkeypatch):
    clear_health_cache()
    cfg = AppConfig(
        workspace=workspace,
        desktop={
            "auto_start_monitor": False,
            "monitor_self_heal": False,
        },
    )
    monkeypatch.setattr("media2text.core.config.AppConfig.load", lambda: cfg)
    monkeypatch.setattr(
        "media2text.core.logging.enable_monitor_log_sink",
        lambda _ws: workspace / "monitor-watch.log",
    )
    app = create_app()
    api = app.state.api_app

    def override_cfg() -> AppConfig:
        return cfg

    def override_db():
        conn = open_db(cfg)
        try:
            yield conn
        finally:
            conn.close()

    for target in (app, api):
        target.dependency_overrides[get_cfg] = override_cfg
        target.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client
    for target in (app, api):
        target.dependency_overrides.clear()
