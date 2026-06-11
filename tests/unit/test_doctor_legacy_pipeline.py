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
