import json
from unittest.mock import patch

from typer.testing import CliRunner

from media2text.cli.main import app


def test_creator_add_with_mocked_resolver(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    with patch(
        "media2text.cli.creator.resolve_sec_uid",
        return_value="MS4wLjABAAAAmock",
    ):
        result = runner.invoke(
            app,
            ["creator", "add", "https://www.douyin.com/user/mock", "--json"],
        )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["sec_uid"] == "MS4wLjABAAAAmock"

    list_result = runner.invoke(app, ["creator", "list", "--json"])
    listed = json.loads(list_result.stdout)
    assert len(listed["creators"]) == 1
