# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 5 — context compression surface tests.

The vendored ContextCompressor itself is exercised at the integration
level (curator smoke test). Here we cover the AIAgent-side wiring:
    - context_compressor is None until first use (lazy)
    - _ensure_compressor is idempotent
    - _compress_context with no messages returns sensibly
    - _compress_context preserves the system prompt when none provided
    - model_metadata Anthropic-only catalog returns 200K for Claude family

Run:
    python -m unittest tests.unit.test_compression -v
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from engine.core.agent import AIAgent
from engine.learning.model_metadata import (
    MINIMUM_CONTEXT_LENGTH,
    get_model_context_length,
    estimate_messages_tokens_rough,
    estimate_request_tokens_rough,
)


def _build_agent() -> AIAgent:
    return AIAgent(
        model="claude-opus-4-7",
        api_key="sk-test-fake",
        quiet_mode=True,
    )


class CompressorLazyTest(unittest.TestCase):
    def test_compressor_is_none_until_used(self):
        agent = _build_agent()
        self.assertIsNone(agent.context_compressor)

    def test_ensure_compressor_builds_once(self):
        agent = _build_agent()
        c1 = agent._ensure_compressor()
        c2 = agent._ensure_compressor()
        self.assertIs(c1, c2)
        self.assertIsNotNone(agent.context_compressor)

    def test_compressor_inherits_model_metadata(self):
        agent = _build_agent()
        c = agent._ensure_compressor()
        # Threshold = 50% of context length (Anthropic Claude = 200K)
        self.assertEqual(c.context_length, 200_000)
        self.assertEqual(c.threshold_tokens, 100_000)


class ModelMetadataTest(unittest.TestCase):
    def test_known_model_returns_200k(self):
        self.assertEqual(get_model_context_length("claude-opus-4-7"), 200_000)
        self.assertEqual(get_model_context_length("claude-sonnet-4-6"), 200_000)

    def test_unknown_model_uses_default(self):
        self.assertEqual(get_model_context_length("unknown-model"), 200_000)

    def test_prefix_match_handles_snapshots(self):
        # Snapshot ids like claude-opus-4-7-20251101 hit the prefix branch
        self.assertEqual(
            get_model_context_length("claude-opus-4-7-20251101"),
            200_000,
        )

    def test_config_override_takes_priority(self):
        self.assertEqual(
            get_model_context_length("claude-opus-4-7", config_context_length=50_000),
            50_000,
        )

    def test_minimum_constant(self):
        self.assertEqual(MINIMUM_CONTEXT_LENGTH, 64_000)


class TokenEstimateTest(unittest.TestCase):
    def test_empty_message_list(self):
        self.assertEqual(estimate_messages_tokens_rough([]), 0)

    def test_rough_chars_div_4(self):
        # "hello" -> 5 chars, ~ (chars+3)//4 = 2 tokens + dict scaffolding
        result = estimate_messages_tokens_rough(
            [{"role": "user", "content": "hello"}]
        )
        self.assertGreater(result, 0)

    def test_request_estimate_includes_tools(self):
        msgs = [{"role": "user", "content": "hi"}]
        tools = [{"name": "x", "description": "y", "input_schema": {}}]
        without_tools = estimate_request_tokens_rough(msgs)
        with_tools = estimate_request_tokens_rough(msgs, tools=tools)
        self.assertGreater(with_tools, without_tools)


class CompressContextSurfaceTest(unittest.TestCase):
    """We don't make a real LLM call here — just verify the method
    accepts the documented signature and returns the right shape. The
    vendored compressor's actual summarization is covered by the smoke
    test that runs curator end-to-end."""

    def test_signature_accepts_keyword_args(self):
        agent = _build_agent()
        agent._compression_warning = None
        # No messages means nothing to compact — the compressor returns
        # the empty list quickly without an LLM call.
        compressed, sysprompt = agent._compress_context(
            messages=[],
            system_message="hello system",
            approx_tokens=0,
            task_id="t-1",
            focus_topic=None,
        )
        self.assertEqual(compressed, [])
        # When caller passes a system_message it is preserved
        self.assertEqual(sysprompt, "hello system")

    def test_no_system_message_falls_back_to_stored_prompt(self):
        agent = _build_agent()
        agent._system_prompt = "stored prompt"
        compressed, sysprompt = agent._compress_context(messages=[])
        self.assertEqual(sysprompt, "stored prompt")


if __name__ == "__main__":
    unittest.main()
