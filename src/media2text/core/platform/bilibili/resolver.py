import re
from urllib.parse import urlparse

from media2text.core.errors import ParseFailed

_MID_PATH_RE = re.compile(r"/(\d+)(?:/|$)")
_MID_QUERY_RE = re.compile(r"[?&]mid=(\d+)")


def resolve_mid(url: str) -> str:
    """Resolve Bilibili space URL to numeric mid."""
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    if "bilibili.com" not in host and "b23.tv" not in host:
        raise ParseFailed("not a bilibili URL")

    path = parsed.path or ""
    if "space.bilibili.com" in host:
        token = path.strip("/").split("/")[0] if path.strip("/") else ""
        if token.isdigit():
            return token

    if "/space/" in path or path.startswith("/space"):
        match = _MID_PATH_RE.search(path)
        if match:
            return match.group(1)

    if path.startswith("/") and path.count("/") <= 1:
        token = path.strip("/")
        if token.isdigit():
            return token

    query_match = _MID_QUERY_RE.search(parsed.query)
    if query_match:
        return query_match.group(1)

    raise ParseFailed("mid not found in bilibili space URL")
