# Copyright (c) 2026 Ubion ax center
"""Minimal AIAgent shim that satisfies the surface curator.py uses.

This is **NOT** a faithful re-implementation of Hermes' run_agent.AIAgent —
it's the smallest possible thing that lets the vendored curator.py run
end-to-end against a real LLM, so we can verify the *portability* of the
curator orchestration logic.

Surface that curator.py:1640-1773 calls (verified against vendored copy):

    AIAgent(
        model: str,
        provider: str,
        api_key: str | None,
        base_url: str | None,
        api_mode: str | None,
        max_iterations: int,
        quiet_mode: bool,
        platform: str,
        skip_context_files: bool,
        skip_memory: bool,
    )
    agent._memory_nudge_interval = 0        # attribute write
    agent._skill_nudge_interval = 0         # attribute write
    agent.run_conversation(user_message: str) -> dict   # returns {"final_response": str, ...}
    agent._session_messages: list[dict]                # read for tool-call extraction
    agent.close()

Behavior:
- Real Anthropic API call via the anthropic SDK.
- No tool execution. The curator review prompt is verbose enough that the
  model returns a text summary of what it WOULD do; the curator records
  this as `final_response`. We're not testing tool wiring at this stage —
  we're testing that the curator orchestration code paths survive the port.
- API key read from ANTHROPIC_API_KEY env var (per Phase 0 decision).

Out of scope (intentionally):
- Tool calling (skill_manage, etc.) — curator's own consolidation actions
  won't actually mutate fixtures. The `_session_messages` list stays empty,
  which curator handles gracefully (empty tool_calls in report).
- Streaming, prompt caching, retries.
- Honcho / memory / context files (curator passes skip_memory=True anyway).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


DEFAULT_MODEL = "claude-opus-4-7"  # Opus 4.7. Dateless model IDs since 4.6 are pinned snapshots.
DEFAULT_MAX_TOKENS = 4096


class AIAgent:
    """See module docstring."""

    def __init__(
        self,
        *,
        model: str = "",
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        api_mode: Optional[str] = None,
        max_iterations: int = 1,
        quiet_mode: bool = True,
        platform: str = "curator",
        skip_context_files: bool = True,
        skip_memory: bool = True,
        **_ignored: Any,
    ) -> None:
        # curator.py reads .model / .provider off the agent for reporting,
        # but never mutates them — store and move on.
        #
        # Resolution order for the model name:
        #   1. Explicit `model` kwarg (curator passes one if config has it)
        #   2. ANTHROPIC_MODEL env var (sandbox convenience override)
        #   3. DEFAULT_MODEL constant
        self.model = (
            model
            or os.environ.get("ANTHROPIC_MODEL", "").strip()
            or DEFAULT_MODEL
        )
        self.provider = provider or "anthropic"
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url
        self.api_mode = api_mode
        self.platform = platform
        # curator.py writes these two; we accept the writes and ignore them.
        self._memory_nudge_interval = 0
        self._skill_nudge_interval = 0
        # curator.py reads this list to extract tool calls for its report.
        # Empty list = "no tool calls made", which is the truthful state
        # for a mock that doesn't execute tools.
        self._session_messages: List[Dict[str, Any]] = []

        if not self.api_key:
            raise RuntimeError(
                "mock_agent.AIAgent: ANTHROPIC_API_KEY is not set in environment. "
                "Either export it or pass api_key= explicitly."
            )

        # Lazy import — keeps the module importable for tests that monkeypatch
        # the API call before construction.
        try:
            import anthropic  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "mock_agent.AIAgent: the `anthropic` package is required. "
                "Install with: pip install anthropic"
            ) from exc

        self._client = anthropic.Anthropic(api_key=self.api_key)

    def run_conversation(self, *, user_message: str) -> Dict[str, Any]:
        """Send `user_message` to Claude once, return curator-shaped result.

        Curator only reads `final_response` from the dict, so we keep the
        rest minimal.
        """
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=DEFAULT_MAX_TOKENS,
            messages=[{"role": "user", "content": user_message}],
        )

        # anthropic SDK returns content as a list of TextBlock | ToolUseBlock.
        # The mock doesn't expose tools, so we expect text-only.
        parts: List[str] = []
        for block in resp.content or []:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        final = "\n".join(parts).strip()

        # Record the assistant turn in the same shape curator.py walks at
        # line 1751: msg.get("tool_calls") — we keep it empty since the
        # mock didn't actually call any tool.
        self._session_messages.append({
            "role": "assistant",
            "content": final,
            "tool_calls": [],
        })

        return {
            "final_response": final,
            # Curator doesn't inspect these but we record them for run_demo's
            # observability layer.
            "model": self.model,
            "provider": self.provider,
        }

    def close(self) -> None:
        """No persistent resources to release — anthropic.Anthropic uses
        connection pooling that GCs itself."""
        return None
