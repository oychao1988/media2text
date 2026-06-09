from media2text.core.platform.douyin.parse import parse_profile_html


def test_parse_profile_html_live_douyin_link() -> None:
    html = (
        '<a href="https://live.douyin.com/628224832373?action_type=click'
        '&room_id=7649404054766291754">live</a>'
    )
    info = parse_profile_html(html)
    assert info.is_live is True
    assert info.web_rid == "628224832373"
    assert info.room_id == "7649404054766291754"


def test_parse_profile_html_live_douyin_link_without_room_id_query() -> None:
    html = '<a href="https://live.douyin.com/10047661734?action_type=click">live</a>'
    info = parse_profile_html(html)
    assert info.is_live is True
    assert info.web_rid == "10047661734"
    assert info.room_id == "10047661734"


def test_parse_profile_html_offline() -> None:
    html = "<html><body>no live here</body></html>"
    info = parse_profile_html(html)
    assert info.is_live is False
    assert info.room_id is None
