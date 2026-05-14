# Copyright (c) 2026 Ubion ax center
"""DeepSeek API client — Phase 1 Unit 13.

DeepSeek exposes an OpenAI-compatible HTTP surface at
`https://api.deepseek.com`. We reuse the official `openai` SDK and just
swap the base_url so we get the same connection pool / retry / error
classification for free.

Surface matches engine.llm.anthropic.AnthropicClient so callers don't
need to branch on provider:

    DeepSeekClient(api_key, model).chat(
        messages: list[dict],
        system: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> ChatResponse

ChatResponse / ToolCall types are reused from engine.llm.anthropic.

Message shape conversion:
    Anthropic messages have `tool_use` and `tool_result` content blocks
    inline in the messages list. OpenAI uses separate `tool_calls` on
    assistant turns and `role: "tool"` messages for results. We
    translate when sending; on receive we re-shape OpenAI tool_calls
    back into our normalized ToolCall.

Tool schema conversion:
    Anthropic tool schema is `{name, description, input_schema}`. OpenAI
    is `{type: "function", function: {name, description, parameters}}`.
    We translate so the agent layer's Tool dataclass (Anthropic shape)
    stays the single source of truth.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover — required dep
    raise RuntimeError(
        "engine.llm.deepseek: the `openai` package is required. "
        "Install: pip install openai"
    ) from exc

from engine.llm.anthropic import ChatResponse, ToolCall


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_MAX_TOKENS = 4096


class DeepSeekClient:
    """Thin synchronous client around openai.OpenAI pointed at DeepSeek.

    One instance is bound to a single (api_key, model) pair. Like
    AnthropicClient, this is thread-safe for config reads; concurrent
    chat() calls are safe because the underlying SDK manages its own
    connection pool.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "",
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "DeepSeekClient: DEEPSEEK_API_KEY is not set and api_key= "
                "was not provided."
            )
        self.model = model or os.environ.get("DEEPSEEK_MODEL", "") or DEFAULT_MODEL
        self.base_url = base_url or DEEPSEEK_BASE_URL
        self._sdk = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> ChatResponse:
        """Send one turn and return the normalized response.

        ``messages`` arrives in our Anthropic-native format (the agent
        loop's convention). We translate to OpenAI shape, send, and
        re-shape the reply back into our normalized ChatResponse.
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


# ----------------------------------------------------------------------
# Message + tool translation (Anthropic shape ↔ OpenAI shape)
# ----------------------------------------------------------------------


def _to_openai_messages(
    messages: List[Dict[str, Any]],
    *,
    system: Optional[str],
) -> List[Dict[str, Any]]:
    """Flatten Anthropic-shape messages into OpenAI's chat completion list.

    - A leading system prompt (passed as `system=` arg) becomes a
      `role: system` message at index 0.
    - Anthropic assistant turns whose content is a list of blocks get
      split: text blocks join into `content`, `tool_use` blocks turn
      into the OpenAI `tool_calls` array on the same message.
    - Anthropic user turns whose content carries `tool_result` blocks
      get split into one `role: tool` message per tool_use_id.
    """
    out: List[Dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "assistant":
            text_parts: List[str] = []
            tool_calls: List[Dict[str, Any]] = []
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        text_parts.append(str(block.get("text", "")))
                    elif btype == "tool_use":
                        tool_calls.append({
                            "id": block.get("id", "") or _mint_call_id(),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(
                                    block.get("input") or {},
                                    ensure_ascii=False,
                                ),
                            },
                        })
            else:
                text_parts.append(str(content or ""))

            entry: Dict[str, Any] = {"role": "assistant"}
            joined = "\n".join(p for p in text_parts if p)
            if joined:
                entry["content"] = joined
            else:
                # OpenAI requires `content` even when tool_calls is set;
                # explicit None / empty string both work depending on
                # version — be safe with empty string.
                entry["content"] = ""
            if tool_calls:
                entry["tool_calls"] = tool_calls
            # DeepSeek thinking mode: echo back reasoning_content when the
            # original assistant turn produced one. Skipping it on a
            # tool-call turn triggers HTTP 400 from the API.
            reasoning = msg.get("reasoning_content")
            if reasoning:
                entry["reasoning_content"] = str(reasoning)
            out.append(entry)
            continue

        if role == "user" and isinstance(content, list):
            # Anthropic packs `tool_result` blocks in a user turn. OpenAI
            # uses a separate `role: tool` message per result.
            user_text_parts: List[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_result":
                    out.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": _stringify_tool_content(block.get("content", "")),
                    })
                elif btype == "text":
                    user_text_parts.append(str(block.get("text", "")))
            if user_text_parts:
                out.append({"role": "user", "content": "\n".join(user_text_parts)})
            continue

        # Simple text user / system messages
        if isinstance(content, list):
            content = "\n".join(
                str(b.get("text", "")) for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        out.append({"role": role, "content": str(content or "")})

    return out


def _stringify_tool_content(content: Any) -> str:
    """Flatten an Anthropic tool_result content into the string OpenAI wants."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            else:
                parts.append(json.dumps(block, ensure_ascii=False, default=str))
        return "\n".join(parts)
    return str(content)


def _tool_to_openai(tool: Dict[str, Any]) -> Dict[str, Any]:
    """Anthropic tool schema → OpenAI function-calling schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
        },
    }


def _normalize_completion(completion: Any) -> ChatResponse:
    """Flatten an openai.types.ChatCompletion into our ChatResponse shape."""
    choice = completion.choices[0] if completion.choices else None
    if choice is None:
        return ChatResponse(text="", stop_reason="empty", raw=completion)

    msg = choice.message
    text = (msg.content or "").strip() if hasattr(msg, "content") else ""

    tool_calls: List[ToolCall] = []
    raw_calls = getattr(msg, "tool_calls", None) or []
    for call in raw_calls:
        fn = getattr(call, "function", None)
        if fn is None:
            continue
        raw_args = getattr(fn, "arguments", "") or "{}"
        try:
            parsed = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except json.JSONDecodeError:
            parsed = {}
        tool_calls.append(
            ToolCall(
                id=getattr(call, "id", "") or _mint_call_id(),
                name=getattr(fn, "name", "") or "",
                arguments=parsed if isinstance(parsed, dict) else {},
            )
        )

    usage: Dict[str, int] = {}
    usage_obj = getattr(completion, "usage", None)
    if usage_obj is not None:
        usage = {
            "input_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
        }

    reasoning_content = getattr(msg, "reasoning_content", "") or ""

    return ChatResponse(
        text=text,
        tool_calls=tool_calls,
        stop_reason=getattr(choice, "finish_reason", "") or "",
        usage=usage,
        raw=completion,
        reasoning_content=str(reasoning_content),
    )


def _mint_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:24]}"
