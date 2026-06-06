import pytest

from media2text.agent.model_tools import handle_function_call, reset_memory_store
from media2text.agent.tools.m2t_handlers import ToolContext
from media2text.agent.tools.registry import ALL_TOOLS, get_tool
from media2text.agent.tools.toolsets import DEFAULT_TOOLSET, tool_names_for_set
from media2text.core.config import AppConfig
from media2text.core.storage.db import connect

pytestmark = pytest.mark.agent


def test_default_toolset_includes_m2t_and_hermes_names() -> None:
    names = tool_names_for_set(DEFAULT_TOOLSET)
    assert "m2t_list_creators" in names
    assert "memory" in names
    assert "m2t_memory" not in names
    assert "session_search" in names


def test_registry_has_thirteen_m2t_tools() -> None:
    m2t = [n for n, t in ALL_TOOLS.items() if t.kind == "m2t"]
    assert len(m2t) == 13


def test_memory_tool_stub_write_read(tmp_path) -> None:
    reset_memory_store()
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    conn = connect(tmp_path / "media2text.db")
    ctx = ToolContext(cfg=cfg, conn=conn)
    write = handle_function_call(
        "memory",
        {"action": "write", "key": "fact", "value": "blue"},
        ctx,
    )
    assert write["ok"] is True
    read = handle_function_call("memory", {"action": "read", "key": "fact"}, ctx)
    assert read["ok"] is True
    assert read["data"]["value"] == "blue"
    conn.close()


def test_unknown_tool_returns_error() -> None:
    cfg = AppConfig.model_validate({"workspace": "./data"})
    ctx = ToolContext(cfg=cfg, conn=object())
    out = handle_function_call("not_a_tool", {}, ctx)
    assert out["ok"] is False
    assert out["error"]["code"] == "UNKNOWN_TOOL"


def test_m2t_list_creators_empty_db(tmp_path) -> None:
    cfg = AppConfig.model_validate({"workspace": str(tmp_path / "data")})
    conn = connect(tmp_path / "media2text.db")
    ctx = ToolContext(cfg=cfg, conn=conn)
    tool = get_tool("m2t_list_creators")
    assert tool is not None
    out = tool.handler(ctx)
    assert out["ok"] is True
    assert out["data"]["creators"] == []
    conn.close()
