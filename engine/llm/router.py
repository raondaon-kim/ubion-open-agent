# Copyright (c) 2026 Ubion ax center
"""Provider router for the Phase 1 engine.

Resolves a model name (or explicit provider tag) to the correct LLM
client. Returns an object with the same `chat()` surface no matter
which provider is behind it.

Resolution:
    0. ``LITELLM_BASE_URL`` env var present → use LiteLLMClient for
       every model. This is the company-internal path: one OpenAI-
       compatible proxy fronts both Claude and DeepSeek (and anything
       else), so a single (key, URL) pair replaces per-provider keys.
    1. Otherwise explicit `provider` argument wins
       ("anthropic" | "deepseek" | "litellm").
    2. Otherwise model-name prefix:
       - "claude-*"   → anthropic
       - "deepseek-*" → deepseek
    3. Fallback default: anthropic.

The router stays simple — no fallback chain, no cached clients, no
health probing. Phase 2 can layer those on top when multi-provider
deployments require them.
"""

from __future__ import annotations

import os
from typing import Any, Optional


PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_LITELLM = "litellm"

VALID_PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_DEEPSEEK, PROVIDER_LITELLM)


def _litellm_mode_active() -> bool:
    """LiteLLM mode kicks in when both env vars are non-empty.

    We require BOTH key and URL — having only one is almost always a
    misconfigured environment, and silently falling back to direct
    providers would defeat the audit-trail reason the proxy exists.
    """
    return bool(
        os.environ.get("LITELLM_BASE_URL", "").strip()
        and os.environ.get("LITELLM_API_KEY", "").strip()
    )


def resolve_provider(model: str, *, explicit: Optional[str] = None) -> str:
    """Return the canonical provider string for a model + explicit override.

    LiteLLM mode (env vars set) overrides everything: the whole point
    is to route all traffic through the proxy. Callers can still pass
    ``provider="litellm"`` explicitly when they want to be loud about
    it.
    """
    if _litellm_mode_active():
        return PROVIDER_LITELLM

    if explicit:
        lower = explicit.strip().lower()
        if lower not in VALID_PROVIDERS:
            raise ValueError(
                f"Unknown provider {explicit!r}. Valid: {VALID_PROVIDERS}"
            )
        return lower

    if not model:
        return PROVIDER_ANTHROPIC

    name = model.strip().lower()
    if name.startswith("deepseek"):
        return PROVIDER_DEEPSEEK
    if name.startswith("claude") or name.startswith("anthropic"):
        return PROVIDER_ANTHROPIC
    # Default fallback. Phase 1 / poet scenario assumes Anthropic by default.
    return PROVIDER_ANTHROPIC


def build_client(
    *,
    model: str = "",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: Optional[str] = None,
) -> Any:
    """Instantiate the right LLM client.

    Returns AnthropicClient, DeepSeekClient, or LiteLLMClient — all
    share the same ``chat(messages, system, tools, max_tokens) ->
    ChatResponse`` surface so the agent loop treats them as
    interchangeable.
    """
    resolved = resolve_provider(model, explicit=provider)
    if resolved == PROVIDER_LITELLM:
        from engine.llm.litellm_client import LiteLLMClient
        return LiteLLMClient(api_key=api_key, model=model, base_url=base_url)
    if resolved == PROVIDER_DEEPSEEK:
        from engine.llm.deepseek import DeepSeekClient
        return DeepSeekClient(api_key=api_key, model=model, base_url=base_url)
    # Default + explicit "anthropic"
    from engine.llm.anthropic import AnthropicClient
    return AnthropicClient(api_key=api_key, model=model, base_url=base_url)
