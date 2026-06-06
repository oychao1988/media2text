"""User-facing agent error messages."""

from media2text.agent.agent_errors import user_facing_agent_error


def test_auth_error_message() -> None:
    class AuthenticationError(Exception):
        pass

    msg = user_facing_agent_error(AuthenticationError("401 Unauthorized"))
    assert "认证失败" in msg
    assert "系统配置" in msg
