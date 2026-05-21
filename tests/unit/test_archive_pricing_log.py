import json

from media2text.core.archive.pricing import append_pricing_log, pricing_log_path


def test_append_pricing_log_creates_jsonl(tmp_path) -> None:
    ws = tmp_path / "data"
    entry = append_pricing_log(
        ws,
        would_pay_99_cny=True,
        note="复盘后愿付",
        creator_id="c1",
        session_id="s1",
    )
    path = pricing_log_path(ws)
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["ts"] == entry.ts
    assert row["would_pay_99_cny"] is True
    assert row["note"] == "复盘后愿付"
    assert row["creator_id"] == "c1"
    assert row["session_id"] == "s1"

    append_pricing_log(ws, would_pay_99_cny=False, note=None)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["would_pay_99_cny"] is False
