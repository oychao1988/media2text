EXIT_OK = 0
EXIT_GENERAL = 1
EXIT_AUTH = 2
EXIT_PARSE = 3
EXIT_PARTIAL = 4


def exit_code_for(exc: Exception) -> int:
    from media2text.core.errors import AuthRequired, ParseFailed, PlatformChanged

    if isinstance(exc, AuthRequired):
        return EXIT_AUTH
    if isinstance(exc, (ParseFailed, PlatformChanged)):
        return EXIT_PARSE
    return EXIT_GENERAL
