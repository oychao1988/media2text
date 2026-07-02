from __future__ import annotations

from pathlib import Path

from media2text.core.config import AppConfig
from media2text.core.desktop_runtime import (
    bundled_tool,
    ensure_ffmpeg_config,
    pip_install_target_writable,
    resolve_ffmpeg_path,
)


def test_resolve_ffmpeg_from_bundled_bin(tmp_path, monkeypatch) -> None:
    root = tmp_path / "runtime"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    ffmpeg_bin = bin_dir / "ffmpeg.bin"
    ffmpeg_bin.write_bytes(b"fake")
    monkeypatch.setenv("M2T_PROJECT_ROOT", str(root))
    monkeypatch.setenv("M2T_DESKTOP_MANAGED", "1")
    cfg = AppConfig()
    resolved = resolve_ffmpeg_path(cfg)
    assert resolved is not None
    assert resolved.endswith("/bin/ffmpeg")
    assert Path(resolved).is_file()


def test_ensure_ffmpeg_config_updates_yaml(tmp_path, monkeypatch) -> None:
    root = tmp_path / "runtime"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    ffmpeg_bin = bin_dir / "ffmpeg.bin"
    ffmpeg_bin.write_bytes(b"fake")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("workspace: ./data\nlive:\n  ffmpeg_path: ffmpeg\n", encoding="utf-8")
    monkeypatch.setenv("M2T_PROJECT_ROOT", str(root))
    monkeypatch.setenv("M2T_DESKTOP_MANAGED", "1")
    monkeypatch.setenv("MEDIA2TEXT_CONFIG", str(cfg_path))
    cfg = AppConfig.load()
    ensure_ffmpeg_config(cfg)
    reloaded = AppConfig.load()
    assert reloaded.live.ffmpeg_path.endswith("/bin/ffmpeg")


def test_bundled_tool_missing_when_no_root(monkeypatch) -> None:
    monkeypatch.delenv("M2T_PROJECT_ROOT", raising=False)
    assert bundled_tool("ffmpeg") is None


def test_pip_install_target_writable_in_temp_venv(tmp_path, monkeypatch) -> None:
    import site
    import sys

    venv = tmp_path / ".venv"
    site_dir = venv / "lib/python3.12/site-packages"
    site_dir.mkdir(parents=True)
    monkeypatch.setenv("VIRTUAL_ENV", str(venv))
    monkeypatch.setattr("site.getsitepackages", lambda: [str(site_dir)])
    monkeypatch.setattr(sys, "prefix", str(venv))
    assert pip_install_target_writable() is True
