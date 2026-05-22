from media2text.core.archive.indexer import index_all
from media2text.core.config import AppConfig
from media2text.core.storage.db import connect
from media2text.core.storage.repos import CreatorRepo, DynamicRepo


def test_archive_index_includes_dynamic_content_md(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    ws = cfg.ensure_workspace()
    conn = connect(ws / "media2text.db")
    cid = CreatorRepo(conn).add(
        sec_uid="12345",
        profile_url="https://space.bilibili.com/12345",
        platform="bilibili",
    )
    dyn_dir = ws / "creators" / "12345" / "dynamics" / "dyn_test"
    dyn_dir.mkdir(parents=True)
    body = "动态正文可被 FTS 检索"
    (dyn_dir / "content.md").write_text(body, encoding="utf-8")
    DynamicRepo(conn).upsert_listed(
        creator_id=cid,
        dynamic_id="dyn_test",
        dynamic_type="draw",
        text=body,
        refs_json="{}",
        local_dir="dynamics/dyn_test",
        published_at="2026-01-01T00:00:00+00:00",
    )
    DynamicRepo(conn).mark_synced("dyn_test", image_count=0, text=body)

    stats = index_all(conn, ws, creator_id=cid)
    assert stats.indexed_files == 1
    assert stats.indexed_segments == 1

    row = conn.execute(
        "SELECT text, session_type, session_id FROM transcript_segments"
    ).fetchone()
    assert row is not None
    assert row["session_type"] == "dynamic"
    assert row["session_id"] == "dyn_test"
    assert body in row["text"]
