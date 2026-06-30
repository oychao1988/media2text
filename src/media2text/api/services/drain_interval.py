"""Resolve outbox drain interval for embedded vs external monitor ownership."""

from __future__ import annotations

from media2text.core.config import AppConfig
from media2text.core.runtime.supervisor import MonitorSupervisor

_DEFAULT_DRAIN_INTERVAL_SEC = 1.5


def resolve_drain_interval_sec(
    cfg: AppConfig,
    *,
    supervisor: MonitorSupervisor | None = None,
) -> float:
    if supervisor is not None:
        managed_by = supervisor.status_dict(cfg).get("managed_by")
        if managed_by == "external":
            return float(cfg.desktop.external_drain_interval_sec)
    return _DEFAULT_DRAIN_INTERVAL_SEC
