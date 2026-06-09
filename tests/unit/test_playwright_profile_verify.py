from media2text.core.platform.douyin.playwright_client import _is_verify_challenge_page


def test_verify_challenge_detects_captcha_intermediate_title() -> None:
    html = "<html><head><title>验证码中间页</title></head><body></body></html>"
    assert _is_verify_challenge_page(html)


def test_verify_challenge_ignores_normal_profile_html() -> None:
    html = "<html><head><title>产品老曾</title></head><body>RENDER_DATA</body></html>"
    assert not _is_verify_challenge_page(html)
