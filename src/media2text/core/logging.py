import logging
import os
from pathlib import Path

import structlog

from media2text.core.runtime.monitor_log import structlog_sink_processor

# Embedded serve: console sink goes to devnull (Tauri sidecar stdout may be closed).
_EMBEDDED_LOG_FILE = open(os.devnull, "w")


def _processors(*, with_monitor_sink: bool) -> list:
    chain: list = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.format_exc_info,
    ]
    if with_monitor_sink:
        chain.append(structlog_sink_processor)
    chain.append(structlog.processors.JSONRenderer())
    return chain


def configure_logging() -> None:
    structlog.configure(
        processors=_processors(with_monitor_sink=False),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


def enable_monitor_log_sink(workspace: Path) -> Path:
    """Tee structlog JSON lines to ``monitor-watch.log`` + in-memory ring (embedded serve)."""
    from media2text.core.runtime.monitor_log import prepare_sink

    path = prepare_sink(workspace)
    structlog.configure(
        processors=_processors(with_monitor_sink=True),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=_EMBEDDED_LOG_FILE),
    )
    return path
