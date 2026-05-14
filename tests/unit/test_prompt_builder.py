# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 4 — prompt builder + caching + AIAgent auto-build.

Two user invariants drive this suite (recorded in phase-1-todo.md, 2026-05-13):
    1. "메모리가 없어도 에러는 없어야 함" — empty memory / no skills / no SOUL
       must not crash AIAgent system prompt construction.
    2. "대충 물어봐도 정확하게 답하고 메모리와 연동" — when a memory manager
       contributes a system_prompt_block, it must land in the composed
       system prompt the LLM sees.

Run:
    python -m unittest tests.unit.test_prompt_builder -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from engine.core.agent import AIAgent, Tool
from engine.core.prompt_builder import (
    build_context_files_prompt,
    build_skills_system_prompt,
    load_soul_md,
)
from engine.core.prompt_caching import apply_anthropic_cache_control
from engine.learning.memory_manager import MemoryManager
from engine.learning.memory_provider import MemoryProvider


class _MemoryStub(MemoryProvider):
    """Minimal provider that contributes a recognisable system prompt
    block so we can assert it lands in the composed system prompt."""

    def __init__(self, block_text: str):
        self._block = block_text

    @property
    def name(self) -> str:
        return "stub-memory"

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def system_prompt_block(self) -> str:
        return self._block

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        return ""

    def sync_turn(self, user_message, assistant_message, *, session_id="", **kwargs):
        return None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return []

    def handle_tool_call(self, name: str, args: Dict[str, Any]) -> str:
        return "{}"


def _build_agent(**kwargs) -> AIAgent:
    return AIAgent(
        model="claude-opus-4-7",
        api_key="sk-test-fake",
        quiet_mode=True,
        **kwargs,
    )


class _EnvCtx:
    """Temporarily override env vars within a test."""

    def __init__(self, **kwargs: str):
        self.overrides = kwargs
        self.original: Dict[str, str | None] = {}

    def __enter__(self):
        for k, v in self.overrides.items():
            self.original[k] = os.environ.get(k)
            os.environ[k] = v
        return self

    def __exit__(self, *args):
        for k, prev in self.original.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


class EmptyEnvironmentTest(unittest.TestCase):
    """Invariant #1: missing memory / missing SOUL / missing skills must
    NOT raise on system prompt construction."""

    def test_load_soul_md_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                self.assertIsNone(load_soul_md())

    def test_build_skills_prompt_returns_empty_when_no_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                result = build_skills_system_prompt()
                self.assertEqual(result, "")

    def test_build_context_files_runs_without_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                # Should return a string (possibly empty) — never raise
                result = build_context_files_prompt()
                self.assertIsInstance(result, str)


class AgentAutoBuildTest(unittest.TestCase):
    """AIAgent._build_system_prompt lazy auto-build behaviour."""

    def test_caller_supplied_prompt_takes_precedence(self):
        agent = _build_agent(system_prompt="hard-coded by caller")
        # Auto-build should be OFF when caller supplied a value
        self.assertFalse(agent._auto_build_system_prompt)
        # _build_system_prompt() returns the caller's string unchanged
        self.assertEqual(agent._build_system_prompt(), "hard-coded by caller")

    def test_auto_build_runs_when_no_caller_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                agent = _build_agent()
                self.assertTrue(agent._auto_build_system_prompt)
                # No skills, no memory, no SOUL.md → composed prompt is empty
                # but the build itself does NOT raise.
                composed = agent._build_system_prompt()
                self.assertEqual(composed, "")

    def test_auto_build_caches_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                agent = _build_agent()
                first = agent._build_system_prompt()
                # Mutate the cached value so we can prove the next call
                # reads the cache rather than rebuilding from scratch.
                agent._system_prompt = "sentinel-from-cache"
                self.assertEqual(agent._build_system_prompt(), "sentinel-from-cache")
                # Sanity: the test environment really did not crash on first
                self.assertEqual(first, "")

    def test_override_argument_replaces_cache(self):
        agent = _build_agent()
        self.assertEqual(agent._build_system_prompt("forced"), "forced")
        self.assertEqual(agent._system_prompt, "forced")

    def test_invalidate_system_prompt_resets_only_auto(self):
        # Auto-build agent: invalidate clears cache for next rebuild
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                a1 = _build_agent()
                a1._build_system_prompt()
                a1._system_prompt = "stale"
                a1._invalidate_system_prompt()
                self.assertEqual(a1._system_prompt, "")
        # Caller-supplied agent: invalidate is a no-op
        a2 = _build_agent(system_prompt="fixed")
        a2._invalidate_system_prompt()
        self.assertEqual(a2._system_prompt, "fixed")


class MemoryIntegrationTest(unittest.TestCase):
    """Invariant #2: a memory provider's system_prompt_block lands in
    the composed prompt the agent sees."""

    def test_memory_block_included_in_composed_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                agent = _build_agent()
                mgr = MemoryManager()
                mgr.add_provider(_MemoryStub(block_text="USER LIKES SHORT POEMS"))
                agent._attach_memory_manager(mgr)
                composed = agent._build_system_prompt()
                self.assertIn("USER LIKES SHORT POEMS", composed)

    def test_no_memory_still_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                agent = _build_agent()
                self.assertIsNone(agent._memory_manager)
                # Invariant: no manager → empty composition, no exception
                self.assertEqual(agent._build_system_prompt(), "")


class PromptCachingTest(unittest.TestCase):
    """prompt_caching applies up to 4 Anthropic cache_control breakpoints."""

    def test_empty_messages_returns_empty(self):
        self.assertEqual(apply_anthropic_cache_control([]), [])

    def test_system_message_gets_cache_marker(self):
        msgs = [
            {"role": "system", "content": "you are a poet"},
            {"role": "user", "content": "hi"},
        ]
        out = apply_anthropic_cache_control(msgs)
        # The system message content should be wrapped in a list with
        # cache_control attached to the text part.
        sys_msg = out[0]
        self.assertEqual(sys_msg["role"], "system")
        self.assertIsInstance(sys_msg["content"], list)
        first_block = sys_msg["content"][0]
        self.assertIn("cache_control", first_block)

    def test_max_4_breakpoints(self):
        # 1 system + 10 user turns. Anthropic allows 4 cache breakpoints:
        # one on system + three on the last three non-system messages.
        msgs = [{"role": "system", "content": "S"}] + [
            {"role": "user", "content": f"msg{i}"} for i in range(10)
        ]
        out = apply_anthropic_cache_control(msgs)

        def has_cache(m: Dict[str, Any]) -> bool:
            if "cache_control" in m:
                return True
            content = m.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "cache_control" in part:
                        return True
            return False

        marked = [i for i, m in enumerate(out) if has_cache(m)]
        # System + last 3 user messages = 4 markers
        self.assertEqual(len(marked), 4)
        # System is one of them
        self.assertIn(0, marked)
        # The last 3 messages (indices 8, 9, 10) are also marked
        self.assertIn(10, marked)
        self.assertIn(9, marked)
        self.assertIn(8, marked)


if __name__ == "__main__":
    unittest.main()
