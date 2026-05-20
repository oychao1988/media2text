import re
from urllib.parse import urlparse

import httpx

from media2text.core.errors import ParseFailed

_SEC_UID_RE = re.compile(r'"sec_uid"\s*:\s*"([^"]+)"')
_SEC_UID_PATH_RE = re.compile(r"/user/([^/?#]+)")


def resolve_sec_uid(url: str, client: httpx.Client | None = None) -> str:
    parsed = urlparse(url)
    if parsed.path.startswith("/user/"):
        match = _SEC_UID_PATH_RE.search(parsed.path)
        if match:
            token = match.group(1)
            if token.startswith("MS4w"):
                return token

    if client is None:
        raise ParseFailed("HTTP client required to resolve sec_uid from URL")

    response = client.get(url)
    response.raise_for_status()
    match = _SEC_UID_RE.search(response.text)
    if not match:
        raise ParseFailed("sec_uid not found in profile page")
    return match.group(1)
