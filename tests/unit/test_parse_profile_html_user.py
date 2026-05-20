import json
from pathlib import Path

from media2text.core.platform.douyin.parse import parse_profile_html_user

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "src/media2text/core/platform/douyin/fixtures/render_data_profile_page.json"
)
TARGET_SEC = "MS4wLjABAAAA3OaCljcu8R1Q3ilE7Q5QEqIut554fV4jhL9imnsfof0"


def test_parse_profile_html_user_ignores_logged_in_session() -> None:
    payload = json.loads(FIXTURE.read_text())
    profile = parse_profile_html_user(payload, sec_uid=TARGET_SEC)
    assert profile is not None
    assert profile.display_name == "目标博主"
    assert profile.unique_id == "target_creator"
    assert profile.follower_count == 999


def test_parse_profile_html_user_returns_none_when_sec_uid_missing() -> None:
    payload = json.loads(FIXTURE.read_text())
    assert parse_profile_html_user(payload, sec_uid="MS4wLjABAAAAunknown") is None
