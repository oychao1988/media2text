from media2text.core.config import AppConfig
from media2text.core.doctor_checks import build_doctor_report
from media2text.core.storage.db import connect


def test_doctor_warns_when_live_pipeline_legacy(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live={"pipeline_mode": "legacy"})
    ws = cfg.ensure_workspace()
    conn = connect(ws / "media2text.db")

    report = build_doctor_report(cfg, conn)

    codes = [w["code"] for w in report.get("warnings", [])]
    assert "live_pipeline_deprecated" in codes
    legacy = next(w for w in report["warnings"] if w["code"] == "live_pipeline_deprecated")
    assert "streaming" in legacy["hint"]
    assert "hls" in legacy["hint"]


def test_doctor_no_legacy_warning_for_streaming(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data", live={"pipeline_mode": "streaming"})
    ws = cfg.ensure_workspace()
    conn = connect(ws / "media2text.db")

    report = build_doctor_report(cfg, conn)

    codes = [w["code"] for w in report.get("warnings", [])]
    assert "live_pipeline_deprecated" not in codes


def test_doctor_warns_fake_monitor_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = AppConfig(workspace=tmp_path / "data")
    ws = cfg.ensure_workspace()
    (ws / ".monitor-watch.lock").write_text("581", encoding="utf-8")
    conn = connect(ws / "media2text.db")
    monkeypatch.setattr(
        "media2text.core.runtime.monitor_lock.is_monitor_watch_pid",
        lambda pid: False,
    )

    report = build_doctor_report(cfg, conn)

    assert report["monitor_lock_valid"] is False
    assert report["monitor_lock_pid"] == 581
    codes = [w["code"] for w in report.get("warnings", [])]
    assert "monitor_lock_pid_mismatch" in codes
