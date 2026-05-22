import json

import pytest

from media2text.core.config import AppConfig
from media2text.core.errors import ParseFailed, PlatformChanged
from media2text.core.platform.bilibili.adapter import BilibiliAdapterV1, FIXTURE_ROOT
from media2text.core.platform.bilibili.archive_fallback import (
    list_awemes_from_dynamics_workspace,
)
from media2text.core.platform.bilibili.catalog import build_adapter, sync_creator
from media2text.core.platform.bilibili.dedupe import register_bvid
from media2text.core.platform.bilibili.parse import (
    parse_arc_search_list,
    parse_archive_cursor_list,
)
from media2text.core.storage.repos import AwemeRepo, CreatorRepo
from media2text.core.workspace import open_db

FIXTURES = FIXTURE_ROOT


def test_parse_arc_search_list_from_fixture() -> None:
    payload = json.loads((FIXTURES / "arc_search.json").read_text())
    items, next_cursor, has_more = parse_arc_search_list(payload)
    assert len(items) == 2
    assert items[0].aweme_id == "BV1fixture001"
    assert next_cursor == "2"
    assert has_more is True


def test_parse_archive_cursor_list_from_fixture() -> None:
    payload = json.loads((FIXTURES / "archive_cursor.json").read_text())
    items, next_cursor, has_more = parse_archive_cursor_list(payload)
    assert len(items) == 2
    assert items[0].aweme_id == "BV1fixture001"
    assert items[0].title == "Fixture archive one"
    assert items[0].create_time == 1710518403
    assert next_cursor == "100002"
    assert has_more is True


def test_parse_archive_cursor_skips_non_av_entries() -> None:
    payload = {
        "code": 0,
        "data": {
            "has_next": False,
            "item": [
                {"goto": "article", "bvid": "BVskip"},
                {"goto": "av", "bvid": "BV1ok", "param": "1", "ctime": 1, "title": "ok"},
            ],
        },
    }
    items, _, _ = parse_archive_cursor_list(payload)
    assert len(items) == 1
    assert items[0].aweme_id == "BV1ok"


def test_adapter_list_awemes_fixture_pagination() -> None:
    adapter = BilibiliAdapterV1(None, fixture_root=FIXTURE_ROOT)
    page1, cursor, more = adapter.list_awemes(sec_uid="12345")
    assert len(page1) == 2
    assert more is True
    assert cursor == "2"
    page2, cursor2, more2 = adapter.list_awemes(sec_uid="12345", max_cursor=cursor or "")
    assert len(page2) == 1
    assert page2[0].aweme_id == "BV1fixture003"
    assert more2 is False
    assert cursor2 is None


def test_adapter_platform_changed_fixture() -> None:
    adapter = BilibiliAdapterV1(None, fixture_root=FIXTURE_ROOT)
    with pytest.raises(PlatformChanged):
        adapter.check_platform_changed_fixture()


def test_adapter_resolve_download_url_fixture() -> None:
    adapter = BilibiliAdapterV1(None, fixture_root=FIXTURE_ROOT)
    url = adapter.resolve_download_url(aweme_id="BV1fixture001")
    assert url == "https://example.com/bilibili-fixture-video.mp4"


def test_sync_creator_dynamics_fallback_on_rate_limit(tmp_path, monkeypatch) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    sec_uid = "777"
    cid = CreatorRepo(conn).add(
        sec_uid=sec_uid,
        profile_url=f"https://space.bilibili.com/{sec_uid}",
        platform="bilibili",
    )
    dyn = cfg.ensure_workspace() / "creators" / sec_uid / "dynamics" / "1"
    dyn.mkdir(parents=True)
    (dyn / "meta.json").write_text(
        json.dumps({"published_at": "2026-01-01T00:00:00+00:00", "refs": {"bvid": "BV1fallback"}}),
        encoding="utf-8",
    )

    def _rate_limited(self, **kwargs):  # noqa: ANN001, ARG001
        raise ParseFailed("bilibili api code -799: 请求过于频繁，请稍后再试")

    monkeypatch.setattr(BilibiliAdapterV1, "list_awemes", _rate_limited)
    result = sync_creator(cfg, cid)
    assert result["ok"] is True
    assert result.get("dynamics_fallback") is True
    assert result["total_listed"] == 1
    row = conn.execute(
        "SELECT aweme_id FROM awemes WHERE creator_id = ?", (cid,)
    ).fetchone()
    assert row[0] == "BV1fallback"


def test_sync_creator_upserts_bvids(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    cid = CreatorRepo(conn).add(
        sec_uid="999",
        profile_url="https://space.bilibili.com/999",
        platform="bilibili",
    )
    result = sync_creator(cfg, cid)
    assert result["ok"] is True
    assert result["new_count"] == 3
    assert result["total_listed"] == 3
    rows = conn.execute("SELECT aweme_id FROM awemes WHERE creator_id = ?", (cid,)).fetchall()
    assert {r[0] for r in rows} == {
        "BV1fixture001",
        "BV1fixture002",
        "BV1fixture003",
    }


def test_register_bvid_dedupes(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    conn = open_db(cfg)
    creators = CreatorRepo(conn)
    awemes = AwemeRepo(conn)
    cid = creators.add(
        sec_uid="888",
        profile_url="https://space.bilibili.com/888",
        platform="bilibili",
    )
    assert register_bvid(awemes, creator_id=cid, bvid="BV1dedupe", title="first") is True
    assert register_bvid(awemes, creator_id=cid, bvid="BV1dedupe", title="second") is False
    assert conn.execute("SELECT COUNT(*) FROM awemes WHERE creator_id = ?", (cid,)).fetchone()[0] == 1


def test_build_adapter_uses_fixture_without_session(tmp_path) -> None:
    cfg = AppConfig(workspace=tmp_path / "data")
    adapter = build_adapter(cfg)
    items, _, _ = adapter.list_awemes(sec_uid="1")
    assert len(items) >= 1


def test_list_awemes_from_dynamics_workspace(tmp_path) -> None:
    root = tmp_path / "creators" / "123"
    dyn = root / "dynamics" / "999"
    dyn.mkdir(parents=True)
    (dyn / "meta.json").write_text(
        json.dumps(
            {
                "published_at": "2026-03-12T08:43:16+00:00",
                "refs": {"bvid": "BV1fromdyn"},
            }
        ),
        encoding="utf-8",
    )
    (dyn / "content.md").write_text("# Dynamic title\n", encoding="utf-8")
    items = list_awemes_from_dynamics_workspace(root)
    assert len(items) == 1
    assert items[0].aweme_id == "BV1fromdyn"
    assert items[0].title == "Dynamic title"
    assert items[0].create_time is not None
