# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 6 — memory manager wiring + "no memory yet" invariant.

The user requirement (2026-05-13): memory may be entirely absent on day-1
of the poet-agent scenario, and the agent MUST keep working. Every
consumer in AIAgent that reads from _memory_manager has to handle None
without raising.

We cover:
    1. AIAgent boots with _memory_manager = None
    2. _memory_prefetch_safe returns "" when manager is None
    3. _attach_memory_manager wires an empty manager (no providers)
    4. Empty manager's prefetch_all + build_system_prompt + has_tool
       all return safe empty values (no errors)
    5. _compress_context with no memory_manager skips the on_pre_compress
       hook silently
    6. Provider that raises in prefetch_all is swallowed by safe wrapper

Run:
    python -m unittest tests.unit.test_memory -v
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from engine.core.agent import AIAgent
from engine.learning.memory_manager import MemoryManager
from engine.learning.memory_provider import MemoryProvider


def _build_agent() -> AIAgent:
    return AIAgent(
        model="claude-opus-4-7",
        api_key="sk-test-fake",
        quiet_mode=True,
    )


class _StubProvider(MemoryProvider):
    """Minimal provider implementation for tests. All hooks return empty
    so we exercise the orchestration layer rather than provider logic."""

    def __init__(self, name: str = "stub", raises: bool = False):
        self._name = name
        self._raises = raises

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def system_prompt_block(self) -> str:
        return f"# memory from {self._name}\n(empty)"

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if self._raises:
            raise RuntimeError("stub provider failure")
        return ""

    def sync_turn(
        self,
        user_message: str,
        assistant_message: str,
        *,
        session_id: str = "",
        **kwargs,
    ) -> None:
        return None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return []

    def handle_tool_call(self, name: str, args: Dict[str, Any]) -> str:
        return "{}"


class DefaultStateTest(unittest.TestCase):
    def test_agent_boots_with_no_memory(self):
        agent = _build_agent()
        self.assertIsNone(agent._memory_manager)

    def test_prefetch_safe_returns_empty_when_none(self):
        agent = _build_agent()
        self.assertEqual(agent._memory_prefetch_safe("anything"), "")


class AttachmentTest(unittest.TestCase):
    def test_attach_memory_manager_stores_reference(self):
        agent = _build_agent()
        mgr = MemoryManager()
        agent._attach_memory_manager(mgr)
        self.assertIs(agent._memory_manager, mgr)

    def test_empty_manager_is_safe(self):
        """A MemoryManager with zero providers must not error on any
        public call — this is what Phase 1 day-1 looks like."""
        mgr = MemoryManager()
        self.assertEqual(mgr.prefetch_all("hello"), "")
        self.assertEqual(mgr.build_system_prompt(), "")
        self.assertFalse(mgr.has_tool("memory"))
        self.assertEqual(mgr.providers, [])


class ProviderRegistrationTest(unittest.TestCase):
    def test_external_provider_registers(self):
        mgr = MemoryManager()
        mgr.add_provider(_StubProvider(name="honcho"))
        self.assertEqual(len(mgr.providers), 1)
        self.assertIsNotNone(mgr.get_provider("honcho"))
        self.assertIsNone(mgr.get_provider("does-not-exist"))

    def test_second_external_provider_rejected(self):
        mgr = MemoryManager()
        mgr.add_provider(_StubProvider(name="honcho"))
        mgr.add_provider(_StubProvider(name="mem0"))
        # Only one external allowed
        self.assertEqual(len(mgr.providers), 1)
        self.assertIsNotNone(mgr.get_provider("honcho"))
        self.assertIsNone(mgr.get_provider("mem0"))


class SafeWrapperTest(unittest.TestCase):
    def test_provider_exception_collapses_to_empty(self):
        agent = _build_agent()
        mgr = MemoryManager()
        mgr.add_provider(_StubProvider(name="broken", raises=True))
        agent._attach_memory_manager(mgr)
        # The provider's prefetch raises — the manager's prefetch_all
        # catches it per-provider, so the user-facing wrapper returns "".
        self.assertEqual(agent._memory_prefetch_safe("query"), "")


class CompressionHookTest(unittest.TestCase):
    def test_compression_works_without_memory(self):
        """_compress_context must run cleanly even when no memory
        manager is attached — the on_pre_compress hook should be skipped."""
        agent = _build_agent()
        compressed, sysprompt = agent._compress_context(
            messages=[],
            system_message="sys",
            approx_tokens=0,
        )
        # No exception, sysprompt preserved, compressed is empty (nothing
        # to summarize from an empty messages list)
        self.assertEqual(compressed, [])
        self.assertEqual(sysprompt, "sys")

    def test_compression_invokes_pre_compress_when_attached(self):
        """When a memory manager IS attached, _compress_context must call
        on_pre_compress so providers can extract durable facts before the
        middle slice is summarized away."""
        agent = _build_agent()

        observed: List[Any] = []

        class _RecordingProvider(_StubProvider):
            def on_pre_compress(self, messages):  # type: ignore[override]
                observed.append(list(messages))
                return ""

        mgr = MemoryManager()
        mgr.add_provider(_RecordingProvider(name="external"))
        agent._attach_memory_manager(mgr)

        agent._compress_context(messages=[{"role": "user", "content": "hi"}])
        # The hook fired exactly once with the unmodified message list
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0], [{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
