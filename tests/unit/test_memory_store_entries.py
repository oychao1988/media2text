import pytest

from media2text.agent.memory_store import MemoryStore
from media2text.core.config import AppConfig

pytestmark = pytest.mark.agent


def test_add_entry_uses_section_delimiter(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    store = MemoryStore(cfg)
    store.add("memory", "likes blue widgets")
    raw = (tmp_path / "data" / ".agent" / "MEMORY.md").read_text(encoding="utf-8")
    assert raw.startswith("§")
    assert "likes blue widgets" in raw


def test_replace_unique_match(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    store = MemoryStore(cfg)
    store.add("memory", "alpha")
    store.add("memory", "beta")
    store.replace("memory", old_text="alpha", content="alpha revised")
    entries = store.list_entries("memory")
    assert any("alpha revised" in e for e in entries)
    assert not any(e.strip() == "alpha" for e in entries)


def test_legacy_whole_file_normalized_on_add(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    path = tmp_path / "data" / ".agent" / "MEMORY.md"
    path.parent.mkdir(parents=True)
    path.write_text("- evolve bullet one\n- evolve bullet two", encoding="utf-8")
    store = MemoryStore(cfg)
    store.add("memory", "new fact")
    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("§")
    assert "new fact" in raw
    assert "evolve bullet one" in raw
