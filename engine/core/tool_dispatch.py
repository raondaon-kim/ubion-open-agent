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
import time
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

    Logging contract: every dispatch — start, finish, error, skip — is
    logged at INFO so server.log shows the agent's actual move list.
    Without this, "quiet" tools (skill_view, todo, memory, delegate)
    leave no trace and `server.log` looks like the agent is hanging
    when it's actually executing a sequence the user can't see.
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
            logger.info("tool dispatch: SKIP %s (interrupted)", call.name)
            results.append(_skip_block(call))
            continue

        tool = agent._tools.get(call.name) if hasattr(agent, "_tools") else None
        if tool is None:
            logger.warning("tool dispatch: UNKNOWN %s", call.name)
            results.append(_error_block(call, f"error: unknown tool {call.name!r}"))
            continue

        args = _coerce_arguments(call.arguments)
        # Log the start with a short arg preview so we can read the
        # trace without dumping huge schemas. Skip giant args (file
        # contents etc.) past ~200 chars — they live in the result
        # block when needed.
        arg_preview = _summarize_args(args)
        depth = getattr(agent, "_delegate_depth", 0)
        depth_prefix = "  " * depth + (f"[depth={depth}] " if depth else "")
        logger.info(
            "%stool dispatch: START %s(%s)",
            depth_prefix, call.name, arg_preview,
        )
        t0 = time.monotonic()
        try:
            value = tool.handler(args)
        except Exception as exc:
            elapsed = time.monotonic() - t0
            logger.exception(
                "%stool dispatch: ERROR %s after %.2fs: %s",
                depth_prefix, call.name, elapsed, exc,
            )
            results.append(
                _error_block(call, f"error: {type(exc).__name__}: {exc}")
            )
            # Hermes' sequential path keeps going after a single failure
            # so the model can read the error block and recover. Do the
            # same here — do NOT trip `interrupted`.
            continue

        elapsed = time.monotonic() - t0
        result_preview = _summarize_result(value)
        logger.info(
            "%stool dispatch: DONE  %s after %.2fs → %s",
            depth_prefix, call.name, elapsed, result_preview,
        )
        results.append(_ok_block(call, value))

    return results


def _summarize_args(args: Dict[str, Any]) -> str:
    """One-line preview of a tool's arguments for the start log.

    Keep it under ~200 chars total so server.log stays readable. Long
    string values get truncated to their first 80 chars; the full
    payload (file contents, base64 blobs, etc.) lives in the result
    block when the model needs to reason about it.
    """
    if not isinstance(args, dict) or not args:
        return ""
    parts: List[str] = []
    for key, value in args.items():
        if isinstance(value, str):
            preview = value if len(value) <= 80 else value[:77] + "..."
            parts.append(f"{key}={preview!r}")
        elif isinstance(value, (int, float, bool)) or value is None:
            parts.append(f"{key}={value!r}")
        elif isinstance(value, (list, tuple)):
            parts.append(f"{key}=<{type(value).__name__} len={len(value)}>")
        elif isinstance(value, dict):
            parts.append(f"{key}=<dict keys={list(value)[:4]}>")
        else:
            parts.append(f"{key}=<{type(value).__name__}>")
    summary = ", ".join(parts)
    if len(summary) > 200:
        summary = summary[:197] + "..."
    return summary


def _summarize_result(value: Any) -> str:
    """One-line preview of a tool result for the DONE log.

    JSON-shaped strings (most of our tools return those) are flattened
    to their top-level keys so the log is greppable. Plain strings get
    truncated. Falls through to ``type(value).__name__`` for anything
    else so we never raise from inside the logger.
    """
    try:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                except Exception:  # noqa: BLE001
                    parsed = None
                if isinstance(parsed, dict):
                    keys = list(parsed)[:6]
                    extra = "" if len(parsed) <= 6 else f", ...{len(parsed)-6} more"
                    return f"dict({', '.join(keys)}{extra})"
                if isinstance(parsed, list):
                    return f"list(len={len(parsed)})"
            return repr(stripped[:120]) + ("..." if len(stripped) > 120 else "")
        return f"<{type(value).__name__}>"
    except Exception:  # noqa: BLE001 — never break logging
        return "<unprintable>"
