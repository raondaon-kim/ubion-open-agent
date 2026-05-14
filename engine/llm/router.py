# Copyright (c) 2026 Ubion ax center
"""Provider router for the Phase 1 engine.

Resolves a model name (or explicit provider tag) to the correct LLM
client. Returns an object with the same `chat()` surface no matter
which provider is behind it (AnthropicClient or DeepSeekClient).

Resolution:
    1. Explicit `provider` argument wins ("anthropic" | "deepseek").
    2. Otherwise model-name prefix:
       - "claude-*"   → anthropic
       - "deepseek-*" → deepseek
    3. Fallback default: anthropic.

The router is intentionally simple — no fallback chain, no cached
clients, no health probing. Phase 2 / later can layer those on top
when multi-provider deployments require them. Phase 1 = single-user
local dev.
"""

from __future__ import annotations

from typing import Any, Optional


PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_DEEPSEEK = "deepseek"

VALID_PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_DEEPSEEK)


def resolve_provider(model: str, *, explicit: Optional[str] = None) -> str:
    """Return the canonical provider string for a model + explicit override."""
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
    """Instantiate the right LLM client. Returns AnthropicClient or DeepSeekClient.

    Both classes share the same `chat(messages, system, tools, max_tokens)
    -> ChatResponse` surface, so the agent loop treats them as
    interchangeable.
    """
    resolved = resolve_provider(model, explicit=provider)
    if resolved == PROVIDER_DEEPSEEK:
        from engine.llm.deepseek import DeepSeekClient
        return DeepSeekClient(api_key=api_key, model=model, base_url=base_url)
    # Default + explicit "anthropic"
    from engine.llm.anthropic import AnthropicClient
    return AnthropicClient(api_key=api_key, model=model, base_url=base_url)
