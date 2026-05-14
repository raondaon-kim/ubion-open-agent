# Inspired by NousResearch/hermes-agent agent/anthropic_adapter.py (MIT License)
# — original idea only, implementation is independent.
#
# Copyright (c) 2026 Ubion ax center
"""Thin Anthropic adapter for the Phase 1 engine.

Surface:
    AnthropicClient(api_key, model).chat(
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> ChatResponse

Where ``ChatResponse`` carries:
    .text          str            — concatenated text blocks of the final turn
    .tool_calls    list[ToolCall] — any tool_use blocks the model emitted
    .stop_reason   str            — anthropic's "end_turn" | "tool_use" | "max_tokens" | ...
    .usage         dict           — input_tokens, output_tokens (raw from SDK)
    .raw           Any            — original SDK Message for callers that need more

Scope (Phase 1 Unit 2):
    - Anthropic Messages API only. No streaming yet (added in Unit 5 with
      trajectory port).
    - No prompt caching (deferred until Unit 4 prompt builder Port).
    - No OAuth, no Bedrock, no provider fallback (deferred to a later unit
      that vendors the full Hermes adapter if needed).
    - No retries here — retries belong to the agent loop (engine.core.agent),
      which already coordinates IterationBudget and error classification.

Why a hand-written thin adapter instead of vendoring Hermes' 2079-line
agent/anthropic_adapter.py:
    The Hermes adapter is a production-hardened module covering OAuth,
    Bedrock, multiple cache strategies, base64 image handling, and provider
    introspection. Our Unit 2 goal is a minimum working AIAgent core, and a
    full adapter port would balloon the scope. We can vendor the full
    adapter in a later unit if we hit a feature wall.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# anthropic SDK is imported lazily inside AnthropicClient.__init__ — the
# top-level import accounts for ~1 second of cold-start time (pydantic +
# anthropic._compat + rich), and most consumers of this module only need
# the ChatResponse / ToolCall dataclasses for type hints. Phase 1 (B)
# acceptance gate (§2.8) requires fast cold start.
def _import_anthropic_sdk():
    """Lazy import. Caches on first call via Python's module system."""
    try:
        import anthropic  # noqa: PLC0415 — intentional lazy import
        return anthropic
    except ImportError as exc:  # pragma: no cover — required dep
        raise RuntimeError(
            "engine.llm.anthropic: the `anthropic` package is required. "
            "Install: pip install anthropic"
        ) from exc


DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 4096


@dataclass
class ToolCall:
    """One tool_use block emitted by the model."""

    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ChatResponse:
    """Normalized response from the Anthropic Messages API."""

    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    stop_reason: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    raw: Any = None
    # DeepSeek thinking mode emits a separate `reasoning_content` stream
    # that MUST be echoed back in the next request when tool_calls are
    # present, or the API returns 400. Anthropic ignores this field.
    reasoning_content: str = ""


class AnthropicClient:
    """Thin synchronous client around anthropic.Anthropic.

    One instance is bound to a single (api_key, model) pair. Reusing the
    instance benefits from the SDK's connection pool. The instance is
    thread-safe for read access to its config; the underlying SDK client
    handles concurrent calls.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "",
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "AnthropicClient: ANTHROPIC_API_KEY is not set and api_key= was "
                "not provided."
            )
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "") or DEFAULT_MODEL
        self.base_url = base_url

        kwargs: Dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        anthropic = _import_anthropic_sdk()
        self._sdk = anthropic.Anthropic(**kwargs)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> ChatResponse:
        """Send one turn and return the normalized response.

        ``messages`` is a list of role/content dicts in Anthropic's native
        format — including `tool_result` content blocks for any prior tool
        calls. The caller (the agent loop) is responsible for stitching the
        conversation, not us.
        """
        # Strip provider-specific sidecar keys (e.g. DeepSeek's
        # `reasoning_content`) that the agent loop attaches to history
        # entries. Anthropic's API only accepts {role, content}.
        sanitized = [
            {k: v for k, v in m.items() if k in ("role", "content")}
            for m in messages
        ]
        request: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": sanitized,
        }
        if system:
            request["system"] = system
        if tools:
            request["tools"] = tools

        msg = self._sdk.messages.create(**request)
        return _normalize_message(msg)


def _normalize_message(msg: Any) -> ChatResponse:
    """Flatten an anthropic.types.Message into our ChatResponse shape."""
    text_parts: List[str] = []
    tool_calls: List[ToolCall] = []
    for block in msg.content or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(getattr(block, "text", "") or "")
        elif btype == "tool_use":
            tool_calls.append(
                ToolCall(
                    id=getattr(block, "id", "") or "",
                    name=getattr(block, "name", "") or "",
                    arguments=dict(getattr(block, "input", {}) or {}),
                )
            )

    usage = {}
    if getattr(msg, "usage", None) is not None:
        usage = {
            "input_tokens": getattr(msg.usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(msg.usage, "output_tokens", 0) or 0,
        }

    return ChatResponse(
        text="\n".join(text_parts).strip(),
        tool_calls=tool_calls,
        stop_reason=getattr(msg, "stop_reason", "") or "",
        usage=usage,
        raw=msg,
    )
