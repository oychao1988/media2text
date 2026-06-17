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


def test_parse_profile_html_offline_render_data_ignores_recommended_live_link() -> None:
    """Profile page may embed a promoted live link while user is offline."""
    html = (
        '<script id="RENDER_DATA" type="application/json">'
        "%7B%22app%22%3A%7B%22user%22%3A%7B%22info%22%3A%7B"
        "%22room_id%22%3A0%2C%22room_id_str%22%3A%220%22%2C%22live_status%22%3A0"
        "%7D%7D%7D%7D"
        "</script>"
        '<a href="https://live.douyin.com/45865776?action_type=click">KPL</a>'
    )
    info = parse_profile_html(html)
    assert info.is_live is False
    assert info.room_id is None
