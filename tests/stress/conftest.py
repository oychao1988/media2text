"""Pre-import API stack so scheduler/watcher imports resolve in stress tests."""

from media2text.api.app import create_app

create_app()
