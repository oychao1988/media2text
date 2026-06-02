from pathlib import Path

from media2text.core.summarize.runner import discover_backfill_targets


def test_discover_backfill_missing_summary(tmp_path: Path) -> None:
    live = tmp_path / "creators" / "uid1" / "live"
    live.mkdir(parents=True)
    tpath = live / "20260101_120000.transcript.json"
    tpath.write_text('{"segments": []}', encoding="utf-8")
    (live / "20260101_120000.mp4").write_bytes(b"x")

    found = discover_backfill_targets(tmp_path)
    assert len(found) == 1
    assert found[0].name == "20260101_120000.mp4"


def test_discover_backfill_skips_existing_summary(tmp_path: Path) -> None:
    live = tmp_path / "creators" / "uid1" / "live"
    live.mkdir(parents=True)
    stem = "20260101_120000"
    (live / f"{stem}.transcript.json").write_text('{"segments": []}', encoding="utf-8")
    (live / f"{stem}.mp4").write_bytes(b"x")
    (live / f"{stem}.summary.md").write_text("# ok\n", encoding="utf-8")

    assert discover_backfill_targets(tmp_path) == []


def test_discover_backfill_creator_scope(tmp_path: Path) -> None:
    for uid in ("uid1", "uid2"):
        live = tmp_path / "creators" / uid / "live"
        live.mkdir(parents=True)
        (live / "a.transcript.json").write_text("{}", encoding="utf-8")
        (live / "a.mp4").write_bytes(b"x")

    found = discover_backfill_targets(tmp_path, creator_sec_uid="uid2")
    assert len(found) == 1
    assert "uid2" in str(found[0])
