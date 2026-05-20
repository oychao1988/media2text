import json
from pathlib import Path

import httpx


def client_from_storage(session_file: Path, *, timeout: float = 30.0) -> httpx.Client:
    data = json.loads(session_file.read_text())
    cookies = {c["name"]: c["value"] for c in data.get("cookies", [])}
    return httpx.Client(
        cookies=cookies,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        },
        timeout=timeout,
        follow_redirects=True,
    )
