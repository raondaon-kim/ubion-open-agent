# Copyright (c) 2026 Ubion ax center
"""LiteLLM proxy client — single OpenAI-compatible endpoint for all models.

When the user runs a sanctioned LiteLLM proxy (an internal HTTP
endpoint configured via the LITELLM_BASE_URL env var), we route every
model — Claude, DeepSeek, anything else the proxy fronts — through it.
The proxy
normalizes the upstream APIs into OpenAI's chat-completions shape, so
we only need ONE adapter regardless of which logical model the agent
picked.

Why this exists instead of just reusing DeepSeekClient:
    DeepSeekClient hardcodes `https://api.deepseek.com` as the default
    base_url and reads `DEEPSEEK_API_KEY` only. A LiteLLM proxy uses a
    completely different (key, URL) pair and accepts model names that
    don't match DeepSeek's naming convention. Splitting the client
    keeps the "direct provider" path (real DEEPSEEK_API_KEY going to
    api.deepseek.com) intact while letting the proxy mode be a clean
    branch in router.build_client().

Resolution order for (key, URL):
    1. Explicit args (caller passes them)
    2. LITELLM_API_KEY + LITELLM_BASE_URL environment variables
    3. Hard error — we never silently fall back to a direct provider
       once LiteLLM mode is selected, because that would leak through
       the company's audit trail.

Shape parity with AnthropicClient / DeepSeekClient is preserved so the
agent loop stays provider-blind. We reuse DeepSeek's message + tool
translation helpers — they target the OpenAI shape, and a LiteLLM
proxy IS the OpenAI shape.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover — required dep
    raise RuntimeError(
        "engine.llm.litellm_client: the `openai` package is required. "
        "Install: pip install openai"
    ) from exc

from engine.llm.anthropic import ChatResponse, ToolCall
from engine.llm.deepseek import (
    _normalize_completion,
    _to_openai_messages,
    _tool_to_openai,
)

logger = logging.getLogger(__name__)


DEFAULT_MAX_TOKENS = 4096


class LiteLLMClient:
    """Synchronous client for a LiteLLM OpenAI-compatible proxy.

    One instance is bound to a single (api_key, base_url, model) tuple.
    `model` here is whatever logical name the proxy maps — typically
    the same Claude / DeepSeek string the user types in the UI, since
    LiteLLM's config usually keeps model_name == upstream name.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "",
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("LITELLM_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "LiteLLMClient: LITELLM_API_KEY is not set and api_key= "
                "was not provided."
            )
        self.base_url = base_url or os.environ.get("LITELLM_BASE_URL", "")
        if not self.base_url:
            raise RuntimeError(
                "LiteLLMClient: LITELLM_BASE_URL is not set and base_url= "
                "was not provided."
            )
        self.model = model or os.environ.get("LITELLM_MODEL", "") or "claude-sonnet-4-6"
        self._sdk = OpenAI(api_key=self.api_key, base_url=self.base_url)
        logger.info(
            "LiteLLMClient init: base_url=%s model=%s", self.base_url, self.model
        )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> ChatResponse:
        """Send one turn through the LiteLLM proxy. Reply is ChatResponse-shaped.

        Reuses DeepSeek's translation helpers since the wire format is
        OpenAI on both sides. Anthropic-shaped tool_use / tool_result
        blocks in `messages` get re-shaped into OpenAI tool_calls /
        role=tool messages before sending, and the OpenAI reply is
        normalized back into Anthropic-shape ToolCall objects.
        """
        openai_messages = _to_openai_messages(messages, system=system)
        request: Dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
        }
        if tools:
            request["tools"] = [_tool_to_openai(t) for t in tools]

        completion = self._sdk.chat.completions.create(**request)
        return _normalize_completion(completion)

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_reasoning_delta: Optional[Callable[[str], None]] = None,
    ) -> ChatResponse:
        """Streaming sibling of :meth:`chat`.

        Forwards each text chunk to ``on_text_delta`` as it arrives, then
        returns the aggregated ChatResponse once the stream ends. The
        return shape is identical to ``chat()`` — same ``text``,
        ``tool_calls``, ``stop_reason``, ``usage``, ``reasoning_content``
        — so callers can plug streaming into the agent loop without
        changing downstream code.

        Streaming semantics:
          * ``on_text_delta`` fires for every non-empty
            ``delta.content`` chunk. The caller is responsible for any
            UI thread hopping / queue.put_nowait dance.
          * ``reasoning_content`` deltas (DeepSeek thinking mode) are
            forwarded to ``on_reasoning_delta`` when provided and
            always accumulated for the final ChatResponse. The agent
            loop echoes the accumulated reasoning back on the next
            turn; the delta callback exists so the SSE endpoint can
            stream thinking in real time — without it the UI shows
            a silent 30-second "thinking" spinner.
          * ``tool_calls`` arrive as partial chunks (id + name early,
            arguments string built up across many chunks). We assemble
            them here so the returned ChatResponse looks identical to
            a non-streaming call. While tool_calls are streaming we do
            NOT forward text — providers occasionally interleave a
            short text preamble that callers can still see in
            ``response.text``.
        """
        openai_messages = _to_openai_messages(messages, system=system)
        request: Dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            request["tools"] = [_tool_to_openai(t) for t in tools]

        text_parts: List[str] = []
        reasoning_parts: List[str] = []
        # Tool calls arrive in fragments — `index` ties them together.
        # Each entry: {"id", "name", "args_chunks": [str, ...]}.
        tool_buffers: Dict[int, Dict[str, Any]] = {}
        stop_reason: str = ""
        usage: Dict[str, int] = {}

        stream = self._sdk.chat.completions.create(**request)
        for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue
            delta = getattr(choice, "delta", None)
            if delta is None:
                # `[DONE]` sentinel, or trailing usage-only chunk.
                fr = getattr(choice, "finish_reason", None)
                if fr:
                    stop_reason = fr
                continue

            # Text delta — forward immediately.
            content = getattr(delta, "content", None)
            if content:
                text_parts.append(content)
                if on_text_delta is not None:
                    try:
                        on_text_delta(content)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("on_text_delta raised: %s", exc)

            # Reasoning delta — accumulate AND forward so the UI can show
            # the thinking stream in real time. Echoed back to the LLM
            # on the next turn via the final ChatResponse.
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                reasoning_parts.append(str(reasoning))
                if on_reasoning_delta is not None:
                    try:
                        on_reasoning_delta(str(reasoning))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("on_reasoning_delta raised: %s", exc)

            # Tool call fragments — assemble by index.
            raw_calls = getattr(delta, "tool_calls", None) or []
            for raw in raw_calls:
                idx = getattr(raw, "index", 0) or 0
                buf = tool_buffers.setdefault(
                    idx,
                    {"id": "", "name": "", "args_chunks": []},
                )
                rid = getattr(raw, "id", None)
                if rid:
                    buf["id"] = rid
                fn = getattr(raw, "function", None)
                if fn is not None:
                    rname = getattr(fn, "name", None)
                    if rname:
                        buf["name"] = rname
                    rargs = getattr(fn, "arguments", None)
                    if rargs:
                        buf["args_chunks"].append(rargs)

            # finish_reason on a partial chunk (some providers send it
            # alongside the last delta instead of in a separate frame).
            fr = getattr(choice, "finish_reason", None)
            if fr:
                stop_reason = fr

        # Usage often lands on the *last* chunk's `usage` field when the
        # provider opts into stream_options.include_usage. Our request
        # doesn't enable it explicitly, so this is best-effort.
        if hasattr(chunk, "usage") and chunk.usage is not None:
            try:
                usage = {
                    "input_tokens": getattr(chunk.usage, "prompt_tokens", 0) or 0,
                    "output_tokens": getattr(chunk.usage, "completion_tokens", 0) or 0,
                }
            except Exception:  # noqa: BLE001
                usage = {}

        # Reshape the assembled buffers into our ToolCall dataclass.
        tool_calls: List[ToolCall] = []
        for idx in sorted(tool_buffers.keys()):
            buf = tool_buffers[idx]
            args_raw = "".join(buf["args_chunks"]) or "{}"
            try:
                args_obj = json.loads(args_raw) if args_raw.strip() else {}
            except json.JSONDecodeError:
                args_obj = {}
            tool_calls.append(
                ToolCall(
                    id=buf["id"] or f"call_{uuid.uuid4().hex[:24]}",
                    name=buf["name"],
                    arguments=args_obj if isinstance(args_obj, dict) else {},
                )
            )

        return ChatResponse(
            text="".join(text_parts).strip(),
            tool_calls=tool_calls,
            stop_reason=stop_reason or "stop",
            usage=usage,
            raw=None,
            reasoning_content="".join(reasoning_parts),
        )
