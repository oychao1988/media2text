"""Command / tool approval gate (Hermes §24.2.3)."""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from media2text.core.config import AppConfig

EmitFn = Callable[[dict[str, Any]], None]

_DANGEROUS_SHELL = [
    re.compile(r"\brm\s+-rf\b", re.I),
    re.compile(r"\bsudo\b", re.I),
    re.compile(r"\bcurl\b", re.I),
    re.compile(r"\bwget\b", re.I),
    re.compile(r"\bchmod\s+[0-7]{3,4}\b", re.I),
    re.compile(r">\s*/", re.I),
]

_M2T_APPROVAL_TOOLS = frozenset(
    {
        "m2t_start_recording",
        "m2t_stop_recording",
        "m2t_daemon_start",
        "m2t_daemon_stop",
    }
)


def shell_needs_approval(command: str) -> bool:
    text = command.strip()
    if not text:
        return False
    return any(p.search(text) for p in _DANGEROUS_SHELL)


def m2t_tool_needs_approval(tool_name: str) -> bool:
    return tool_name in _M2T_APPROVAL_TOOLS


@dataclass
class PendingApproval:
    id: str
    action: str
    summary: str
    detail: dict[str, Any]
    event: threading.Event = field(default_factory=threading.Event)
    approved: bool | None = None


class ApprovalRegistry:
    """Thread-safe pending approvals (Desktop resolves via API)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PendingApproval] = {}

    def create(self, *, action: str, summary: str, detail: dict[str, Any]) -> PendingApproval:
        item = PendingApproval(id=str(uuid.uuid4()), action=action, summary=summary, detail=detail)
        with self._lock:
            self._pending[item.id] = item
        return item

    def resolve(self, approval_id: str, *, approved: bool) -> bool:
        with self._lock:
            item = self._pending.get(approval_id)
            if item is None or item.approved is not None:
                return False
            item.approved = approved
            item.event.set()
            return True

    def pop(self, approval_id: str) -> PendingApproval | None:
        with self._lock:
            return self._pending.pop(approval_id, None)


GLOBAL_APPROVAL_REGISTRY = ApprovalRegistry()


class ApprovalGate:
    def __init__(
        self,
        cfg: AppConfig,
        *,
        emit: EmitFn | None = None,
        registry: ApprovalRegistry | None = None,
        auto_approve: bool = False,
        timeout_sec: float = 120.0,
    ) -> None:
        self._cfg = cfg
        self._emit = emit
        self._registry = registry or GLOBAL_APPROVAL_REGISTRY
        self._auto_approve = auto_approve
        self._timeout = timeout_sec

    def ensure(
        self,
        *,
        action: str,
        summary: str,
        detail: dict[str, Any] | None = None,
    ) -> bool:
        mode = self._cfg.security.command_approval
        if self._auto_approve or mode == "off":
            return True
        if mode == "allowlist":
            allow = set(self._cfg.security.allowlist or [])
            if action in allow:
                return True

        item = self._registry.create(action=action, summary=summary, detail=detail or {})
        if self._emit:
            self._emit(
                {
                    "type": "approval.request",
                    "payload": {
                        "id": item.id,
                        "action": action,
                        "summary": summary,
                        "detail": item.detail,
                    },
                }
            )
        if not item.event.wait(timeout=self._timeout):
            self._registry.pop(item.id)
            return False
        approved = item.approved is True
        self._registry.pop(item.id)
        return approved
