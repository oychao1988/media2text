from media2text.core.platform.douyin.parse import parse_profile_html


def test_parse_profile_html_live_douyin_link() -> None:
    html = '<a href="https://live.douyin.com/10047661734?action_type=click">live</a>'
    info = parse_profile_html(html)
    assert info.is_live is True
    assert info.room_id == "10047661734"


def test_parse_profile_html_offline() -> None:
    html = "<html><body>no live here</body></html>"
    info = parse_profile_html(html)
    assert info.is_live is False
    assert info.room_id is None
