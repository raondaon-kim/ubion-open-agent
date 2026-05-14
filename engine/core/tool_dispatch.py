# Ported from NousResearch/hermes-agent (MIT License)
# Original references:
#   - run_agent.py:10453 (_execute_tool_calls dispatch)
#   - run_agent.py:10495 (_invoke_tool single-call wrapper)
#   - run_agent.py:11019 (_execute_tool_calls_sequential, 445 lines)
#
# This is a *Port*, not a Vendor copy: the Hermes implementations are
# tightly bound to OpenAI-style tool_call objects, tool guardrails,
# checkpoint manager, activity callbacks, and an inline branch table for
# todo/memory/clarify/delegate/session_search. Our Phase 1 surface is
# Anthropic-native dataclass ToolCalls and a flat Tool registry, so we
# preserve the *meaning* of the upstream algorithm (interrupt skip,
# JSON-arg safety, tool_result shape) while rewriting the skeleton.
#
# Copyright (c) 2025 Nous Research (original algorithm)
# Copyright (c) 2026 Ubion ax center (implementation)
#
# This file is licensed under the MIT License. See engine/NOTICE.md.
"""Sequential tool-call dispatcher for AIAgent.

Phase 1 Unit 3-3 scope:
    - Cooperative interrupt: if _interrupt_requested flips during a tool
      run, skip every remaining tool_call and emit a placeholder tool_result
      for each (Anthropic requires every tool_use id to have a matching
      tool_result on the next user turn).
    - JSON argument safety: arguments may arrive as dict (Anthropic native)
      or as a JSON string (after our agent transcript round-trip). Parse
      defensively; coerce to {} on failure.
    - Handler exceptions never bubble: catch and surface as is_error=True
      tool_result blocks.

Explicitly NOT ported in this unit (see research/run-agent-split-plan.md):
    - Tool guardrails (Phase 3)
    - Plugin pre-tool-call block hooks (Phase 2)
    - Checkpoint manager (Unit 11)
    - Activity callback / inactivity monitor (Phase 2)
    - Concurrent execution path (Phase 2 performance)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping

from engine.llm.anthropic import ToolCall

logger = logging.getLogger(__name__)


# Sentinel error used by Anthropic SDK clients to detect tool failures.
TOOL_ERROR_TYPE = "tool_result"

_SKIPPED_MARKER = (
    "[Tool execution cancelled — {name} was skipped due to user interrupt]"
)


def _coerce_arguments(raw: Any) -> Dict[str, Any]:
    """Return a dict regardless of how the model serialized its arguments.

    Anthropic returns `input` as a dict already; replaying through our own
    transcript format flattens it back to JSON text. Either form is valid;
    anything else collapses to {}.
    """
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("tool arg JSON parse failed (%s); using {}", exc)
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _stringify_tool_value(value: Any) -> str:
    """Coerce a tool handler's return into the string Anthropic expects."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _skip_block(call: ToolCall) -> Dict[str, Any]:
    return {
        "type": TOOL_ERROR_TYPE,
        "tool_use_id": call.id,
        "content": _SKIPPED_MARKER.format(name=call.name),
        "is_error": True,
    }


def _error_block(call: ToolCall, message: str) -> Dict[str, Any]:
    return {
        "type": TOOL_ERROR_TYPE,
        "tool_use_id": call.id,
        "content": message,
        "is_error": True,
    }


def _ok_block(call: ToolCall, value: Any) -> Dict[str, Any]:
    return {
        "type": TOOL_ERROR_TYPE,
        "tool_use_id": call.id,
        "content": _stringify_tool_value(value),
    }


def execute_tool_calls_sequential(
    agent: Any,
    tool_calls: List[ToolCall],
) -> List[Dict[str, Any]]:
    """Run each tool_call serially; honour interrupt mid-batch.

    `agent` must expose `_tools: dict[str, Tool]` and `_interrupt_requested:
    bool`. The returned list always has the same length as `tool_calls` and
    preserves order (Anthropic pairs tool_result blocks to tool_use ids in
    the next user message — every id needs a match).
    """
    results: List[Dict[str, Any]] = []
    interrupted = False

    for index, call in enumerate(tool_calls):
        if interrupted or getattr(agent, "_interrupt_requested", False):
            # Once we trip, every remaining call gets a skip block.
            # The flag may flip mid-loop (tool A flips it while running)
            # so we sticky-bit it here to keep ordering consistent even
            # if the agent clears _interrupt_requested later.
            interrupted = True
            results.append(_skip_block(call))
            continue

        tool = agent._tools.get(call.name) if hasattr(agent, "_tools") else None
        if tool is None:
            results.append(_error_block(call, f"error: unknown tool {call.name!r}"))
            continue

        args = _coerce_arguments(call.arguments)
        try:
            value = tool.handler(args)
        except Exception as exc:
            logger.exception("Tool %s raised: %s", call.name, exc)
            results.append(
                _error_block(call, f"error: {type(exc).__name__}: {exc}")
            )
            # Hermes' sequential path keeps going after a single failure
            # so the model can read the error block and recover. Do the
            # same here — do NOT trip `interrupted`.
            continue

        results.append(_ok_block(call, value))

    return results
