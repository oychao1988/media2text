import json

from media2text.core.runtime import monitor_log


def test_sink_records_to_ring_and_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(monitor_log, "_ring", monitor_log.deque(maxlen=500))
    monkeypatch.setattr(monitor_log, "_sink_active", False)
    monkeypatch.setattr(monitor_log, "_log_path", None)

    path = monitor_log.prepare_sink(tmp_path)
    monitor_log.record_event_dict(
        {"event": "live_tick", "active_recordings": 1, "timestamp": "2026-06-05T10:00:00Z"}
    )

    assert monitor_log.is_sink_active()
    lines = monitor_log.tail_lines(tail=5)
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "live_tick"
    file_text = path.read_text(encoding="utf-8")
    assert "live_tick" in file_text


def test_tail_prefers_ring_over_stale_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(monitor_log, "_ring", monitor_log.deque(maxlen=500))
    monkeypatch.setattr(monitor_log, "_sink_active", False)
    monkeypatch.setattr(monitor_log, "_log_path", None)

    log_path = tmp_path / "monitor-watch.log"
    log_path.write_text('{"event":"old"}\n', encoding="utf-8")
    monitor_log.prepare_sink(tmp_path)
    monitor_log.record_event_dict({"event": "live_tick", "active_recordings": 0})

    lines = monitor_log.tail_lines(tail=5, log_path=log_path)
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "live_tick"
