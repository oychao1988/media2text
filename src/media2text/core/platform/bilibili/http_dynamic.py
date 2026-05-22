from __future__ import annotations

import httpx

from media2text.core.platform.bilibili.models_dynamic import ParsedDynamic
from media2text.core.platform.bilibili.parse import parse_dynamic_feed

FEED_SPACE_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
FEED_FEATURES = (
    "itemOpusStyle,listOnlyfans,opusBigCover,onlyfansVote,forwardListHidden,"
    "decorationCard,commentsNewVersion,onlyfansAssetsV2,ugcDelete,onlyfansQaCard"
)


def fetch_dynamic_feed_page(
    client: httpx.Client,
    *,
    host_mid: str,
    offset: str = "",
) -> tuple[list[ParsedDynamic], str | None, bool]:
    params: dict[str, str] = {
        "host_mid": host_mid,
        "features": FEED_FEATURES,
        "timezone_offset": "-480",
    }
    if offset:
        params["offset"] = offset
    response = client.get(FEED_SPACE_URL, params=params)
    response.raise_for_status()
    return parse_dynamic_feed(response.json())
