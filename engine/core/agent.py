# Ported from NousResearch/hermes-agent (MIT License)
# Original: https://github.com/NousResearch/hermes-agent/blob/b06e9993021a8eebd891fc60d52372446315b2f0/run_agent.py
# Rewritten in Ubion conventions; algorithm (loop termination, tool dispatch,
# retry classification) preserved, surface drastically narrowed.
#
# Copyright (c) 2025 Nous Research (original algorithm)
# Copyright (c) 2026 Ubion ax center (implementation)
#
# This file is licensed under the MIT License. See engine/NOTICE.md.
"""AIAgent — Phase 1 Unit 2 minimum core.

Surface mirrors the subset of run_agent.AIAgent that engine.learning.curator
actually uses (curator.py:1709-1771 in the vendored copy):

    AIAgent(
        model: str,
        provider: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        api_mode: str | None = None,
        max_iterations: int = 90,
        quiet_mode: bool = True,
        platform: str = "engine",
        skip_context_files: bool = True,
        skip_memory: bool = True,
        iteration_budget: IterationBudget | None = None,
        tools: list[Tool] | None = None,
    )
    agent._memory_nudge_interval = 0
    agent._skill_nudge_interval = 0
    agent.run_conversation(user_message=...) -> {"final_response": str, ...}
    agent._session_messages: list[dict]
    agent.close()

Out of scope for Unit 2 (deferred to later units, marked with TODO[unit-N]):
    - Streaming callbacks (deferred to Unit 5)
    - Prompt builder integration (deferred to Unit 4)
    - Session DB / checkpoints (deferred to Unit 9)
    - Memory provider (deferred to Unit 6)
    - Provider fallback chain (deferred — only Anthropic in Phase 1)
    - Delegate tool, gateway session cache, MoA (per Unit 2 design doc)

Loop termination conditions ported from run_agent.py:12112-14857:
    - No tool_use blocks in response  -> success, set final_response, break
    - IterationBudget.consume() False -> "budget_exhausted", break
    - Self._interrupt_requested       -> "interrupted_by_user", break
    - Retry chain exhausted           -> "all_retries_exhausted", break

Retry handling:
    - LLM API errors classified via engine.core.errors.classify_api_error
    - jittered_backoff sleep between attempts
    - Hardcoded ceiling of 6 retries per LLM call (Hermes default)
    - On final failure: log + propagate as exit reason, no exception
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from engine.core.budget import IterationBudget
from engine.core.errors import classify_api_error, FailoverReason
from engine.core.retry import jittered_backoff
from engine.core.tool_dispatch import execute_tool_calls_sequential
from engine.core.turn_setup import TurnContext, setup_turn
from engine.llm.anthropic import ChatResponse

logger = logging.getLogger(__name__)


DEFAULT_MAX_ITERATIONS = 90
DEFAULT_MAX_RETRIES_PER_CALL = 6


@dataclass
class Tool:
    """A tool the agent can call.

    `schema` is the JSON Schema Anthropic expects in the `tools` request
    field. `handler` is a sync callable that takes the deserialized
    arguments dict and returns a result; the result is stringified into
    the tool_result content block.
    """

    name: str
    description: str
    schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Any]


@dataclass
class ConversationResult:
    """What run_conversation returns. Curator reads `final_response`."""

    final_response: str = ""
    exit_reason: str = ""
    api_calls: int = 0
    tool_calls_made: int = 0
    error: Optional[str] = None
    task_id: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "final_response": self.final_response,
            "exit_reason": self.exit_reason,
            "api_calls": self.api_calls,
            "tool_calls_made": self.tool_calls_made,
            "error": self.error,
            "task_id": self.task_id,
        }


class AIAgent:
    """Phase 1 Unit 2 agent core."""

    def __init__(
        self,
        *,
        model: str = "",
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        api_mode: Optional[str] = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        quiet_mode: bool = True,
        platform: str = "engine",
        skip_context_files: bool = True,
        skip_memory: bool = True,
        iteration_budget: Optional[IterationBudget] = None,
        tools: Optional[List[Tool]] = None,
        system_prompt: Optional[str] = None,
        max_retries_per_call: int = DEFAULT_MAX_RETRIES_PER_CALL,
        **_ignored: Any,
    ) -> None:
        # Provider only matters once we have more than Anthropic — Phase 1
        # Phase 1 supports Anthropic (Claude) + DeepSeek. Provider is
        # resolved further down via engine.llm.router based on model
        # name + optional explicit provider arg. api_mode reserved for
        # future bedrock/oauth routing.
        self.model = model or "deepseek-v4-flash"
        # `self.provider` is set below by the router (replaces the early
        # default-to-anthropic assignment that pre-dated Unit 13).
        self.api_key = api_key
        self.base_url = base_url
        self.api_mode = api_mode
        self.platform = platform
        self.quiet_mode = quiet_mode
        self.skip_context_files = skip_context_files
        self.skip_memory = skip_memory

        self.max_iterations = max_iterations
        self.iteration_budget = iteration_budget or IterationBudget(max_iterations)
        # When the caller supplied a budget, treat it as shared (e.g. with a
        # parent/sub-agent pair). Per-turn reset is skipped in that case so
        # the shared counter isn't silently refilled.
        self._budget_externally_supplied = iteration_budget is not None
        self.max_retries_per_call = max_retries_per_call

        # Curator writes these directly after construction. We accept the
        # writes; they have no effect in Unit 2 because we don't run the
        # nudge logic yet (Unit 4).
        self._memory_nudge_interval = 0
        self._skill_nudge_interval = 0

        # Auto-curator trigger (B-5, decision 2026-05-14). Increment each
        # successful run_conversation, fire curator on every Nth turn from a
        # background thread. 0 disables. Phase 1 (B) 시 시나리오 default = 1
        # (every session) to maximize learning signal during the 1-week
        # observation; Phase 3 may relax to 3-5.
        self._curator_trigger_interval = int(
            os.environ.get("UBION_CURATOR_INTERVAL", "1")
        )
        self._curator_turns_since_run = 0
        self._curator_thread = None  # last spawned thread (for tests)
        # Set by run_conversation when the caller wants fine-grained
        # progress events (used by the SSE chat endpoint).
        self._progress_callback: Optional[Any] = None

        # Delegation bookkeeping — depth ticks up each time
        # ``delegate_task`` spawns a child. Hard-capped in
        # ``engine.tools.delegate`` to prevent runaway fan-out. ``role``
        # is set by the parent when constructing this child; "leaf"
        # means we never re-register delegate_task on ourselves.
        self._delegate_depth: int = 0
        self._delegate_role: str = "root"

        # Transcript of API turns. Each entry is an Anthropic-shaped dict.
        # Curator walks this list at curator.py:1751 to pull tool_calls
        # into its report.
        self._session_messages: List[Dict[str, Any]] = []

        # Cancellation flag the gateway / CLI sets when the user hits ^C.
        # Unit 2 exposes the flag but has no async signal handler yet.
        self._interrupt_requested = False

        # Tools indexed by name for dispatch.
        self._tools: Dict[str, Tool] = {t.name: t for t in (tools or [])}
        # `tools` attribute mirrors the Anthropic-shape schemas so the
        # context compressor (Unit 5) can include schema tokens in its
        # request-size estimate.
        self.tools = [
            {"name": t.name, "description": t.description, "input_schema": t.schema}
            for t in self._tools.values()
        ] or None
        # `valid_tool_names` is the set the (future) prompt builder reads
        # to decide which capability blocks (skill_manage, memory,
        # session_search, …) to inject. Stays a set so it can be mutated
        # later when memory_manager registers external tools.
        self.valid_tool_names = set(self._tools.keys())

        # System prompt: caller-supplied takes precedence. When omitted,
        # _build_system_prompt() composes one from skills + memory + SOUL/USER
        # the first time the loop needs it (lazy — short-lived agents like
        # the curator review fork stay cheap).
        self._system_prompt = system_prompt or ""
        self._auto_build_system_prompt = system_prompt is None

        # LLM client. The router picks AnthropicClient or DeepSeekClient
        # based on the model name (Phase 1 Unit 13). Per-provider clients
        # share the same chat() surface so the agent loop is provider-blind.
        from engine.llm.router import build_client, resolve_provider
        self.provider = resolve_provider(self.model, explicit=provider)
        self._llm = build_client(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            provider=self.provider,
        )

        # Context compressor (Unit 5). Constructed lazily — building one
        # imports a 1300-line module + does a context-length lookup, which
        # is wasted work for short-lived calls (curator review, single-turn
        # smoke tests). compression_enabled gates the preflight check that
        # Unit 4 will wire up.
        self.context_compressor = None  # populated by _ensure_compressor()
        self.compression_enabled = True
        self._compression_warning: Optional[str] = None
        # Unit 9 (session_db) hook.
        self._session_db = None
        self.session_id = ""

        # Memory manager (Unit 6). Stays None until a caller attaches one
        # via _attach_memory_manager(). Every consumer in this class is
        # required to guard reads with `if self._memory_manager:` so the
        # "no memory yet" invariant (Phase 1 (B) day-1 user has empty
        # ~/.ubion-agent/memory/) holds — every public method must work
        # unchanged when the attribute is None.
        self._memory_manager = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_conversation(
        self,
        *,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        task_id: Optional[str] = None,
        persist_user_message: Optional[str] = None,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Run one user_message through the loop and return a result dict.

        Returns curator-shaped dict (see ConversationResult). Never raises;
        unexpected exceptions are caught and surfaced as ``error``.

        ``progress_callback`` — optional ``(event_type, payload) -> None``
        hook the loop calls at well-defined points so SSE callers can
        report fine-grained progress to the user. Events:

            * ``llm_call_started``   — about to call the LLM
            * ``tool_call_started``  — payload includes ``name``
            * ``tool_call_finished`` — payload includes ``name``, ``ok``
            * ``final_text``         — payload includes ``text``
            * ``done``               — payload includes ``exit_reason``

        The callback runs on the AIAgent's thread; keep it cheap and
        thread-safe.
        """
        result = ConversationResult()
        ctx = setup_turn(
            self,
            user_message=user_message,
            conversation_history=conversation_history,
            task_id=task_id,
            persist_user_message=persist_user_message,
        )
        result.task_id = ctx.task_id
        _msg_preview = ctx.original_user_message.replace("\n", " ")[:80]
        logger.info(
            "conversation turn: task=%s history=%d msg=%r",
            ctx.task_id, len(ctx.messages) - 1, _msg_preview,
        )
        # One-shot inventory log so server.log records what THIS turn
        # could call. Doesn't repeat per LLM iteration to keep the log
        # readable — but on a hang the tool list explains "is X even
        # registered for this turn?". Cheap to compute.
        depth = getattr(self, "_delegate_depth", 0)
        depth_tag = f"[d={depth}] " if depth else ""
        tool_names = sorted(self._tools.keys())
        logger.info(
            "%sturn inventory: model=%s tools=%d [%s] max_iter=%d",
            depth_tag,
            self.model,
            len(tool_names),
            ", ".join(tool_names),
            self.max_iterations,
        )
        # Attach the callback to ``self`` so _run_loop (and the helpers it
        # delegates to) can reach it without thread the parameter through
        # every internal API.
        self._progress_callback = progress_callback
        try:
            self._run_loop(ctx, result)
        except Exception as exc:  # last-resort guard around the loop
            logger.exception("Agent loop crashed: %s", exc)
            result.exit_reason = result.exit_reason or "loop_exception"
            result.error = f"{type(exc).__name__}: {exc}"
        finally:
            # Emit a terminal `done` event so SSE consumers can close their
            # stream regardless of which branch above exited the loop.
            self._emit_progress("done", {
                "exit_reason": result.exit_reason or "unknown",
                "error": result.error,
            })
            self._progress_callback = None
        # B-5: fire curator on every Nth successful turn — non-blocking,
        # best-effort. Skipped when the loop crashed (we don't want curator
        # judging a half-finished trajectory) or when the interval is 0.
        if not result.error and self._curator_trigger_interval > 0:
            self._curator_turns_since_run += 1
            if self._curator_turns_since_run >= self._curator_trigger_interval:
                self._curator_turns_since_run = 0
                self._spawn_curator_background()
        return result.as_dict()

    def _emit_progress(self, event: str, payload: Dict[str, Any]) -> None:
        """Fire one progress event if a callback is wired. Never raises."""
        cb = self._progress_callback
        if cb is None:
            return
        try:
            cb(event, payload)
        except Exception as exc:
            logger.debug("progress_callback raised %r — ignoring", exc)

    def _spawn_curator_background(self) -> None:
        """Run one curator pass on a daemon thread. Never raises.

        Hermes equivalent: cron job or post-session hook. Ours is in-process
        for Phase 1 simplicity — Phase 3 may move to a dedicated worker.
        """
        def _runner():
            try:
                from engine.learning.curator import maybe_run_curator
                summary_lines: list[str] = []
                result = maybe_run_curator(
                    on_summary=lambda s: summary_lines.append(s)
                )
                if result is not None:
                    logger.info(
                        "curator background pass complete: %s (summary lines=%d)",
                        result.get("status", "?"), len(summary_lines),
                    )
            except Exception as exc:  # noqa: BLE001 — best-effort
                logger.warning("curator background pass failed: %s", exc)

        t = threading.Thread(
            target=_runner,
            name="ubion-curator-bg",
            daemon=True,
        )
        t.start()
        self._curator_thread = t

    def close(self) -> None:
        """Release per-agent resources. No-op in Unit 2."""
        # The anthropic SDK manages its own connection pool. Tools may
        # need cleanup in later units; expose the hook now so callers
        # (curator) can call it unconditionally.
        return None

    def register_default_tools(
        self,
        *,
        include_file_ops: bool = True,
        include_session_search: bool = True,
        include_hermes_tier_a: bool = True,
        include_delegate: bool = True,
    ) -> None:
        """Attach the Phase 1 default toolset.

        Always includes:
          - skill_view  (Unit 2)
          - skill_manage (Unit 8 vendored manager)

        When `include_file_ops=True` (default) also attaches:
          - read_file, write_file, list_files  (Unit 8 file_ops Port, writes
            confined to the agent home via path_security).

        When `include_session_search=True` (default) also attaches:
          - session_search  (Unit 9 vendored session search; FTS5-backed
            via engine.storage.session_db).

        When `include_delegate=True` (default) also attaches:
          - delegate_task  — spawn a child AIAgent for a focused subtask
            in a fresh conversation. The handler is a closure over THIS
            agent so the child gets the right parent reference at call
            time. Children are forced to leaf-role so the same call site
            handles depth-limiting transparently.

        Idempotent — calling this twice doesn't duplicate entries.
        """
        from engine.skills import build_default_skill_tools
        from engine.storage.agent_home import ensure_bundled_skills_seeded
        from engine.tools.file_ops import build_default_file_tools

        # First-boot housekeeping: make sure agent_home/skills/{custom,installed}
        # directories exist so downstream tools don't trip over missing paths.
        # NB: this no longer copies the optional pool — Hermes-식 분리
        # (사용자 결정 2026-05-14): the agent starts with an *empty* skill
        # pool and the model uses ``skills_install`` to bring in optional
        # skills on demand. self-evolution populates ``skills/custom/``.
        try:
            ensure_bundled_skills_seeded()
        except Exception as exc:  # noqa: BLE001 — housekeeping is best-effort
            logger.warning("agent_home housekeeping failed: %s", exc)

        catalogue = list(build_default_skill_tools())
        if include_file_ops:
            catalogue.extend(build_default_file_tools())
        if include_session_search:
            from engine.tools import build_session_search_tool
            catalogue.append(build_session_search_tool())

        # Delegation is the OUR addition (Hermes ships its own 2700-line
        # version; we keep a ~350-line Phase 1 surface). A "leaf" child
        # never re-registers this on itself, both because the handler
        # passes the parent reference and because depth-limit refuses
        # the call anyway.
        if include_delegate and self._delegate_role != "leaf":
            from engine.tools.delegate import build_delegate_tool
            catalogue.append(build_delegate_tool(self))

        if include_hermes_tier_a:
            # Importing these modules triggers their module-level
            # `registry.register(...)` calls (Hermes convention). We then
            # walk the registry stub and lift the entries into our Tool
            # dataclasses so the Anthropic-shape tool list sees them.
            for modname in (
                "engine.tools.todo_tool",
                "engine.tools.memory_tool",
                "engine.tools.file_tools",
                "engine.tools.osv_check",
                "engine.tools.shell",
            ):
                try:
                    __import__(modname)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("could not import %s: %s", modname, exc)
            from engine.tools.registry import registry as _hermes_registry
            for name in _hermes_registry.names():
                if name in self._tools:
                    continue
                entry = _hermes_registry.get(name) or {}
                schema = entry.get("schema") or {}
                if not isinstance(schema, dict):
                    schema = {}
                description = schema.get("description", "")
                # Hermes schema dict is {"name", "description", "input_schema"}.
                # Our Tool.schema is just the input_schema (JSON Schema body)
                # — that's what gets shipped to Anthropic in `tools[].input_schema`.
                input_schema = schema.get("input_schema") or schema.get("parameters") or {}
                upstream_handler = entry.get("handler") or (lambda _a, **_k: "")
                # Adapt (args, **kw) → (args) so our dispatcher's call shape
                # matches. Extra kwargs (store=, etc.) default to None.
                catalogue.append(Tool(
                    name=name,
                    description=description,
                    schema=input_schema,
                    handler=(lambda args, _h=upstream_handler: _h(args or {})),
                ))

        for tool in catalogue:
            if tool.name in self._tools:
                continue
            self._tools[tool.name] = tool
            self.valid_tool_names.add(tool.name)
        # Refresh the Anthropic-shape mirror so the next API call sees
        # the new schemas.
        self.tools = [
            {"name": t.name, "description": t.description, "input_schema": t.schema}
            for t in self._tools.values()
        ] or None

    def _ensure_session_db(self):
        """Lazily build the SessionDB on first use.

        Like the context compressor (Unit 5), constructing SessionDB
        eagerly burns disk I/O on short-lived agents. We defer until the
        first call site (session_search tool handler, _persist_session
        write, etc.) actually needs it.
        """
        if self._session_db is not None:
            return self._session_db
        from engine.storage.session_db import SessionDB
        self._session_db = SessionDB()
        return self._session_db

    # ------------------------------------------------------------------
    # System prompt (Unit 4) — lazy composed from skills + memory + SOUL/USER
    # ------------------------------------------------------------------

    def _build_system_prompt(self, override: Optional[str] = None) -> str:
        """Compose the active system prompt.

        Resolution order:
          1. ``override`` argument (e.g. curator passes a fully-formed prompt)
          2. Caller-supplied `system_prompt=` from __init__ (auto-build OFF)
          3. Auto-built from prompt_builder: skill index + SOUL.md +
             memory provider blocks. Empty fragments collapse — the agent
             still works with no skills, no memory, and no SOUL.md.

        Cached on first build so the next turn reuses the same string
        (Anthropic prefix-cache friendly).
        """
        if override is not None:
            self._system_prompt = override
            return override
        if self._system_prompt and not self._auto_build_system_prompt:
            return self._system_prompt
        if self._system_prompt:
            # Already built once this session — reuse.
            return self._system_prompt

        # ── Auto-build path ──────────────────────────────────────────
        try:
            from engine.core.prompt_builder import (
                build_skills_system_prompt,
                build_context_files_prompt,
            )
        except Exception as exc:
            logger.warning("prompt_builder unavailable, using empty system prompt: %s", exc)
            self._system_prompt = ""
            return ""

        # Section order matters for smaller models (DeepSeek flash etc.).
        # "Lost in the middle" hits prompts where rules and the skills
        # index are buried between a long intro and the user turn. We
        # place identity + skill-routing TABLE (SOUL.md) first so the
        # model is primed with the operating rules; then the
        # <available_skills> index (which is where it learns *what is
        # available*); memory last because it's per-conversation drift.
        parts: List[str] = []

        # Workspace = the user's current target directory (poems folder,
        # codebase, etc.) — distinct from the agent's persistent home.
        # Setting UBION_WORKSPACE flips the context files the prompt
        # builder reads (SOUL.md / HERMES.md / AGENTS.md / CLAUDE.md /
        # .cursorrules under that directory).
        from engine.storage.agent_home import get_workspace, get_hermes_home
        try:
            workspace = get_workspace()
            ctx_text = build_context_files_prompt(cwd=str(workspace))
        except Exception as exc:
            logger.debug("build_context_files_prompt failed: %s", exc)
            ctx_text = ""
        # Hermes' build_context_files_prompt only walks the workspace.
        # Our SOUL.md lives in agent_home (~/.ubion-agent/SOUL.md) so
        # we read it explicitly and prepend.
        try:
            soul_path = get_hermes_home() / "SOUL.md"
            if soul_path.is_file():
                soul_body = soul_path.read_text(encoding="utf-8", errors="replace")
                if soul_body.strip():
                    parts.append(
                        f"# AGENT IDENTITY (~/.ubion-agent/SOUL.md)\n\n{soul_body}"
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("could not read SOUL.md: %s", exc)

        try:
            skills_text = build_skills_system_prompt(
                available_tools=self.valid_tool_names or None,
            )
        except Exception as exc:
            logger.debug("build_skills_system_prompt failed: %s", exc)
            skills_text = ""
        if skills_text and skills_text.strip():
            parts.append(skills_text)
        if ctx_text and ctx_text.strip():
            parts.append(ctx_text)

        # Memory provider system_prompt_block — invariant: empty manager OK
        if self._memory_manager is not None:
            try:
                mem_text = self._memory_manager.build_system_prompt()
            except Exception as exc:
                logger.debug("memory build_system_prompt failed: %s", exc)
                mem_text = ""
            if mem_text and mem_text.strip():
                parts.append(mem_text)

        composed = "\n\n".join(parts)
        self._system_prompt = composed
        return composed

    def _invalidate_system_prompt(self) -> None:
        """Drop the cached prompt so the next turn rebuilds (called after
        ContextCompressor rotates the session)."""
        if self._auto_build_system_prompt:
            self._system_prompt = ""

    # ------------------------------------------------------------------
    # Memory manager (Unit 6) — optional. Every consumer must guard.
    # ------------------------------------------------------------------

    def _attach_memory_manager(self, manager) -> None:
        """Wire up a MemoryManager (typically caller-built with providers).

        Caller is responsible for adding providers (built-in + at most one
        external) via manager.add_provider(...). After attachment, the
        agent's prompt builder, tool dispatch, and compression hooks read
        from it through guarded `if self._memory_manager:` paths.

        Side effect: the memory manager's provider tool names are folded
        into self.valid_tool_names so the (Unit 4) prompt builder picks
        them up.
        """
        self._memory_manager = manager
        if manager is None:
            return
        for provider in getattr(manager, "providers", []) or []:
            try:
                for schema in provider.get_tool_schemas() or []:
                    tname = schema.get("name")
                    if tname:
                        self.valid_tool_names.add(tname)
            except Exception as exc:
                logger.debug("memory provider tool schema read failed: %s", exc)

    def _memory_prefetch_safe(self, query: str) -> str:
        """Run prefetch_all defensively — empty manager / no-providers /
        provider exceptions all collapse to an empty string.

        Phase 1 invariant ("memory absent → no error"): every caller can
        treat the return value as a plain string with no None handling.
        """
        mgr = self._memory_manager
        if mgr is None:
            return ""
        try:
            return mgr.prefetch_all(query, session_id=self.session_id or "") or ""
        except Exception as exc:
            logger.debug("memory prefetch failed: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Context compression (Unit 5 — manual entry point only; automatic
    # preflight + post-LLM should_compress wiring lands in Unit 4)
    # ------------------------------------------------------------------

    def _ensure_compressor(self):
        """Lazily build the ContextCompressor on first use.

        Constructing it eagerly in __init__ would import a 1,300-line
        module + look up model context length for every short-lived
        AIAgent (e.g. curator review). We pay that cost only when
        compression actually needs to fire.
        """
        if self.context_compressor is not None:
            return self.context_compressor
        from engine.learning.context_compressor import ContextCompressor
        self.context_compressor = ContextCompressor(
            model=self.model,
            base_url=self.base_url or "",
            api_key=self.api_key or "",
            provider=self.provider or "",
            api_mode=self.api_mode or "",
            quiet_mode=self.quiet_mode,
        )
        return self.context_compressor

    def _compress_context(
        self,
        messages: List[Dict[str, Any]],
        system_message: Optional[str] = None,
        *,
        approx_tokens: Optional[int] = None,
        task_id: str = "default",  # noqa: ARG002 — Hermes signature compat
        focus_topic: Optional[str] = None,
    ) -> tuple:
        """Run one compression pass and return (compressed, system_prompt).

        Phase 1 Unit 5 scope: minimum surface. Hermes' run_agent.py:10237
        version handles session DB rotation (task_id flows to file dedup
        reset there), memory provider hooks, todo snapshot injection, and
        prompt rebuild — all deferred to Units 6/4/9. We accept task_id
        in the signature so callers (and the future Unit 4 preflight)
        don't need to be modified when those hooks land.
        """
        compressor = self._ensure_compressor()
        pre_count = len(messages)
        logger.info(
            "context compression started: messages=%d tokens=~%s model=%s focus=%r",
            pre_count,
            f"{approx_tokens:,}" if approx_tokens else "unknown",
            self.model, focus_topic,
        )

        # Notify the memory manager *before* the compressor discards
        # turns — providers may want to extract durable facts from the
        # middle slice that's about to be summarized away.
        if self._memory_manager is not None:
            try:
                self._memory_manager.on_pre_compress(messages)
            except Exception as exc:
                logger.debug("memory on_pre_compress failed: %s", exc)

        try:
            compressed = compressor.compress(
                messages,
                current_tokens=approx_tokens,
                focus_topic=focus_topic,
            )
        except TypeError:
            # Older context_engine signatures may reject focus_topic.
            compressed = compressor.compress(messages, current_tokens=approx_tokens)

        summary_error = getattr(compressor, "_last_summary_error", None)
        if summary_error:
            self._compression_warning = (
                f"Compression summary failed: {summary_error}. "
                "Inserted a fallback context marker."
            )
            logger.warning(self._compression_warning)

        # Phase 1 single-prompt mode — we don't rebuild the system prompt
        # here. Unit 4 (prompt builder) will repopulate it from skills +
        # memory + SOUL/USER on the next turn. Return the cached system
        # prompt unchanged so callers can pass it through.
        new_system_prompt = system_message or self._system_prompt

        logger.info(
            "context compression done: messages=%d->%d", pre_count, len(compressed),
        )
        return compressed, new_system_prompt

    # ------------------------------------------------------------------
    # Loop internals
    # ------------------------------------------------------------------

    def _run_loop(self, ctx: TurnContext, result: ConversationResult) -> None:
        messages: List[Dict[str, Any]] = ctx.messages

        # Per-loop guard counter (separate from the shared IterationBudget so
        # nested loops can each enforce their own ceiling).
        api_call_count = 0

        while True:
            # ── Interrupt check #1 — before any work ─────────────────────
            if self._interrupt_requested:
                result.exit_reason = "interrupted_by_user"
                return

            # ── Iteration ceiling: surface max_iterations *before* we even
            #    consume budget, so the exit reason matches what blocked us.
            if api_call_count >= self.max_iterations:
                result.exit_reason = "max_iterations"
                return
            if self.iteration_budget.remaining <= 0:
                result.exit_reason = "budget_exhausted"
                return

            # consume() can race with another agent sharing the budget — if
            # someone else burned the last slot since the remaining check,
            # treat it as a budget exhaustion.
            if not self.iteration_budget.consume():
                result.exit_reason = "budget_exhausted"
                return

            api_call_count += 1
            result.api_calls = api_call_count

            self._emit_progress("llm_call_started", {"turn": api_call_count})

            # Forward incremental text + reasoning chunks to the
            # progress callback so the SSE endpoint can push real
            # token-by-token deltas to the UI. Without this, a 30 s
            # DeepSeek thinking burst looks like a frozen spinner;
            # with it, the user sees the reasoning unfold and knows
            # the agent is alive. text_delta goes to the assistant
            # bubble; reasoning_delta rides a separate "thinking"
            # channel so the UI can render it differently (dimmed
            # preview vs. final answer).
            def _on_text_delta(chunk: str, _i=api_call_count) -> None:
                if chunk:
                    self._emit_progress("text_delta", {"text": chunk, "turn": _i})

            def _on_reasoning_delta(chunk: str, _i=api_call_count) -> None:
                if chunk:
                    self._emit_progress(
                        "reasoning_delta", {"text": chunk, "turn": _i}
                    )

            response = self._call_llm_with_retry(
                messages,
                on_text_delta=_on_text_delta,
                on_reasoning_delta=_on_reasoning_delta,
            )
            if response is None:
                # _call_llm_with_retry already filled result.error / logged.
                # Distinguish interrupt-during-retry from retry exhaustion.
                if self._interrupt_requested:
                    result.exit_reason = "interrupted_by_user"
                else:
                    result.exit_reason = "all_retries_exhausted"
                return

            # Record the assistant turn in the shape curator walks.
            self._session_messages.append(
                _assistant_turn_record(response)
            )

            # One-line per-turn summary — vital for diagnosis when the
            # UI shows "thinking (turn 18)" forever: this log tells
            # whether the model actually returned anything, what
            # tool_calls (if any) it produced, and how big the
            # reasoning burst was. Without this the turn boundary is
            # invisible in server.log.
            depth = getattr(self, "_delegate_depth", 0)
            depth_tag = f"[d={depth}] " if depth else ""
            tool_names = (
                ", ".join(tc.name for tc in response.tool_calls)
                if response.tool_calls
                else "—"
            )
            logger.info(
                "%sturn %d done: text=%d reasoning=%d tools=[%s] stop=%s",
                depth_tag,
                api_call_count,
                len(response.text or ""),
                len(getattr(response, "reasoning_content", "") or ""),
                tool_names,
                response.stop_reason or "?",
            )

            if not response.tool_calls:
                # No tool calls → the model is done.
                result.final_response = response.text
                result.exit_reason = "completed"
                self._emit_progress("final_text", {"text": response.text})
                return

            # ── Truncation guard: when stop_reason == "length" the model
            # hit max_tokens mid-output. If it was mid-tool_call, the
            # arguments JSON is incomplete — the LiteLLM client falls
            # back to args={} and we end up dispatching the tool with
            # empty inputs (write_file(path=''), create_workspace_file()
            # — both REFUSED, then the model retries and truncates
            # again, indefinitely). Drop the tool_calls, append a guidance
            # message, and let the next turn re-plan with smaller payloads.
            if response.stop_reason == "length" and response.tool_calls:
                depth = getattr(self, "_delegate_depth", 0)
                depth_tag = f"[d={depth}] " if depth else ""
                logger.warning(
                    "%sturn %d: response truncated (stop=length) with %d tool_call(s) — "
                    "dropping incomplete calls and asking model to retry with smaller payloads",
                    depth_tag, api_call_count, len(response.tool_calls),
                )
                # Record what the model attempted as plain text so the
                # transcript stays readable, then add a user-role nudge.
                truncated_names = ", ".join(tc.name for tc in response.tool_calls) or "?"
                messages.append({
                    "role": "assistant",
                    "content": (response.text or "")
                    + f"\n\n[truncated: attempted {truncated_names} but ran out of tokens]",
                })
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous response was cut off because it exceeded the output "
                        "token limit. The tool call arguments did not arrive in full and "
                        "have been discarded. Retry with a smaller payload — for write_file "
                        "/ create_workspace_file with large content, split into multiple "
                        "smaller calls using append_file for subsequent chunks, or generate "
                        "the file with a script via the shell tool instead of inlining its "
                        "body. Plan your next step before producing it."
                    ),
                })
                continue

            # ── Interrupt check #2 — between LLM and tool dispatch ───────
            # The model already produced tool_calls; we *could* drop them,
            # but appending the assistant turn first keeps the transcript
            # consistent with what the API returned.
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": _to_anthropic_content(response),
            }
            # DeepSeek thinking mode requires reasoning_content to be echoed
            # back on subsequent turns whenever tool_calls are present, or
            # the API returns 400. Carry it as a sidecar key; Anthropic
            # ignores unknown top-level keys, our DeepSeek client reads it.
            if getattr(response, "reasoning_content", ""):
                assistant_msg["reasoning_content"] = response.reasoning_content
            messages.append(assistant_msg)
            if self._interrupt_requested:
                result.exit_reason = "interrupted_by_user"
                return

            for tc in response.tool_calls:
                self._emit_progress("tool_call_started", {"name": tc.name})
            tool_results = execute_tool_calls_sequential(self, response.tool_calls)
            for tc, tr in zip(response.tool_calls, tool_results):
                # tool_results items are Anthropic-shape dicts; presence of
                # `is_error` flags a failed call.
                ok = not (isinstance(tr, dict) and tr.get("is_error"))
                self._emit_progress("tool_call_finished", {"name": tc.name, "ok": ok})
            result.tool_calls_made += len(tool_results)
            messages.append({"role": "user", "content": tool_results})

            # ── Interrupt check #3 — after tool results, before next API
            # call. Same effect as #1 on the next iteration, but bails
            # one consumable API call earlier when the user interrupts
            # during tool execution.
            if self._interrupt_requested:
                result.exit_reason = "interrupted_by_user"
                return

    def _call_llm_with_retry(
        self,
        messages: List[Dict[str, Any]],
        *,
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_reasoning_delta: Optional[Callable[[str], None]] = None,
    ) -> Optional[ChatResponse]:
        """Send one turn with retry. Returns None when all retries are spent.

        When ``on_text_delta`` is provided AND the underlying client
        exposes ``chat_stream`` (currently LiteLLM only), we take the
        streaming path so the agent can emit ``text_delta`` progress
        events for the SSE endpoint. ``on_reasoning_delta`` rides the
        same stream — DeepSeek thinking mode emits chain-of-thought
        in ``reasoning_content`` chunks; surfacing those to the SSE
        client kills the "frozen for 30 s" UX during reasoning bursts.

        Falls back to the non-streaming ``chat`` method when streaming
        isn't available — the returned ChatResponse shape is identical.
        """
        tool_schemas: Optional[List[Dict[str, Any]]] = None
        if self._tools:
            tool_schemas = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.schema,
                }
                for t in self._tools.values()
            ]

        # Ensure the system prompt has been composed (Unit 4 lazy build).
        # Caller-supplied prompts pass through untouched.
        active_system_prompt = self._build_system_prompt()

        # Choose the call surface once per turn — switching between
        # streaming and non-streaming mid-retry would just double the
        # complexity without any user-visible benefit.
        use_stream = (
            on_text_delta is not None
            and hasattr(self._llm, "chat_stream")
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries_per_call + 1):
            if self._interrupt_requested:
                return None
            try:
                if use_stream:
                    return self._llm.chat_stream(
                        messages=messages,
                        system=active_system_prompt or None,
                        tools=tool_schemas,
                        on_text_delta=on_text_delta,
                        on_reasoning_delta=on_reasoning_delta,
                    )
                return self._llm.chat(
                    messages=messages,
                    system=active_system_prompt or None,
                    tools=tool_schemas,
                )
            except Exception as exc:
                last_error = exc
                classification = classify_api_error(exc)
                # Unrecoverable errors: auth, billing, permanent rate-limit
                # ban. Stop retrying immediately.
                if classification.reason in {
                    FailoverReason.auth,
                    FailoverReason.auth_permanent,
                    FailoverReason.billing,
                }:
                    logger.error(
                        "Unrecoverable LLM error (%s): %s",
                        classification.reason.value, exc,
                    )
                    if not self.quiet_mode:
                        logger.error("Aborting retry chain.")
                    break
                # Otherwise backoff and try again.
                delay = jittered_backoff(attempt)
                if not self.quiet_mode:
                    logger.warning(
                        "LLM call failed (attempt %d/%d, reason=%s): %s — "
                        "sleeping %.1fs",
                        attempt, self.max_retries_per_call,
                        classification.reason.value, exc, delay,
                    )
                time.sleep(delay)

        if last_error is not None:
            logger.error("All %d retries exhausted: %s",
                         self.max_retries_per_call, last_error)
        return None

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _assistant_turn_record(response: ChatResponse) -> Dict[str, Any]:
    """Shape an assistant turn the way curator.py:1751 expects to read it.

    Curator iterates msg.get("tool_calls") looking for {"function": {"name",
    "arguments"}} entries. Hermes' main loop populates that shape directly;
    we synthesize the same shape from our normalized response.
    """
    return {
        "role": "assistant",
        "content": response.text,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": tc.arguments,
                },
            }
            for tc in response.tool_calls
        ],
    }


def _to_anthropic_content(response: ChatResponse) -> List[Dict[str, Any]]:
    """Reconstruct content list for the assistant message we feed back in."""
    blocks: List[Dict[str, Any]] = []
    if response.text:
        blocks.append({"type": "text", "text": response.text})
    for tc in response.tool_calls:
        blocks.append(
            {
                "type": "tool_use",
                "id": tc.id,
                "name": tc.name,
                "input": tc.arguments,
            }
        )
    return blocks


