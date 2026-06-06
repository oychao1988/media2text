"""Agent loop iteration budget (Hermes IterationBudget)."""

from __future__ import annotations


class IterationBudget:
    """Tracks remaining LLM iterations for one conversation turn."""

    def __init__(self, max_turns: int) -> None:
        self._max = max(1, max_turns)
        self._used = 0

    @property
    def remaining(self) -> int:
        return max(0, self._max - self._used)

    @property
    def exhausted(self) -> bool:
        return self._used >= self._max

    def consume(self) -> None:
        self._used += 1
