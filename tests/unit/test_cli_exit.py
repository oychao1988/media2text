from media2text.core.cli_exit import exit_for_result
from media2text.core.exit_codes import EXIT_AUTH, EXIT_OK, EXIT_PARSE, EXIT_PARTIAL


def test_exit_for_result_ok() -> None:
    assert exit_for_result({"ok": True}) == EXIT_OK


def test_exit_for_result_auth() -> None:
    assert exit_for_result({"ok": False, "auth_required": True}) == EXIT_AUTH


def test_exit_for_result_platform_changed() -> None:
    assert exit_for_result({"ok": False, "platform_changed": True}) == EXIT_PARSE


def test_exit_for_result_partial() -> None:
    assert exit_for_result({"ok": False}) == EXIT_PARTIAL
