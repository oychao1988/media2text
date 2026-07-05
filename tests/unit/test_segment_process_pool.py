"""Segment manifest repos route mutations through DbWriteGateway (DL-4c)."""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from media2text.core.config import AppConfig, MonitorWriteGatewayConfig
from media2text.core.live.segment_manifest import SegmentManifestRepo, SegmentProcessJobRepo
from media2text.core.storage import write_gateway as wg_mod
from media2text.core.storage.repos import CreatorRepo, LiveSessionRepo
from media2text.core.storage.write_gateway import ensure_write_gateway_started, shutdown_write_gateway
from media2text.core.workspace import open_db


@pytest.fixture(autouse=True)
def _reset_gateway() -> None:
    shutdown_write_gateway()
    wg_mod._gateway = None
    yield
    shutdown_write_gateway()
    wg_mod._gateway = None


def test_segment_manifest_upsert_uses_gateway(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsegw",
        profile_url="https://x",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn, cfg=cfg).create(
        creator_id=cid,
        room_id="1",
        temp_path="/tmp/x.m3u8",
        session_dir="/tmp/session",
        pipeline_mode="streaming",
    )
    repo = SegmentManifestRepo(conn, cfg=cfg)
    calls: list[str] = []
    original = repo._mutate

    def track(label: str, fn):
        calls.append(label)
        return original(label, fn)

    monkeypatch.setattr(repo, "_mutate", track)
    repo.upsert_part(
        session_id=sid,
        part_index=1,
        rel_path="parts/seg-00001.m4s",
        state="recording",
    )
    assert calls == ["segment_manifest.upsert_part"]


def test_segment_process_job_enqueue_uses_gateway(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    cfg.monitor.write_gateway = MonitorWriteGatewayConfig(shutdown_drain_sec=2.0)
    ensure_write_gateway_started(cfg)
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="MS4wLjABAAAAsegj",
        profile_url="https://x",
        monitor_enabled=True,
    )
    sid = LiveSessionRepo(conn, cfg=cfg).create(
        creator_id=cid,
        room_id="1",
        temp_path="/tmp/x.m3u8",
        session_dir="/tmp/session",
        pipeline_mode="streaming",
    )
    jobs = SegmentProcessJobRepo(conn, cfg=cfg)
    calls: list[str] = []
    original = jobs._mutate

    def track(label: str, fn):
        calls.append(label)
        return original(label, fn)

    monkeypatch.setattr(jobs, "_mutate", track)
    job_id = jobs.enqueue(session_id=sid, part_index=1)
    assert job_id
    assert calls == ["segment_job.enqueue"]
