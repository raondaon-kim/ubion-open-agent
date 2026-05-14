# Ported from NousResearch/hermes-agent (MIT License)
# Original: https://github.com/NousResearch/hermes-agent/blob/b06e9993021a8eebd891fc60d52372446315b2f0/run_agent.py
# Surface narrowed: only the subset of run_conversation pre-turn setup that
# our Phase 1 Unit 3-1 scope actually needs. Compression preflight, plugin
# hooks, scrubbers, memory provider hookups, codex/qwen retry counters,
# vision flags, etc. stay in Hermes for now.
#
# Copyright (c) 2025 Nous Research (original algorithm)
# Copyright (c) 2026 Ubion ax center (implementation)
#
# This file is licensed under the MIT License. See engine/NOTICE.md.
"""Per-turn setup + teardown helpers for AIAgent.run_conversation.

Mirrors run_agent.py:11707-12100 (pre-turn block) at a much smaller surface.
Phase 1 Unit 3-1 scope only:
    - sanitize the inbound user_message (surrogate chars)
    - mint a task_id when caller didn't supply one
    - reset per-turn IterationBudget
    - hydrate the messages list from conversation_history
    - bump the user-turn counter that downstream nudge logic reads
    - bind interrupt state to the executing thread
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.core.budget import IterationBudget

logger = logging.getLogger(__name__)


@dataclass
class TurnContext:
    """State that lives for the duration of one run_conversation call.

    Fields with leading underscores in Hermes (e.g. _execution_thread_id)
    are exposed as plain names here — TurnContext is scoped to one turn so
    name-collision concerns from the AIAgent instance don't apply.
    """

    messages: List[Dict[str, Any]] = field(default_factory=list)
    task_id: str = ""
    user_turn_count: int = 0
    execution_thread_id: Optional[int] = None
    original_user_message: str = ""


def sanitize_user_message(value: Any) -> Any:
    """Strip lone UTF-16 surrogates that crash JSON encoders.

    Hermes' _sanitize_surrogates (run_agent.py:616) handles clipboard paste
    from Word/Google Docs etc. We mirror it for str inputs and pass other
    types through unchanged — multimodal payloads are out of scope until
    Phase 2.
    """
    if not isinstance(value, str):
        return value
    cleaned = value.encode("utf-8", "surrogatepass").decode("utf-8", "replace")
    return cleaned


def mint_task_id(supplied: Optional[str] = None) -> str:
    """Return the caller-supplied task_id or a fresh uuid4 string.

    Hermes uses task_id to scope VM/tool isolation between concurrent
    sub-agents. We don't have concurrent sub-agents in Phase 1 but adopt
    the same shape so curator-style consumers can pass task_id through
    unchanged.
    """
    return supplied or str(uuid.uuid4())


def reset_iteration_budget(
    agent: Any,
    *,
    max_iterations: Optional[int] = None,
) -> IterationBudget:
    """Mint a fresh per-turn IterationBudget on the agent.

    Hermes assigns a new IterationBudget at run_agent.py:11809. The
    constructor budget gets exhausted across turns otherwise — a user's
    second turn would inherit the depleted counter from the first.

    Exception: when the agent's budget was supplied externally (parent →
    sub-agent sharing), we leave it alone. Resetting a shared counter
    would silently refill the parent's quota on every sub-turn.
    """
    if getattr(agent, "_budget_externally_supplied", False):
        return agent.iteration_budget
    ceiling = max_iterations if max_iterations is not None else agent.max_iterations
    agent.iteration_budget = IterationBudget(ceiling)
    return agent.iteration_budget


def hydrate_messages(
    conversation_history: Optional[List[Dict[str, Any]]],
    user_message: str,
) -> List[Dict[str, Any]]:
    """Build the per-turn `messages` list.

    The caller's `conversation_history` is copied (not aliased) so a
    crashing turn cannot leave half-written tool_use blocks in the
    caller's list. The fresh user turn is appended last.
    """
    messages: List[Dict[str, Any]] = (
        list(conversation_history) if conversation_history else []
    )
    messages.append({"role": "user", "content": user_message})
    return messages


def bump_user_turn_count(agent: Any, conversation_history: Optional[List[Dict[str, Any]]]) -> int:
    """Hydrate then increment agent._user_turn_count for this turn.

    Hermes does this at run_agent.py:11840-11859 to keep memory-nudge cadence
    correct when the gateway rebuilds a fresh AIAgent for a continuing
    session. Phase 1 has no gateway cache yet, but counter shape needs to
    match for Unit 6 (memory manager) to read consistent state.
    """
    current = getattr(agent, "_user_turn_count", 0) or 0
    if current == 0 and conversation_history:
        prior = sum(1 for m in conversation_history if m.get("role") == "user")
        current = prior
    current += 1
    agent._user_turn_count = current
    return current


def bind_interrupt_thread(agent: Any) -> int:
    """Record the OS thread that runs this turn so interrupt() can target it.

    Hermes' interrupt path (run_agent.py:5174) signals a specific thread
    rather than the whole process. We persist the same identifier even
    though our Phase 1 interrupt is cooperative (poll flag, no signal).
    """
    tid = threading.current_thread().ident or 0
    agent._execution_thread_id = tid
    if not getattr(agent, "_interrupt_requested", False):
        agent._interrupt_message = None
    return tid


def setup_turn(
    agent: Any,
    *,
    user_message: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    task_id: Optional[str] = None,
    persist_user_message: Optional[str] = None,
) -> TurnContext:
    """One-call entry point — runs the full Unit 3-1 pre-turn sequence.

    Returns the TurnContext that the main loop reads. Stateful side
    effects on the agent (iteration_budget reset, _user_turn_count++,
    _execution_thread_id) match Hermes' shape for the subset we support.
    """
    user_message = sanitize_user_message(user_message)
    persist_user_message = sanitize_user_message(persist_user_message)
    original = persist_user_message if isinstance(persist_user_message, str) else user_message

    reset_iteration_budget(agent)

    ctx = TurnContext(
        messages=hydrate_messages(conversation_history, user_message),
        task_id=mint_task_id(task_id),
        user_turn_count=bump_user_turn_count(agent, conversation_history),
        execution_thread_id=bind_interrupt_thread(agent),
        original_user_message=original or "",
    )
    return ctx
