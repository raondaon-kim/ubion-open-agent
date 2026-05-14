# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 3-3 — tool_dispatch.execute_tool_calls_sequential coverage.

Six cases mirrored from Hermes' sequential semantics:
    1. dict args pass through
    2. JSON-string args parse into a dict
    3. malformed JSON args coerce to {}
    4. unknown tool name returns an error block (loop continues)
    5. handler exception returns is_error block (loop continues)
    6. mid-batch interrupt fills every remaining slot with skip block

Run:
    python -m unittest tests.unit.test_tool_dispatch -v
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from engine.core.agent import Tool
from engine.core.tool_dispatch import execute_tool_calls_sequential
from engine.llm.anthropic import ToolCall


class _FakeAgent:
    """Minimal stand-in for AIAgent — only what tool_dispatch reads."""

    def __init__(self, tools: List[Tool]):
        self._tools: Dict[str, Tool] = {t.name: t for t in tools}
        self._interrupt_requested = False


def _echo_tool() -> Tool:
    return Tool(
        name="echo",
        description="echo args back",
        schema={"type": "object", "properties": {}},
        handler=lambda args: {"got": args},
    )


def _call(name: str, args: Any, call_id: str = "tc_1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=args)


class DictArgsTest(unittest.TestCase):
    def test_dict_args_pass_through(self):
        agent = _FakeAgent([_echo_tool()])
        out = execute_tool_calls_sequential(agent, [_call("echo", {"v": 1})])
        self.assertEqual(len(out), 1)
        self.assertNotIn("is_error", out[0])
        self.assertIn('"v": 1', out[0]["content"])


class JsonStringArgsTest(unittest.TestCase):
    def test_json_string_args_parse(self):
        agent = _FakeAgent([_echo_tool()])
        out = execute_tool_calls_sequential(
            agent, [_call("echo", '{"v": "x"}')]
        )
        self.assertEqual(len(out), 1)
        self.assertNotIn("is_error", out[0])
        self.assertIn('"v": "x"', out[0]["content"])


class MalformedJsonArgsTest(unittest.TestCase):
    def test_malformed_json_coerces_to_empty(self):
        agent = _FakeAgent([_echo_tool()])
        out = execute_tool_calls_sequential(
            agent, [_call("echo", "{not-valid-json")]
        )
        self.assertEqual(len(out), 1)
        # echo handler still ran, got {} — i.e. no is_error, and content
        # carries an empty args dict
        self.assertNotIn("is_error", out[0])
        self.assertIn('"got": {}', out[0]["content"])


class UnknownToolTest(unittest.TestCase):
    def test_unknown_tool_emits_error_and_continues(self):
        agent = _FakeAgent([_echo_tool()])
        out = execute_tool_calls_sequential(
            agent,
            [
                _call("nope", {}, call_id="t1"),
                _call("echo", {"v": 2}, call_id="t2"),
            ],
        )
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0]["is_error"])
        self.assertIn("unknown tool", out[0]["content"])
        # Second call still runs — unknown tool doesn't trip the batch
        self.assertNotIn("is_error", out[1])


class HandlerExceptionTest(unittest.TestCase):
    def test_handler_exception_emits_is_error_and_continues(self):
        def boom(_args):
            raise ValueError("bang")
        bomb = Tool(
            name="bomb", description="raises",
            schema={"type": "object", "properties": {}},
            handler=boom,
        )
        agent = _FakeAgent([bomb, _echo_tool()])
        out = execute_tool_calls_sequential(
            agent,
            [
                _call("bomb", {}, call_id="t1"),
                _call("echo", {"v": 3}, call_id="t2"),
            ],
        )
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0]["is_error"])
        self.assertIn("ValueError: bang", out[0]["content"])
        # Crash in one tool does NOT halt the rest of the batch — matches
        # Hermes sequential path, lets the model recover via next turn.
        self.assertNotIn("is_error", out[1])


class InterruptMidBatchTest(unittest.TestCase):
    def test_interrupt_flag_skips_remaining(self):
        flipper_calls: List[int] = []

        def flip(_args):
            flipper_calls.append(1)
            agent_ref["a"]._interrupt_requested = True
            return "ok"

        flip_tool = Tool(
            name="flip", description="flip interrupt",
            schema={"type": "object", "properties": {}},
            handler=flip,
        )
        agent_ref: Dict[str, Any] = {}
        agent = _FakeAgent([flip_tool, _echo_tool()])
        agent_ref["a"] = agent

        out = execute_tool_calls_sequential(
            agent,
            [
                _call("flip", {}, call_id="t1"),
                _call("echo", {"v": 4}, call_id="t2"),
                _call("echo", {"v": 5}, call_id="t3"),
            ],
        )
        # First call ran, the next two are skip blocks
        self.assertEqual(len(out), 3)
        self.assertEqual(len(flipper_calls), 1)
        self.assertNotIn("is_error", out[0])  # flip itself succeeded
        for skip in out[1:]:
            self.assertTrue(skip["is_error"])
            self.assertIn("skipped due to user interrupt", skip["content"])

    def test_already_interrupted_skips_everything(self):
        agent = _FakeAgent([_echo_tool()])
        agent._interrupt_requested = True
        out = execute_tool_calls_sequential(
            agent,
            [
                _call("echo", {}, call_id="t1"),
                _call("echo", {}, call_id="t2"),
            ],
        )
        self.assertEqual(len(out), 2)
        for r in out:
            self.assertTrue(r["is_error"])
            self.assertIn("skipped due to user interrupt", r["content"])


class OrderPreservedTest(unittest.TestCase):
    def test_results_preserve_input_order(self):
        agent = _FakeAgent([_echo_tool()])
        ids = [f"tc_{i}" for i in range(5)]
        calls = [_call("echo", {"i": i}, call_id=ids[i]) for i in range(5)]
        out = execute_tool_calls_sequential(agent, calls)
        self.assertEqual([r["tool_use_id"] for r in out], ids)


if __name__ == "__main__":
    unittest.main()
