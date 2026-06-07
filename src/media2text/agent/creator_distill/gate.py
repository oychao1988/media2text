"""Bootstrap merge gate (CD5) — pure deferred rules before distill."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BootstrapGateResult:
    web_channels_ok: int
    local_chars: int
    web_enabled: bool
    proceed: bool
    deferred_reason: str | None


def evaluate_bootstrap_gate(
    *,
    web_channels_ok: int,
    local_chars: int,
    defer_until_min_chars: int,
    bootstrap_web_research: bool,
) -> BootstrapGateResult:
    web_enabled = bootstrap_web_research
    if web_enabled and web_channels_ok >= 1:
        return BootstrapGateResult(
            web_channels_ok=web_channels_ok,
            local_chars=local_chars,
            web_enabled=web_enabled,
            proceed=True,
            deferred_reason=None,
        )
    if not web_enabled and local_chars >= defer_until_min_chars:
        return BootstrapGateResult(
            web_channels_ok=web_channels_ok,
            local_chars=local_chars,
            web_enabled=web_enabled,
            proceed=True,
            deferred_reason=None,
        )
    if web_enabled and web_channels_ok == 0 and local_chars >= defer_until_min_chars:
        return BootstrapGateResult(
            web_channels_ok=web_channels_ok,
            local_chars=local_chars,
            web_enabled=web_enabled,
            proceed=True,
            deferred_reason=None,
        )
    reason = (
        "local_below_min"
        if not web_enabled
        else "web_and_local_insufficient"
    )
    return BootstrapGateResult(
        web_channels_ok=web_channels_ok,
        local_chars=local_chars,
        web_enabled=web_enabled,
        proceed=False,
        deferred_reason=reason,
    )
