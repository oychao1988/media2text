import os

import media2text.core.config as config_mod
from media2text.core.config import _project_root, load_dotenv_file


def test_project_root_from_cwd_when_site_packages_layout(tmp_path, monkeypatch) -> None:
    fake_site = tmp_path / ".venv/lib/python3.12/site-packages/media2text/core"
    fake_site.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='media2text'\n", encoding="utf-8")
    (tmp_path / ".env").write_text("NVIDIA_API_KEY=test-from-env\n", encoding="utf-8")
    fake_config = fake_site / "config.py"
    fake_config.write_text("# stub\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_mod, "__file__", str(fake_config))

    assert _project_root() == tmp_path.resolve()


def test_load_dotenv_from_cwd_project_root(tmp_path, monkeypatch) -> None:
    fake_site = tmp_path / ".venv/lib/python3.12/site-packages/media2text/core"
    fake_site.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='media2text'\n", encoding="utf-8")
    (tmp_path / ".env").write_text("NVIDIA_API_KEY=test-from-env\n", encoding="utf-8")
    fake_config = fake_site / "config.py"
    fake_config.write_text("# stub\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_mod, "__file__", str(fake_config))
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    loaded = load_dotenv_file()
    assert loaded == tmp_path / ".env"
    assert os.environ.get("NVIDIA_API_KEY") == "test-from-env"
