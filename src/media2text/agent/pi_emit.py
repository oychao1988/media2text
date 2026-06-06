"""PiEvent-shaped payloads for WS /api/agent/stream."""

from __future__ import annotations

import time
from typing import Any


def pi_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "payload": payload}


def sidecar_ready(version: str = "hermes-m1") -> dict[str, Any]:
    return pi_event("sidecar.ready", {"version": version})


def turn_start(*, started_at: float | None = None) -> dict[str, Any]:
    return pi_event("turn.start", {"startedAt": started_at or time.time() * 1000})


def turn_phase(phase: str, label: str) -> dict[str, Any]:
    return pi_event("turn.phase", {"phase": phase, "label": label})


def assistant_delta(delta: str) -> dict[str, Any]:
    return pi_event("message.assistant.delta", {"delta": delta})


def message_assistant(
    text: str,
    *,
    duration_ms: int | None = None,
    thinking_text: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"text": text}
    if duration_ms is not None:
        payload["durationMs"] = duration_ms
    if thinking_text:
        payload["thinkingText"] = thinking_text
    return pi_event("message.assistant", payload)


def turn_end(duration_ms: int) -> dict[str, Any]:
    return pi_event("turn.end", {"durationMs": duration_ms})


def thread_title(thread_id: str, title: str) -> dict[str, Any]:
    return pi_event("thread.title", {"threadId": thread_id, "title": title})


def tool_start(*, tool_call_id: str, name: str) -> dict[str, Any]:
    return pi_event("tool.start", {"toolCallId": tool_call_id, "name": name})


def tool_result_payload(result: dict[str, Any], *, name: str | None = None) -> dict[str, Any]:
    payload = dict(result)
    if name:
        payload["name"] = name
    return pi_event("tool.result", payload)


def agent_error(message: str, *, code: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"message": message}
    if code:
        payload["code"] = code
    return pi_event("error", payload)
