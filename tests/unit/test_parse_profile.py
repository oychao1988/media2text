import json
from pathlib import Path

from media2text.core.platform.douyin.parse import parse_user_profile

FIXTURE = Path(__file__).resolve().parents[2] / "src/media2text/core/platform/douyin/fixtures/user_profile_detail.json"


def test_parse_user_profile_fixture() -> None:
    payload = json.loads(FIXTURE.read_text())
    profile = parse_user_profile(payload)
    assert profile.display_name == "测试博主"
    assert profile.unique_id == "test_creator"
    assert profile.avatar_url == "https://example.com/avatar.jpg"
    assert profile.signature == "fixture profile"
    assert profile.follower_count == 12345
