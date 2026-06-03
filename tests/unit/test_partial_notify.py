from unittest.mock import MagicMock

from media2text.core.config import AppConfig, LiveConfig, NotifyConfig, NotifyEventsConfig, StreamingSttConfig
from media2text.core.live.partial_notify import PartialTranscriptNotifier
from media2text.core.notify import EventKind, NotifyService


def test_partial_notify_respects_throttle() -> None:
    cfg = AppConfig(
        notify=NotifyConfig(
            enabled=True,
            events=NotifyEventsConfig(transcribe_partial=True),
        ),
        live=LiveConfig(
            streaming_stt=StreamingSttConfig(
                partial_notify_interval_sec=60,
                partial_notify_min_finals=3,
            )
        ),
    )
    notify = NotifyService(cfg)
    notify.emit = MagicMock()
    gate = PartialTranscriptNotifier(cfg, notify, title="测试")
    gate.maybe_emit("第一句", segment_count=1)
    gate.maybe_emit("第二句", segment_count=2)
    notify.emit.assert_not_called()
    gate.maybe_emit("第三句", segment_count=3)
    notify.emit.assert_called_once()
    assert notify.emit.call_args[0][0].kind == EventKind.TRANSCRIBE_PARTIAL


def test_partial_notify_disabled_by_default() -> None:
    cfg = AppConfig(notify=NotifyConfig(enabled=True))
    notify = NotifyService(cfg)
    notify.emit = MagicMock()
    gate = PartialTranscriptNotifier(cfg, notify, title="测试")
    gate.maybe_emit("hello", segment_count=10)
    notify.emit.assert_not_called()
