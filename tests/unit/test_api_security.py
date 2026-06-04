import pytest
from fastapi import HTTPException

from media2text.api.security import safe_workspace_path

pytestmark = pytest.mark.desktop


def test_rejects_traversal(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    with pytest.raises(HTTPException) as exc:
        safe_workspace_path(ws, "../etc/passwd")
    assert exc.value.status_code == 400


def test_accepts_workspace_relative(tmp_path) -> None:
    ws = tmp_path / "data"
    ws.mkdir()
    (ws / "creators").mkdir()
    p = safe_workspace_path(ws, "creators/x/live/y.flv")
    assert p.is_relative_to(ws.resolve()) or str(p).startswith(str(ws.resolve()))
