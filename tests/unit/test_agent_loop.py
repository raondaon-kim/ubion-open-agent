# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 3-2 — main while-loop exit-reason coverage.

Stubs the AnthropicClient with a deterministic FakeLLM so the loop can be
driven through every exit_reason without spending API budget. Run with:

    python -m unittest tests.unit.test_agent_loop -v
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional

from engine.core.agent import AIAgent, Tool
from engine.core.budget import IterationBudget
from engine.llm.anthropic import ChatResponse, ToolCall


class FakeLLM:
    """Scripted LLM. Each call pops one response off the script."""

    def __init__(self, script: List[ChatResponse]):
        self.script = list(script)
        self.calls: List[List[Dict[str, Any]]] = []

    def chat(self, *, messages, system=None, tools=None, max_tokens=None):
        self.calls.append(list(messages))
        if not self.script:
            raise RuntimeError("FakeLLM exhausted")
        return self.script.pop(0)


def _text(t: str) -> ChatResponse:
    return ChatResponse(text=t, tool_calls=[], stop_reason="end_turn",
                        usage={}, raw=None)


def _tool(name: str, args: Optional[Dict[str, Any]] = None, *,
          call_id: str = "tool_1", text: str = "") -> ChatResponse:
    return ChatResponse(
        text=text,
        tool_calls=[ToolCall(id=call_id, name=name, arguments=args or {})],
        stop_reason="tool_use",
        usage={},
        raw=None,
    )


def _build_agent(script: List[ChatResponse], *, max_iterations: int = 5,
                 budget: Optional[IterationBudget] = None,
                 tools: Optional[List[Tool]] = None) -> AIAgent:
    agent = AIAgent(
        model="claude-opus-4-7",
        api_key="sk-test-fake",  # AnthropicClient never used in tests
        max_iterations=max_iterations,
        iteration_budget=budget,
        tools=tools,
        quiet_mode=True,
    )
    agent._llm = FakeLLM(script)
    return agent


class CompletedPathTest(unittest.TestCase):
    def test_single_turn_text_response(self):
        agent = _build_agent([_text("hello")])
        result = agent.run_conversation(user_message="hi")
        self.assertEqual(result["exit_reason"], "completed")
        self.assertEqual(result["final_response"], "hello")
        self.assertEqual(result["api_calls"], 1)
        self.assertEqual(result["tool_calls_made"], 0)
        self.assertTrue(result["task_id"])  # uuid minted


class ToolThenAnswerTest(unittest.TestCase):
    def test_one_tool_then_text(self):
        echo_tool = Tool(
            name="echo",
            description="echo back",
            schema={"type": "object", "properties": {"v": {"type": "string"}},
                    "required": ["v"]},
            handler=lambda args: f"echoed:{args.get('v')}",
        )
        agent = _build_agent(
            script=[_tool("echo", {"v": "x"}), _text("done")],
            tools=[echo_tool],
        )
        result = agent.run_conversation(user_message="run echo")
        self.assertEqual(result["exit_reason"], "completed")
        self.assertEqual(result["final_response"], "done")
        self.assertEqual(result["api_calls"], 2)
        self.assertEqual(result["tool_calls_made"], 1)


class MaxIterationsTest(unittest.TestCase):
    def test_max_iterations_exit_reason(self):
        # Three tool turns, but max_iterations=2 -> we trip the ceiling
        # *before* the third call.
        echo_tool = Tool(
            name="echo", description="echo back",
            schema={"type": "object", "properties": {}},
            handler=lambda args: "ok",
        )
        agent = _build_agent(
            script=[_tool("echo"), _tool("echo"), _tool("echo")],
            max_iterations=2,
            tools=[echo_tool],
        )
        result = agent.run_conversation(user_message="loop")
        self.assertEqual(result["exit_reason"], "max_iterations")
        self.assertEqual(result["api_calls"], 2)


class BudgetExhaustedTest(unittest.TestCase):
    def test_shared_budget_runs_out(self):
        echo_tool = Tool(
            name="echo", description="echo back",
            schema={"type": "object", "properties": {}},
            handler=lambda args: "ok",
        )
        # Budget=1 means we can do exactly one consume() and then it's gone.
        budget = IterationBudget(1)
        agent = _build_agent(
            script=[_tool("echo"), _tool("echo")],
            max_iterations=10,
            budget=budget,
            tools=[echo_tool],
        )
        result = agent.run_conversation(user_message="loop")
        self.assertEqual(result["exit_reason"], "budget_exhausted")
        self.assertEqual(result["api_calls"], 1)


