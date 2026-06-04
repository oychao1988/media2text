from media2text.core.config import AppConfig
from media2text.core.desktop.auto_record import effective_auto_record
from media2text.core.storage.models import CreatorRow


def _creator(override: str = "inherit") -> CreatorRow:
    return CreatorRow(
        id="c1",
        platform="douyin",
        sec_uid="s1",
        display_name="t",
        profile_url=None,
        watch_live=0,
        monitor_enabled=1,
        unique_id=None,
        avatar_url=None,
        signature=None,
        follower_count=None,
        profile_synced_at=None,
        created_at="2026-01-01T00:00:00Z",
        auto_record_override=override,
    )


def test_inherit_follows_global() -> None:
    cfg = AppConfig.model_validate({"live": {"auto_record": False}})
    assert effective_auto_record(_creator("inherit"), cfg) is False
    cfg2 = AppConfig.model_validate({"live": {"auto_record": True}})
    assert effective_auto_record(_creator("inherit"), cfg2) is True


def test_override_on_off() -> None:
    cfg = AppConfig.model_validate({"live": {"auto_record": False}})
    assert effective_auto_record(_creator("on"), cfg) is True
    assert effective_auto_record(_creator("off"), cfg) is False
