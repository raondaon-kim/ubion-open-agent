# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 13 — DeepSeek + provider router.

Covers:
    - resolve_provider() routing (claude-* / deepseek-* / unknown / override)
    - build_client() returns the right concrete class
    - AIAgent picks the right client when model name shifts
    - DeepSeekClient message translation: Anthropic shape → OpenAI shape
    - DeepSeekClient response normalization: OpenAI → ChatResponse
    - Tool schema translation
    - /v1/models lists deepseek entries
    - get_model_context_length returns 128K for deepseek family

Real network calls are stubbed via patch on the underlying SDK.

Run:
    python -m unittest tests.unit.test_multi_provider -v
"""

from __future__ import annotations

import json
import os
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class _EnvCtx:
    def __init__(self, **kwargs):
        self.overrides = kwargs
        self.original: Dict[str, str | None] = {}

    def __enter__(self):
        for k, v in self.overrides.items():
            self.original[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *args):
        for k, prev in self.original.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


class RouterResolutionTest(unittest.TestCase):
    def test_claude_model_routes_anthropic(self):
        from engine.llm.router import resolve_provider
        self.assertEqual(resolve_provider("claude-opus-4-7"), "anthropic")
        self.assertEqual(resolve_provider("claude-sonnet-4-6"), "anthropic")

    def test_deepseek_model_routes_deepseek(self):
        from engine.llm.router import resolve_provider
        self.assertEqual(resolve_provider("deepseek-v4-flash"), "deepseek")
        self.assertEqual(resolve_provider("deepseek-v4-pro"), "deepseek")
        self.assertEqual(resolve_provider("deepseek-chat"), "deepseek")

    def test_unknown_model_defaults_to_anthropic(self):
        from engine.llm.router import resolve_provider
        self.assertEqual(resolve_provider("mystery-7b"), "anthropic")
        self.assertEqual(resolve_provider(""), "anthropic")

    def test_explicit_override_wins(self):
        from engine.llm.router import resolve_provider
        # User says "use deepseek" with a claude-named model
        self.assertEqual(
            resolve_provider("claude-opus-4-7", explicit="deepseek"),
            "deepseek",
        )

    def test_invalid_explicit_provider_raises(self):
        from engine.llm.router import resolve_provider
        with self.assertRaises(ValueError):
            resolve_provider("claude-opus-4-7", explicit="palmtree")


class BuildClientTest(unittest.TestCase):
    def test_build_anthropic_client(self):
        with _EnvCtx(ANTHROPIC_API_KEY="sk-fake"):
            from engine.llm.router import build_client
            from engine.llm.anthropic import AnthropicClient
            c = build_client(model="claude-opus-4-7")
            self.assertIsInstance(c, AnthropicClient)

    def test_build_deepseek_client(self):
        with _EnvCtx(DEEPSEEK_API_KEY="sk-fake-deepseek"):
            from engine.llm.router import build_client
            from engine.llm.deepseek import DeepSeekClient
            c = build_client(model="deepseek-v4-flash")
            self.assertIsInstance(c, DeepSeekClient)


class AIAgentProviderRoutingTest(unittest.TestCase):
    def test_agent_picks_anthropic_for_claude_model(self):
        with _EnvCtx(ANTHROPIC_API_KEY="sk-fake"):
            from engine.core.agent import AIAgent
            from engine.llm.anthropic import AnthropicClient
            agent = AIAgent(model="claude-opus-4-7", quiet_mode=True)
            self.assertEqual(agent.provider, "anthropic")
            self.assertIsInstance(agent._llm, AnthropicClient)

    def test_agent_picks_deepseek_for_deepseek_model(self):
        with _EnvCtx(DEEPSEEK_API_KEY="sk-fake-deepseek"):
            from engine.core.agent import AIAgent
            from engine.llm.deepseek import DeepSeekClient
            agent = AIAgent(model="deepseek-v4-flash", quiet_mode=True)
            self.assertEqual(agent.provider, "deepseek")
            self.assertIsInstance(agent._llm, DeepSeekClient)


class DeepSeekMessageTranslationTest(unittest.TestCase):
    """The crucial bit: Anthropic-shape messages → OpenAI-shape."""

    def test_simple_user_message(self):
        from engine.llm.deepseek import _to_openai_messages
        result = _to_openai_messages(
            [{"role": "user", "content": "hi"}],
            system="be terse",
        )
        self.assertEqual(result, [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
        ])

    def test_assistant_with_tool_use_block(self):
        from engine.llm.deepseek import _to_openai_messages
        anthropic_msgs = [
            {"role": "user", "content": "use a tool"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll call a tool."},
                    {
                        "type": "tool_use",
                        "id": "tool_abc",
                        "name": "echo",
                        "input": {"v": "hello"},
                    },
                ],
            },
        ]
        result = _to_openai_messages(anthropic_msgs, system=None)
        # No system message → first entry is the user turn
        self.assertEqual(result[0]["role"], "user")
        # Assistant turn carries text content + tool_calls array
        asst = result[1]
        self.assertEqual(asst["role"], "assistant")
        self.assertEqual(asst["content"], "I'll call a tool.")
        self.assertEqual(len(asst["tool_calls"]), 1)
        tc = asst["tool_calls"][0]
        self.assertEqual(tc["id"], "tool_abc")
        self.assertEqual(tc["type"], "function")
        self.assertEqual(tc["function"]["name"], "echo")
        self.assertEqual(json.loads(tc["function"]["arguments"]), {"v": "hello"})

    def test_user_with_tool_result_splits_into_tool_role(self):
        from engine.llm.deepseek import _to_openai_messages
        anthropic_msgs = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool_abc",
                        "content": "tool said hello",
                    },
                ],
            },
        ]
        result = _to_openai_messages(anthropic_msgs, system=None)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "tool")
        self.assertEqual(result[0]["tool_call_id"], "tool_abc")
        self.assertEqual(result[0]["content"], "tool said hello")


class DeepSeekToolSchemaTranslationTest(unittest.TestCase):
    def test_anthropic_tool_schema_to_openai(self):
        from engine.llm.deepseek import _tool_to_openai
        anthropic_tool = {
            "name": "echo",
            "description": "echoes the input",
            "input_schema": {
                "type": "object",
                "properties": {"v": {"type": "string"}},
                "required": ["v"],
            },
        }
        result = _tool_to_openai(anthropic_tool)
        self.assertEqual(result["type"], "function")
        self.assertEqual(result["function"]["name"], "echo")
        self.assertEqual(result["function"]["description"], "echoes the input")
        self.assertEqual(
            result["function"]["parameters"],
            anthropic_tool["input_schema"],
        )


class DeepSeekResponseNormalizationTest(unittest.TestCase):
    def test_text_only_completion(self):
        from engine.llm.deepseek import _normalize_completion

        message = MagicMock()
        message.content = "hello back"
        message.tool_calls = None

        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "stop"

        usage = MagicMock()
        usage.prompt_tokens = 12
        usage.completion_tokens = 5

        completion = MagicMock()
        completion.choices = [choice]
        completion.usage = usage

        result = _normalize_completion(completion)
        self.assertEqual(result.text, "hello back")
        self.assertEqual(result.tool_calls, [])
        self.assertEqual(result.stop_reason, "stop")
        self.assertEqual(result.usage["input_tokens"], 12)
        self.assertEqual(result.usage["output_tokens"], 5)

    def test_completion_with_tool_calls(self):
        from engine.llm.deepseek import _normalize_completion

        fn = MagicMock()
        fn.name = "echo"
        fn.arguments = '{"v": "hi"}'

        tc = MagicMock()
        tc.id = "call_123"
        tc.function = fn

        message = MagicMock()
        message.content = ""
        message.tool_calls = [tc]

        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "tool_calls"

        completion = MagicMock()
        completion.choices = [choice]
        completion.usage = None

        result = _normalize_completion(completion)
        self.assertEqual(len(result.tool_calls), 1)
        parsed = result.tool_calls[0]
        self.assertEqual(parsed.id, "call_123")
        self.assertEqual(parsed.name, "echo")
        self.assertEqual(parsed.arguments, {"v": "hi"})


class ServerModelsListTest(unittest.TestCase):
    def test_models_endpoint_lists_deepseek(self):
        from engine.server.api import create_app
        with _EnvCtx(UBION_API_TOKEN=None):
            client = TestClient(create_app())
            r = client.get("/v1/models")
        self.assertEqual(r.status_code, 200)
        ids = {m["id"] for m in r.json()["data"]}
        self.assertIn("deepseek-v4-flash", ids)
        self.assertIn("deepseek-v4-pro", ids)
        self.assertIn("claude-opus-4-7", ids)


class ModelContextLengthTest(unittest.TestCase):
    def test_deepseek_v4_returns_128k(self):
        from engine.learning.model_metadata import get_model_context_length
        self.assertEqual(get_model_context_length("deepseek-v4-flash"), 128_000)
        self.assertEqual(get_model_context_length("deepseek-v4-pro"), 128_000)

    def test_deepseek_v3_legacy(self):
        from engine.learning.model_metadata import get_model_context_length
        self.assertEqual(get_model_context_length("deepseek-chat"), 128_000)
        self.assertEqual(get_model_context_length("deepseek-reasoner"), 128_000)

    def test_deepseek_snapshot_prefix_match(self):
        from engine.learning.model_metadata import get_model_context_length
        # Hypothetical future snapshot id
        self.assertEqual(
            get_model_context_length("deepseek-v4-pro-20260513"),
            128_000,
        )


if __name__ == "__main__":
    unittest.main()
