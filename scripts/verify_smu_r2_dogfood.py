#!/usr/bin/env python3
"""SMU-R2 dogfood verification for session 20260611T110019Z (Issue #296 Task 2.6).

Uses real workspace + DB; temporarily moves media files aside and restores them.
Exit 0 on PASS, 1 on failure.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from media2text.api.app import create_app
from media2text.api.deps import get_cfg, get_db
from media2text.core.config import AppConfig
from media2text.core.workspace import open_db

SESSION_ID = "64cd09e0-e249-4b0e-9bb6-33f4c7131397"
SESSION_DIR = Path(
    "data/creators/MS4wLjABAAAAvOVYmHtxbIkHL6FLKewVaMeTD5rQ3CAwWMY3l4m3uNU/live/20260611T110019Z"
)


@contextmanager
def _api_client():
    cfg = AppConfig.load()
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


@contextmanager
def _moved_aside(path: Path):
    if not path.exists() and not path.is_symlink():
        yield False
        return
    backup = Path(tempfile.mkdtemp()) / path.name
    if path.is_symlink():
        path.unlink()
    else:
        shutil.move(path, backup)
    try:
        yield True
    finally:
        if backup.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(backup, path)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    session_dir = (root / SESSION_DIR).resolve()
    if not session_dir.is_dir():
        print(f"SKIP: dogfood session dir missing: {session_dir}")
        return 0

    cfg = AppConfig.load()
    if not cfg.aliyundrive.enabled:
        print("FAIL: aliyundrive.enabled must be true for cloud dogfood checks")
        return 1
    if not cfg.aliyundrive_token_path().is_file():
        print("FAIL: aliyundrive token missing")
        return 1

    failures: list[str] = []

    with _api_client() as client:
        r = client.get(f"/api/sessions/{SESSION_ID}/playback.m3u8")
        if r.status_code != 200:
            failures.append(f"playback.m3u8 local master: expected 200 got {r.status_code}")
        elif "#EXT-X-DISCONTINUITY" not in r.text:
            failures.append("playback.m3u8 missing #EXT-X-DISCONTINUITY")
        elif f"/api/sessions/{SESSION_ID}/parts/1" not in r.text:
            failures.append("playback.m3u8 missing rewritten part/1 URI")
        else:
            print("PASS: local master.m3u8 200 + discontinuity + part rewrite")

        master = session_dir / "master.m3u8"
        with _moved_aside(master) as moved:
            if not moved:
                failures.append("master.m3u8 not found for cloud fallback test")
            else:
                r_cloud = client.get(f"/api/sessions/{SESSION_ID}/playback.m3u8")
                if r_cloud.status_code != 200:
                    failures.append(
                        f"cloud master fallback: expected 200 got {r_cloud.status_code}"
                    )
                elif "#EXTM3U" not in r_cloud.text:
                    failures.append("cloud master playlist missing #EXTM3U")
                elif f"/api/sessions/{SESSION_ID}/parts/" not in r_cloud.text:
                    failures.append("cloud master playlist missing rewritten part URI")
                else:
                    note = ""
                    if "#EXT-X-DISCONTINUITY" not in r_cloud.text:
                        note = " (cloud master predates DISCONTINUITY tags; local master has them)"
                    print(f"PASS: cloud master fallback 200 + part rewrite{note}")

        for part_index in (1, 2):
            part_path = session_dir / "parts" / f"seg-{part_index:05d}.m4s"
            with _moved_aside(part_path) as moved:
                if not moved:
                    failures.append(f"part {part_index} file missing for cloud proxy test")
                    continue
                r_part = client.get(
                    f"/api/sessions/{SESSION_ID}/parts/{part_index}",
                    headers={"Range": "bytes=0-1023"},
                )
                if r_part.status_code not in (200, 206):
                    failures.append(
                        f"part {part_index} cloud proxy: expected 200/206 got {r_part.status_code}"
                    )
                elif r_part.headers.get("location"):
                    failures.append(f"part {part_index} returned 302 redirect (expected proxy)")
                elif not r_part.content:
                    failures.append(f"part {part_index} cloud proxy returned empty body")
                else:
                    print(
                        f"PASS: part {part_index} cloud Range proxy "
                        f"{r_part.status_code} len={len(r_part.content)}"
                    )

    if failures:
        for msg in failures:
            print(f"FAIL: {msg}")
        return 1
    print("SMU-R2 dogfood: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
