from __future__ import annotations

from dataclasses import dataclass, field
from subprocess import Popen

from media2text.core.live.streaming_stt import StreamingSttSession


@dataclass
class SessionRuntime:
    """SR-01/02: in-process sidecar state shared by all LiveRecordingCore instances."""

    processes: dict[str, Popen] = field(default_factory=dict)
    stt_sessions: dict[str, StreamingSttSession] = field(default_factory=dict)
