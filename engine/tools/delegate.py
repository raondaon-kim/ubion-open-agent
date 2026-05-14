# Copyright (c) 2026 Ubion ax center
#
# Inspired by NousResearch/hermes-agent tools/delegate_tool.py (MIT).
# The upstream module is ~2700 lines covering OpenAI/Anthropic specifics,
# OpenRouter provider routing, ACP integration, gateway approval flows,
# kill-switch RPCs, etc. — far past what a single-user local Phase 1
# scenario needs. This file keeps the *algorithm* (depth-limited child
# spawn, batch ThreadPoolExecutor, isolation invariants) but rewrites
# the skeleton against our own AIAgent.
"""Delegation tool — spawn child AIAgent instances for focused subtasks.

Why delegate?
    The parent's context window stays small even when a multi-step task
    blows through a hundred tool calls. Each child runs in a *fresh
    conversation* with no parent history and no parent memory: it just
    gets a focused goal + optional context blob, executes, and returns a
    JSON summary the parent reads as a single tool_result.

Phase 1 surface:
    delegate_task(
        goal:        str | None,        # single mode
        context:     str | None,
        tasks:       list[dict] | None, # batch mode (parallel)
        max_iterations: int | None,     # optional per-child budget
    ) -> str  # JSON: {"results": [...]}

Single vs batch:
    Provide either ``goal`` (one task) or ``tasks`` (a list of
    ``{"goal": "...", "context": "..."}`` dicts, run in parallel with a
    ThreadPoolExecutor capped at MAX_CONCURRENT_CHILDREN).

Isolation invariants (must hold or we break the "small context" promise):
    1. Children inherit ALL parent tools *except* ``delegate_task``
       itself (no recursive fan-out) and a few side-effect tools we
       refuse to give a sub-process (``memory``, ``skill_manage`` for
       writes — explicit on the parent only).
    2. Children get a *brand new* IterationBudget and a *brand new*
       conversation. Parent transcript is never passed in.
    3. Children get ``skip_context_files=True`` and ``skip_memory=True``
       so SOUL.md / MEMORY.md side-channels stay on the parent only.
    4. Depth limit (default 2) — children of children of children are
       refused so a buggy prompt can't fork-bomb.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Tools a child must never receive. Mirrors Hermes' DELEGATE_BLOCKED_TOOLS
# but trimmed to the ones we actually register on the parent.
DELEGATE_BLOCKED_TOOLS = frozenset(
    [
        "delegate_task",  # no recursive delegation (depth limit also enforces)
        "memory",         # no shared MEMORY.md writes from a worker
    ]
)

# Hard caps — kept small because Phase 1 is single-user local.
DEFAULT_MAX_SPAWN_DEPTH = 2
DEFAULT_MAX_CONCURRENT_CHILDREN = 4
DEFAULT_CHILD_MAX_ITERATIONS = 40   # plenty for a focused single subtask
PER_CHILD_TIMEOUT_S = 600            # 10 min runaway guard


DELEGATE_SCHEMA = {
    "name": "delegate_task",
    "description": (
        "Spawn a child agent to handle a focused subtask in a fresh "
        "conversation. The child sees no parent history — pass everything "
        "it needs in `context`. Use this when:\n"
        "  • A subtask would otherwise burn many tool calls in YOUR "
        "conversation (e.g. web research, multi-step file generation, "
        "running a long script and summarizing).\n"
        "  • Two independent things can run in parallel (pass `tasks=[...]`).\n"
        "\nReturns JSON: {\"results\": [{\"summary\": str, \"status\": "
        "\"ok\"|\"error\", \"api_calls\": int, \"duration_s\": float}, ...]}\n"
        "The child has the same tools you do EXCEPT delegate_task itself "
        "(no recursion). Children cannot ask the user clarifying questions "
        "— give them enough context up front."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": (
                    "The single subtask, written as a directive to a "
                    "fresh agent that has zero context. Example: "
                    "'Read D:/poems/draft.md, write a 3-line critique "
                    "of its closing image to D:/poems/draft.review.md.'"
                ),
            },
            "context": {
                "type": "string",
                "description": (
                    "Background facts, paths, links the child needs. "
                    "Children do NOT see your conversation, so paste "
                    "anything load-bearing here."
                ),
            },
            "tasks": {
                "type": "array",
                "description": (
                    "Batch mode: list of {goal, context} dicts to run "
                    "in parallel. Use when subtasks are independent. "
                    "Mutually exclusive with `goal`."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "goal":    {"type": "string"},
                        "context": {"type": "string"},
                    },
                    "required": ["goal"],
                },
            },
            "max_iterations": {
                "type": "integer",
                "description": (
                    "Optional cap on the child's iteration count. "
                    f"Default: {DEFAULT_CHILD_MAX_ITERATIONS}. "
                    "Raise only when the subtask genuinely needs many "
                    "tool calls; high values inflate cost."
                ),
                "minimum": 1,
                "maximum": 200,
            },
        },
    },
}


def _tool_error(msg: str, **extra: Any) -> str:
    payload = {"success": False, "error": msg}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _build_child(
    *,
    parent_agent: Any,
    goal: str,
    context: Optional[str],
    max_iterations: int,
    task_index: int,
) -> Any:
    """Construct a child AIAgent with isolation guarantees.

    The child receives the parent's tool catalogue minus
    DELEGATE_BLOCKED_TOOLS. Memory / context / SOUL bypassed so the
    parent stays the single source of identity.
    """
    from engine.core.agent import AIAgent, Tool

    # Subset the parent tools — copy the Tool objects (handlers are
    # idempotent and stateless; reusing them keeps registration cheap).
    child_tools: List[Tool] = [
        t
        for t in parent_agent._tools.values()
        if t.name not in DELEGATE_BLOCKED_TOOLS
    ]

    # Compose a single-shot system prompt so the child knows what it's
    # for. We deliberately do NOT inherit parent.system_prompt — that
    # carries SOUL.md / skills index, which would double the child's
    # context for no benefit (the child has the same skills index
    # already because get_all_skills_dirs() is process-wide).
    child_system_prompt = _build_child_system_prompt(goal, context)

    child = AIAgent(
        model=parent_agent.model,
        provider=parent_agent.provider,
        api_key=parent_agent.api_key,
        base_url=parent_agent.base_url,
        max_iterations=max_iterations,
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
        tools=child_tools,
        system_prompt=child_system_prompt,
        # iteration_budget=None → AIAgent constructs a fresh one
        # scoped to this child only.
    )

    # Bookkeeping: depth ticks up so a child of a child gets refused.
    parent_depth = getattr(parent_agent, "_delegate_depth", 0)
    child._delegate_depth = parent_depth + 1
    child._delegate_role = "leaf"
    return child


_CHILD_SYSTEM_PROMPT_TEMPLATE = """\
You are a focused subagent spawned by a parent agent to handle ONE task.

