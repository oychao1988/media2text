import time

import pytest

from media2text.api.schemas.events import EventType
from media2text.api.services import runtime_health_loop as loop
from media2text.api.services.events_hub import events_hub

pytestmark = pytest.mark.desktop


def test_runtime_ws_diff_detects_health_change() -> None:
    prev = loop.runtime_ws_payload(
        {
            "health": "healthy",
            "health_reasons": [],
            "managed_by": "embedded",
            "daemon": {"running": True, "tick_age_sec": 1.0},
            "recordings": {"active_count": 0},
            "queues": {"post_process": {"pending": 0}},
            "observability": {"snapshots_stale_count": 0},
        }
    )
    curr = loop.runtime_ws_payload(
        {
            "health": "degraded",
            "health_reasons": ["live tick stale"],
            "managed_by": "embedded",
            "daemon": {"running": True, "tick_age_sec": 45.0},
            "recordings": {"active_count": 0},
            "queues": {"post_process": {"pending": 0}},
            "observability": {"snapshots_stale_count": 1},
        }
    )
    diff = loop.runtime_ws_diff(prev, curr)
    assert diff is not None
    assert diff["health"] == "degraded"


def test_runtime_ws_diff_unchanged_returns_none() -> None:
    payload = loop.runtime_ws_payload(
        {
            "health": "healthy",
            "health_reasons": [],
            "managed_by": "embedded",
            "daemon": {"running": True},
            "recordings": {"active_count": 1},
            "queues": {"post_process": {"pending": 0}},
            "observability": {},
        }
    )
    assert loop.runtime_ws_diff(payload, payload) is None


def test_drain_runtime_health_publishes_diff(monkeypatch, tmp_path) -> None:
    from fastapi import FastAPI

    from media2text.core.config import AppConfig

    published: list[dict] = []
    monkeypatch.setattr(events_hub, "publish", lambda msg: published.append(msg))

    cfg = AppConfig(workspace=tmp_path)
    app = FastAPI()
    app.state.supervisor = None

    full = {
        "health": "healthy",
        "health_reasons": [],
        "managed_by": "embedded",
        "daemon": {"running": True, "tick_age_sec": 2.0, "live_poll_interval_sec": 20},
        "recordings": {"active_count": 0, "items": []},
        "queues": {
            "post_process": {"pending": 1, "running": 0, "max_workers": 2},
            "monitor_tasks": {
                "pending": 0,
                "running": 0,
                "failed_total": 0,
                "failed_recent_24h": 0,
                "dlq": 0,
            },
        },
        "observability": {"snapshots_stale_count": 0, "monitored_creators": 0},
    }

    monkeypatch.setattr(
        "media2text.api.services.runtime_health_loop.get_runtime_status",
        lambda _cfg, _sup: full,
    )

    prev, ts = loop.drain_runtime_health_once(
        app,
        cfg,
        prev_payload=None,
        last_publish_at=0.0,
        heartbeat_sec=30.0,
    )
    assert prev["health"] == "healthy"
    assert any(p["type"] == EventType.RUNTIME_HEALTH.value for p in published)

    published.clear()
    full2 = {**full, "queues": {**full["queues"], "post_process": {"pending": 2, "running": 0, "max_workers": 2}}}
    monkeypatch.setattr(
        "media2text.api.services.runtime_health_loop.get_runtime_status",
        lambda _cfg, _sup: full2,
    )
    loop.drain_runtime_health_once(
        app,
        cfg,
        prev_payload=prev,
        last_publish_at=ts,
        heartbeat_sec=30.0,
    )
    assert any(p["type"] == EventType.QUEUE_UPDATED.value for p in published)


def test_drain_runtime_health_heartbeat(monkeypatch, tmp_path) -> None:
    from fastapi import FastAPI

    from media2text.core.config import AppConfig

    published: list[dict] = []
    monkeypatch.setattr(events_hub, "publish", lambda msg: published.append(msg))

    cfg = AppConfig(workspace=tmp_path)
    app = FastAPI()
    full = {
        "health": "stopped",
        "health_reasons": ["monitor not running"],
        "managed_by": "none",
        "daemon": {"running": False},
        "recordings": {"active_count": 0, "items": []},
        "queues": {
            "post_process": {"pending": 0, "running": 0, "max_workers": 2},
            "monitor_tasks": {
                "pending": 0,
                "running": 0,
                "failed_total": 0,
                "failed_recent_24h": 0,
                "dlq": 0,
            },
        },
        "observability": {"snapshots_stale_count": 0, "monitored_creators": 0},
    }
    monkeypatch.setattr(
        "media2text.api.services.runtime_health_loop.get_runtime_status",
        lambda _cfg, _sup: full,
    )
    prev = loop.runtime_ws_payload(full)
    loop.drain_runtime_health_once(
        app,
        cfg,
        prev_payload=prev,
        last_publish_at=time.monotonic() - 60.0,
        heartbeat_sec=30.0,
    )
    assert any(p["type"] == EventType.RUNTIME_HEALTH.value for p in published)