class InterruptedTest(unittest.TestCase):
    def test_interrupt_before_first_call(self):
        agent = _build_agent([_text("never seen")])
        agent._interrupt_requested = True
        result = agent.run_conversation(user_message="hi")
        self.assertEqual(result["exit_reason"], "interrupted_by_user")
        self.assertEqual(result["api_calls"], 0)

    def test_interrupt_mid_loop_after_tool(self):
        """Tool handler flips the interrupt flag; the loop should bail
        out before the next LLM call (api_calls stays at 1)."""
        agent_ref: Dict[str, Any] = {}

        def flip_interrupt(_args):
            agent_ref["agent"]._interrupt_requested = True
            return "ok"

        flipper = Tool(
            name="flip",
            description="flip interrupt mid-turn",
            schema={"type": "object", "properties": {}},
            handler=flip_interrupt,
        )
        agent = _build_agent(
            script=[_tool("flip"), _text("should never reach")],
            tools=[flipper],
        )
        agent_ref["agent"] = agent
        result = agent.run_conversation(user_message="trigger")
        self.assertEqual(result["exit_reason"], "interrupted_by_user")
        self.assertEqual(result["api_calls"], 1)
        self.assertEqual(result["tool_calls_made"], 1)
        # final_response must remain empty — we never observed the second turn
        self.assertEqual(result["final_response"], "")


class RetryExhaustedTest(unittest.TestCase):
    def test_all_retries_exhausted_returns_error(self):
        agent = _build_agent([])  # empty script -> RuntimeError each retry
        # Trim retry count so the test stays fast (default is 6 with backoff).
        agent.max_retries_per_call = 2

        # Disable backoff sleep entirely so the test doesn't spend ~10s.
        import engine.core.agent as agent_mod
        original_sleep = agent_mod.time.sleep
        agent_mod.time.sleep = lambda _s: None
        try:
            result = agent.run_conversation(user_message="hi")
        finally:
            agent_mod.time.sleep = original_sleep

        self.assertEqual(result["exit_reason"], "all_retries_exhausted")
        self.assertEqual(result["api_calls"], 1)
        # error field stays empty unless the try/except guard triggered;
        # _call_llm_with_retry logs but doesn't surface error to result.
        # That's intentional — exit_reason is the source of truth.


class MultiTurnHistoryTest(unittest.TestCase):
    def test_conversation_history_carries_into_loop(self):
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi back"},
        ]
        agent = _build_agent([_text("ok")])
        result = agent.run_conversation(
            user_message="follow up",
            conversation_history=history,
        )
        self.assertEqual(result["exit_reason"], "completed")
        self.assertEqual(result["api_calls"], 1)
        # FakeLLM stored the messages it saw — confirm history + new user
        # turn both made it across.
        seen = agent._llm.calls[0]
        self.assertEqual(len(seen), 3)
        self.assertEqual(seen[0]["content"], "hello")
        self.assertEqual(seen[1]["content"], "hi back")
        self.assertEqual(seen[2]["content"], "follow up")

    def test_history_is_not_mutated_by_loop(self):
        history = [{"role": "user", "content": "h"}]
        snapshot = list(history)
        agent = _build_agent([_text("ok")])
        agent.run_conversation(
            user_message="next",
            conversation_history=history,
        )
        # Caller's list must remain unchanged — the loop copies it.
        self.assertEqual(history, snapshot)


class TaskIdTest(unittest.TestCase):
    def test_caller_task_id_preserved(self):
        agent = _build_agent([_text("ok")])
        result = agent.run_conversation(
            user_message="hi",
            task_id="caller-supplied-id-123",
        )
        self.assertEqual(result["task_id"], "caller-supplied-id-123")

    def test_minted_task_id_is_uuid_length(self):
        agent = _build_agent([_text("ok")])
        result = agent.run_conversation(user_message="hi")
        self.assertEqual(len(result["task_id"]), 36)  # uuid4 canonical


if __name__ == "__main__":
    unittest.main()