Constraints you must respect:
  • You have no view of the parent's conversation. Everything you need
    is in your goal + context below.
  • You cannot ask the user clarifying questions — make a reasonable
    judgement and finish.
  • Once you have the answer, reply with the final result text.
    Do NOT pad with status updates; the parent only sees your last
    message.

## Your goal
{goal}
{context_section}"""


def _build_child_system_prompt(goal: str, context: Optional[str]) -> str:
    if context and context.strip():
        ctx_section = f"\n## Context (load-bearing facts)\n{context.strip()}\n"
    else:
        ctx_section = ""
    return _CHILD_SYSTEM_PROMPT_TEMPLATE.format(
        goal=goal.strip(),
        context_section=ctx_section,
    )


def _run_single(
    *,
    child: Any,
    goal: str,
    task_index: int,
) -> Dict[str, Any]:
    """Execute one child synchronously. Never raises — packs failures into the dict."""
    started = time.monotonic()
    goal_preview = goal[:80].replace("\n", " ") + ("..." if len(goal) > 80 else "")
    logger.info(
        "delegate child %d START goal=%r depth=%d",
        task_index, goal_preview, getattr(child, "_delegate_depth", "?"),
    )
    try:
        out = child.run_conversation(user_message=goal)
        elapsed = time.monotonic() - started
        status = "ok" if not out.get("error") else "error"
        logger.info(
            "delegate child %d DONE status=%s api_calls=%d tools=%d dur=%.1fs",
            task_index, status,
            int(out.get("api_calls", 0) or 0),
            int(out.get("tool_calls_made", 0) or 0),
            elapsed,
        )
        return {
            "task_index": task_index,
            "status": status,
            "summary": out.get("final_response", ""),
            "exit_reason": out.get("exit_reason", ""),
            "api_calls": int(out.get("api_calls", 0) or 0),
            "tool_calls_made": int(out.get("tool_calls_made", 0) or 0),
            "duration_s": round(elapsed, 2),
            "error": out.get("error"),
        }
    except Exception as exc:
        elapsed = time.monotonic() - started
        logger.exception("child agent %d crashed: %s", task_index, exc)
        return {
            "task_index": task_index,
            "status": "error",
            "summary": "",
            "exit_reason": "crashed",
            "api_calls": 0,
            "tool_calls_made": 0,
            "duration_s": round(elapsed, 2),
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        try:
            child.close()
        except Exception:  # noqa: BLE001 — defensive
            pass


def delegate_task(
    args: Dict[str, Any],
    *,
    parent_agent: Any = None,
) -> str:
    """Tool handler — registered with parent_agent baked in via closure."""
    if parent_agent is None:
        return _tool_error(
            "delegate_task requires a parent agent context. This is a "
            "registration bug — the handler must be a closure over the "
            "parent AIAgent."
        )

    # Depth limit — refuse before doing any work so the parent gets a
    # clean error message it can read and recover from.
    depth = getattr(parent_agent, "_delegate_depth", 0)
    if depth >= DEFAULT_MAX_SPAWN_DEPTH:
        return _tool_error(
            f"delegation depth limit reached (depth={depth}, "
            f"max={DEFAULT_MAX_SPAWN_DEPTH}). Children of children of "
            "children are refused to prevent runaway fan-out. Restructure "
            "the work into fewer levels."
        )

    args = args or {}
    goal = (args.get("goal") or "").strip()
    tasks_raw = args.get("tasks")
    requested_max_iter = args.get("max_iterations")
    try:
        max_iter = (
            int(requested_max_iter)
            if requested_max_iter is not None
            else DEFAULT_CHILD_MAX_ITERATIONS
        )
    except (TypeError, ValueError):
        max_iter = DEFAULT_CHILD_MAX_ITERATIONS
    max_iter = max(1, min(max_iter, 200))

    # Normalize to a task list. Single goal becomes a one-element batch.
    task_list: List[Dict[str, Any]] = []
    if tasks_raw and isinstance(tasks_raw, list):
        if goal:
            return _tool_error(
                "provide either 'goal' (single) OR 'tasks' (batch), not both."
            )
        for i, t in enumerate(tasks_raw):
            if not isinstance(t, dict):
                return _tool_error(
                    f"task {i} must be an object with at least 'goal'."
                )
            sub_goal = (t.get("goal") or "").strip()
            if not sub_goal:
                return _tool_error(f"task {i} is missing 'goal'.")
            task_list.append({"goal": sub_goal, "context": t.get("context")})
        if len(task_list) > DEFAULT_MAX_CONCURRENT_CHILDREN:
            return _tool_error(
                f"too many tasks: {len(task_list)} provided, cap is "
                f"{DEFAULT_MAX_CONCURRENT_CHILDREN}. Split into multiple "
                "delegate_task calls."
            )
    elif goal:
        task_list = [{"goal": goal, "context": args.get("context")}]
    else:
        return _tool_error(
            "provide either 'goal' (single) or 'tasks' (batch)."
        )

    # Build children on the main thread — AIAgent construction does a
    # bunch of imports + an LLM client init, which is fine sequentially
    # but messy from N parallel threads.
    children = []
    for i, t in enumerate(task_list):
        child = _build_child(
            parent_agent=parent_agent,
            goal=t["goal"],
            context=t.get("context"),
            max_iterations=max_iter,
            task_index=i,
        )
        children.append((i, t, child))

    logger.info(
        "delegate_task: spawning %d child agent(s), depth=%d→%d, max_iter=%d",
        len(children), depth, depth + 1, max_iter,
    )

    results: List[Dict[str, Any]] = []

    if len(children) == 1:
        # Skip the threadpool overhead for the common single case.
        i, t, child = children[0]
        results.append(_run_single(child=child, goal=t["goal"], task_index=i))
    else:
        with ThreadPoolExecutor(max_workers=DEFAULT_MAX_CONCURRENT_CHILDREN) as ex:
            futures = {
                ex.submit(_run_single, child=c, goal=t["goal"], task_index=i): i
                for (i, t, c) in children
            }
            pending = set(futures.keys())
            deadline = time.monotonic() + PER_CHILD_TIMEOUT_S * len(children)

            while pending:
                # Bail on parent interrupt — collect whatever finished so
                # the parent at least sees partial progress.
                if getattr(parent_agent, "_interrupt_requested", False):
                    for f in pending:
                        idx = futures[f]
                        if f.done():
                            try:
                                results.append(f.result())
                            except Exception as exc:  # noqa: BLE001
                                results.append({
                                    "task_index": idx,
                                    "status": "error",
                                    "summary": "",
                                    "error": str(exc),
                                })
                        else:
                            results.append({
                                "task_index": idx,
                                "status": "interrupted",
                                "summary": "",
                                "error": "parent interrupted before child finished",
                            })
                    break

                if time.monotonic() > deadline:
                    logger.warning(
                        "delegate_task: batch deadline elapsed, "
                        "abandoning %d pending future(s)", len(pending),
                    )
                    for f in pending:
                        idx = futures[f]
                        results.append({
                            "task_index": idx,
                            "status": "timeout",
                            "summary": "",
                            "error": "child did not finish before batch deadline",
                        })
                    break

                done, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                for fut in done:
                    try:
                        results.append(fut.result())
                    except Exception as exc:  # noqa: BLE001
                        results.append({
                            "task_index": futures[fut],
                            "status": "error",
                            "summary": "",
                            "error": f"{type(exc).__name__}: {exc}",
                        })

    # Sort by task_index so the response order matches the input order
    # even when threads complete out of order.
    results.sort(key=lambda r: r.get("task_index", 0))
    return json.dumps({"results": results}, ensure_ascii=False)


def build_delegate_tool(parent_agent: Any) -> Any:
    """Return a Tool dataclass with parent_agent captured in the closure.

    Called from AIAgent.register_default_tools so the child-spawn handler
    can reach the live parent without the dispatcher having to learn a
    new signature.
    """
    from engine.core.agent import Tool

    return Tool(
        name=DELEGATE_SCHEMA["name"],
        description=DELEGATE_SCHEMA["description"],
        schema=DELEGATE_SCHEMA["input_schema"],
        handler=lambda args, _agent=parent_agent: delegate_task(args, parent_agent=_agent),
    )
