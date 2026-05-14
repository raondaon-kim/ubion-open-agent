# Ported from NousResearch/hermes-agent (MIT License)
# Original: https://github.com/NousResearch/hermes-agent/blob/b06e9993021a8eebd891fc60d52372446315b2f0/agent/model_metadata.py
# Narrowed scope: 3 symbols + 2 transitive helpers that context_compressor
# imports. Upstream is 1,574 lines covering 9-step provider fallback chain
# (Anthropic, OpenAI, Codex, Copilot, Nous, OpenRouter, Bedrock, Ollama,
# LMStudio, GMI). Phase 1 = Anthropic-only, so get_model_context_length
# is reduced to a static catalog with one fallback.
#
# Copyright (c) 2025 Nous Research (original algorithm)
# Copyright (c) 2026 Ubion ax center (implementation)
#
# This file is licensed under the MIT License. See engine/NOTICE.md.
"""Model metadata + rough token estimation.

context_compressor needs three symbols:
    - MINIMUM_CONTEXT_LENGTH
    - get_model_context_length(model, ...)
    - estimate_messages_tokens_rough(messages)

Upstream resolves context length via cache → live API probe → models.dev →
hardcoded catalog → 256K fallback. We replace steps 1-3 with a static
catalog because Phase 1 only targets Anthropic Claude. Switching providers
later means extending CLAUDE_CONTEXT_LENGTHS or restoring the upstream
resolution chain.

The token estimator is byte-identical to upstream (rough char/4 +
flat-rate image cost). Algorithm preserved.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


MINIMUM_CONTEXT_LENGTH = 64_000


# Anthropic published context window per model family. Keys match the
# canonical model IDs we expect to see at request time.
_CLAUDE_CONTEXT_LENGTHS: Dict[str, int] = {
    "claude-opus-4-7": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
}

# DeepSeek catalog (Unit 13). v4 family is the active default; v3-era
# `deepseek-chat` / `deepseek-reasoner` are scheduled to be deprecated
# 2026-07-24 per the official API docs.
_DEEPSEEK_CONTEXT_LENGTHS: Dict[str, int] = {
    "deepseek-v4-flash": 128_000,
    "deepseek-v4-pro": 128_000,
    "deepseek-chat": 128_000,        # deprecated 2026-07-24
    "deepseek-reasoner": 128_000,    # deprecated 2026-07-24
}

_DEFAULT_CONTEXT_LENGTH = 200_000


def get_model_context_length(
    model: str,
    base_url: str = "",
    api_key: str = "",
    config_context_length: int | None = None,
    provider: str = "",
    custom_providers: list | None = None,
) -> int:
    """Return the context length (tokens) for the given model.

    Resolution order (Phase 1 simplified):
      0. explicit config_context_length override
      1. static Claude / DeepSeek catalog match (exact or prefix)
      2. _DEFAULT_CONTEXT_LENGTH

    Signature kept compatible with upstream so vendored context_compressor
    calls don't need to change.
    """
    if (
        config_context_length is not None
        and isinstance(config_context_length, int)
        and config_context_length > 0
    ):
        return config_context_length

    if not model:
        return _DEFAULT_CONTEXT_LENGTH

    # Exact match first — Claude family then DeepSeek family.
    direct = _CLAUDE_CONTEXT_LENGTHS.get(model) or _DEEPSEEK_CONTEXT_LENGTHS.get(model)
    if direct is not None:
        return direct

    # Fall back to prefix match — handles snapshot ids like
    # "claude-opus-4-7-20251101" before we add them to the catalog.
    for key, length in _CLAUDE_CONTEXT_LENGTHS.items():
        if model.startswith(key):
            return length
    for key, length in _DEEPSEEK_CONTEXT_LENGTHS.items():
        if model.startswith(key):
            return length

    return _DEFAULT_CONTEXT_LENGTH


def _count_image_tokens(msg: Dict[str, Any], cost_per_image: int) -> int:
    """Count image-like content parts in a message; return their token cost."""
    count = 0
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype in {"image", "image_url", "input_image"}:
                count += 1
    stashed = msg.get("_anthropic_content_blocks") if isinstance(msg, dict) else None
    if isinstance(stashed, list):
        for part in stashed:
            if isinstance(part, dict) and part.get("type") == "image":
                count += 1
    if isinstance(content, dict) and content.get("_multimodal"):
        inner = content.get("content")
        if isinstance(inner, list):
            for part in inner:
                if isinstance(part, dict) and part.get("type") in {"image", "image_url"}:
                    count += 1
    return count * cost_per_image


def _estimate_message_chars(msg: Dict[str, Any]) -> int:
    """Char count for token estimation, excluding base64 image data.

    Base64 images are counted via _count_image_tokens instead; including
    their raw chars here would massively overestimate token usage.
    """
    if not isinstance(msg, dict):
        return len(str(msg))
    shadow: Dict[str, Any] = {}
    for k, v in msg.items():
        if k == "_anthropic_content_blocks":
            continue
        if k == "content":
            if isinstance(v, list):
                cleaned = []
                for part in v:
                    if isinstance(part, dict):
                        if part.get("type") in {"image", "image_url", "input_image"}:
                            cleaned.append({"type": part.get("type"), "image": "[stripped]"})
                        else:
                            cleaned.append(part)
                    else:
                        cleaned.append(part)
                shadow[k] = cleaned
            elif isinstance(v, dict) and v.get("_multimodal"):
                shadow[k] = v.get("text_summary", "")
            else:
                shadow[k] = v
        else:
            shadow[k] = v
    return len(str(shadow))


def estimate_messages_tokens_rough(messages: List[Dict[str, Any]]) -> int:
    """Rough token estimate for a message list (pre-flight only).

    Image parts (base64 PNG/JPEG) are counted as a flat ~1500 tokens per
    image — the Anthropic pricing model — instead of counting raw base64
    character length. Without this, a single ~1MB screenshot would be
    estimated at ~250K tokens and trigger premature context compression.
    """
    _IMAGE_TOKEN_COST = 1500
    total_chars = 0
    image_tokens = 0
    for msg in messages:
        total_chars += _estimate_message_chars(msg)
        image_tokens += _count_image_tokens(msg, _IMAGE_TOKEN_COST)
    return ((total_chars + 3) // 4) + image_tokens


def estimate_request_tokens_rough(
    messages: List[Dict[str, Any]],
    *,
    system_prompt: str = "",
    tools: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Rough token estimate for a full chat-completions request.

    Includes the major payload buckets we send to Anthropic: system prompt,
    conversation messages, and tool schemas. With 50+ tools enabled,
    schemas alone can add 20-30K tokens — a significant blind spot when
    only counting messages.
    """
    total = 0
    if system_prompt:
        total += (len(system_prompt) + 3) // 4
    if messages:
        total += estimate_messages_tokens_rough(messages)
    if tools:
        total += (len(str(tools)) + 3) // 4
    return total
