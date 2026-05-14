# Ported from NousResearch/hermes-agent (MIT License)
# Original: https://github.com/NousResearch/hermes-agent/blob/b06e9993021a8eebd891fc60d52372446315b2f0/run_agent.py#L283
# Rewritten in Ubion conventions; algorithm + behavior preserved.
#
# Copyright (c) 2025 Nous Research (original algorithm)
# Copyright (c) 2026 Ubion ax center (implementation)
#
# This file is licensed under the MIT License. See engine/NOTICE.md.
"""Iteration budget for a single agent run.

Each agent (top-level or sub) gets its own :class:`IterationBudget`. Parent
budget is independent from any sub-agent's budget so that an out-of-control
sub doesn't drain the parent's quota.

A consumed iteration that turns out to be cheap (e.g. ``execute_code``
turns that batched many tool calls into one network round-trip) can be
refunded via :meth:`refund`.

Thread-safe: ``consume`` / ``refund`` / property reads all acquire an
internal lock so concurrent tool dispatch can update the same budget
without corruption.
"""

from __future__ import annotations

import threading


class IterationBudget:
    """Thread-safe iteration counter for an agent run."""

    __slots__ = ("max_total", "_used", "_lock")

    def __init__(self, max_total: int) -> None:
        if max_total < 1:
            raise ValueError(f"max_total must be >= 1, got {max_total}")
        self.max_total: int = max_total
        self._used: int = 0
        self._lock = threading.Lock()

    def consume(self) -> bool:
        """Attempt to consume one iteration. Returns True if allowed."""
        with self._lock:
            if self._used >= self.max_total:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        """Return one iteration to the pool.

        No-op if nothing has been consumed yet — refunding past zero would
        let a misbehaving caller create budget out of thin air.
        """
        with self._lock:
            if self._used > 0:
                self._used -= 1

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.max_total - self._used)
