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

import logging
import os
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover — required dep
    raise RuntimeError(
        "engine.llm.litellm_client: the `openai` package is required. "
        "Install: pip install openai"
    ) from exc

from engine.llm.anthropic import ChatResponse
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
