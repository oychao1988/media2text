import pytest
import yaml


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "data"
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({"workspace": str(ws)}), encoding="utf-8")
    monkeypatch.setenv("MEDIA2TEXT_CONFIG", str(cfg_path))
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "sessions").mkdir(exist_ok=True)
    (ws / "creators").mkdir(exist_ok=True)
    return ws
