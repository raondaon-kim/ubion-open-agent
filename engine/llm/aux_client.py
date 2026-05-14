# Copyright (c) 2026 Ubion ax center
#
# Inspiration: NousResearch/hermes-agent agent/auxiliary_client.py (MIT).
# This is NOT a Vendor copy — upstream is 4,179 lines covering 6 providers
# and a multi-tier resolution chain. We expose the two symbols
# context_compressor depends on (call_llm, _is_connection_error) and route
# them through our existing engine.llm.anthropic.AnthropicClient.
"""Auxiliary LLM call adapter.

context_compressor.py imports:
    from agent.auxiliary_client import call_llm, _is_connection_error

We provide signature-compatible shims. The compressor never touches the
provider-resolution machinery from upstream — it just calls call_llm
with `task="compression"` and reads `response.choices[0].message.content`.

OpenAI-shaped response surface kept intentionally — vendored context_compressor
treats responses as OpenAI ChatCompletion objects, so our adapter wraps the
Anthropic reply in the same shape (just enough for compressor to read
.choices[0].message.content).

Note: this module is named ``aux_client``, NOT ``aux``. ``aux`` is a
reserved DOS device name on Windows; Python's import machinery refuses
to load a module called that even though the file is readable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from engine.llm.anthropic import AnthropicClient, ChatResponse

logger = logging.getLogger(__name__)


@dataclass
class _ShimMessage:
    content: str
    role: str = "assistant"


@dataclass
class _ShimChoice:
    message: _ShimMessage
    finish_reason: str = "stop"
    index: int = 0


@dataclass
class _ShimResponse:
    """OpenAI ChatCompletion-shaped wrapper around our ChatResponse."""

    choices: List[_ShimChoice]
    usage: Dict[str, Any]
    model: str
    raw: Optional[ChatResponse] = None


def _is_connection_error(exc: BaseException) -> bool:
    """Best-effort classification of network-tier failures.

    Used by context_compressor's streaming retry branch. We never stream
    compression in Phase 1 (compression uses non-streaming chat), so this
    is mostly defensive — return False for non-network errors so the
    upstream retry/fallback path does not trip on logic exceptions.
    """
    import socket
    if isinstance(exc, (ConnectionError, TimeoutError, socket.gaierror, socket.timeout)):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in ("connection", "timed out", "timeout", "reset by peer", "broken pipe")
    )


def _split_system(messages: List[Dict[str, Any]]) -> tuple[Optional[str], List[Dict[str, Any]]]:
    """Separate the leading system message from the rest.

    Anthropic's Messages API takes `system` as a top-level parameter, not
    inline in messages. context_compressor passes OpenAI-style messages
    with role="system" at index 0 (or absent). Split here so the adapter
    can pass system text through to AnthropicClient.chat correctly.
    """
    if not messages:
        return None, []
    if messages[0].get("role") == "system":
        return str(messages[0].get("content") or ""), list(messages[1:])
    return None, list(messages)


def _coerce_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strip OpenAI-only fields and pass user/assistant messages through.

    Compression prompts are plain text turns — no tool_use, no images —
    so this is a thin pass-through. Tool result blocks from a wider
    transcript pre-compression are already shaped for Anthropic.
    """
    out: List[Dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in {"user", "assistant"}:
            continue
        out.append({"role": role, "content": msg.get("content", "")})
    return out


def call_llm(
    task: str = None,
    *,
    provider: str = None,
    model: str = None,
    base_url: str = None,
    api_key: str = None,
    main_runtime: Optional[Dict[str, Any]] = None,
    messages: List[Dict[str, Any]],
    temperature: float = None,
    max_tokens: int = None,
    tools: list = None,
    timeout: float = None,
    extra_body: dict = None,
) -> _ShimResponse:
    """Phase 1 auxiliary LLM call — routes everything through AnthropicClient.

    Signature mirrors agent/auxiliary_client.call_llm so vendored
    context_compressor calls land here unchanged. Args not relevant to
    Anthropic (provider, base_url, extra_body, tools, timeout) are
    accepted and ignored.

    `main_runtime` (the parent agent's provider/model snapshot) lets the
    upstream auxiliary pick the same key for compression as for the main
    turn. We use it only as a fallback model hint.
    """
    if tools:
        logger.debug("call_llm tools=%s ignored in Phase 1 aux adapter", len(tools))

    chosen_model = (
        model
        or (main_runtime or {}).get("model")
        or "claude-opus-4-7"
    )
    system_text, plain_messages = _split_system(messages)
    plain_messages = _coerce_messages(plain_messages)

    client = AnthropicClient(api_key=api_key, model=chosen_model, base_url=base_url)
    chat_response: ChatResponse = client.chat(
        messages=plain_messages,
        system=system_text,
        tools=None,
        max_tokens=max_tokens or 4096,
    )

    return _ShimResponse(
        choices=[_ShimChoice(message=_ShimMessage(content=chat_response.text or ""))],
        usage=chat_response.usage or {},
        model=chosen_model,
        raw=chat_response,
    )


async def async_call_llm(
    task: str = None,
    *,
    provider: str = None,
    model: str = None,
    base_url: str = None,
    api_key: str = None,
    main_runtime: Optional[Dict[str, Any]] = None,
    messages: List[Dict[str, Any]],
    temperature: float = None,
    max_tokens: int = None,
    tools: list = None,
    timeout: float = None,
    extra_body: dict = None,
) -> _ShimResponse:
    """Async sibling of `call_llm` for vendored async callers.

    Our underlying AnthropicClient.chat is sync — we wrap the sync call
    in `asyncio.to_thread` so the caller can `await` without blocking
    the event loop. session_search_tool.py uses this when reranking
    matches with the LLM. The Anthropic SDK supports a real async client
    too; switching to it lands in Phase 2 once we have multiple async
    consumers worth optimising for.
    """
    import asyncio
    return await asyncio.to_thread(
        call_llm,
        task,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        main_runtime=main_runtime,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=tools,
        timeout=timeout,
        extra_body=extra_body,
    )


def _run_async(coro):
    """Run an async coroutine from a sync context.

    Vendored session_search_tool.py imports `model_tools._run_async`.
    Upstream Hermes has a 100-line implementation handling running event
    loops, worker-thread isolation, and persistent loops for cached
    async clients. Our Phase 1 surface only calls this from sync tool
    handlers with no existing loop, so a tight `asyncio.run`-fallback is
    enough — if a future caller is already inside an event loop we
    detect it and spin up a worker thread so the coroutine still runs.
    """
    import asyncio
    import concurrent.futures

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()

    return asyncio.run(coro)


def extract_content_or_reasoning(response) -> str:
    """Extract text from an LLM response, falling back to reasoning fields.

    Vendored from auxiliary_client.py:4404. Strips inline <think> blocks
    from `message.content` and falls back to `message.reasoning` /
    `reasoning_content` / `reasoning_details` for models that return
    structured reasoning instead of plain content.
    """
    import re

    msg = response.choices[0].message
    content = (msg.content or "").strip() if hasattr(msg, "content") else ""

    if content:
        cleaned = re.sub(
            r"<(?:think|thinking|reasoning|thought|REASONING_SCRATCHPAD)>"
            r".*?"
            r"</(?:think|thinking|reasoning|thought|REASONING_SCRATCHPAD)>",
            "", content, flags=re.DOTALL | re.IGNORECASE,
        ).strip()
        if cleaned:
            return cleaned

    reasoning_parts: list[str] = []
    for field in ("reasoning", "reasoning_content"):
        val = getattr(msg, field, None)
        if val and isinstance(val, str) and val.strip() and val not in reasoning_parts:
            reasoning_parts.append(val.strip())

    details = getattr(msg, "reasoning_details", None)
    if details and isinstance(details, list):
        for detail in details:
            if isinstance(detail, dict):
                summary = (
                    detail.get("summary")
                    or detail.get("content")
                    or detail.get("text")
                )
                if summary and summary not in reasoning_parts:
                    text_value = summary.strip() if isinstance(summary, str) else str(summary)
                    reasoning_parts.append(text_value)

    if reasoning_parts:
        return "\n\n".join(reasoning_parts)

    return ""
