from __future__ import annotations


class ReconcilerDisabledError(RuntimeError):
    """Raised when daemon starts with monitor.reconciler_enabled=false."""

    MESSAGE = (
        "monitor.reconciler_enabled=false is not supported; "
        "set monitor.reconciler_enabled=true"
    )

    def __init__(self) -> None:
        super().__init__(self.MESSAGE)
