# Vendor copy from NousResearch/hermes-agent (MIT License)
# Original: https://github.com/NousResearch/hermes-agent/blob/b06e9993021a8eebd891fc60d52372446315b2f0/tools/registry.py
# Selective extract: `tool_error` (lines 537-548) + `tool_result` (lines 551-563)
# only. Upstream registry.py is a 600+ line tool dispatch hub we're not
# adopting until Unit 8 — the two JSON helpers are pulled here so the
# vendored memory_manager (Unit 6) can import them unchanged.
#
# Copyright (c) 2025 Nous Research
#
# This file is licensed under the MIT License. See engine/NOTICE.md.
"""JSON-shaped return helpers for tool handlers."""

from __future__ import annotations

import json


def tool_error(message, **extra) -> str:
    """Return a JSON error string for tool handlers.

    >>> tool_error("file not found")
    '{"error": "file not found"}'
    >>> tool_error("bad input", success=False)
    '{"error": "bad input", "success": false}'
    """
    result = {"error": str(message)}
    if extra:
        result.update(extra)
    return json.dumps(result, ensure_ascii=False)


def tool_result(data=None, **kwargs) -> str:
    """Return a JSON result string for tool handlers.

    Accepts a dict positional arg *or* keyword arguments (not both):

    >>> tool_result(success=True, count=42)
    '{"success": true, "count": 42}'
    >>> tool_result({"key": "value"})
    '{"key": "value"}'
    """
    if data is not None:
        return json.dumps(data, ensure_ascii=False)
    return json.dumps(kwargs, ensure_ascii=False)


class _ToolRegistry:
    """Compatibility stub for the Hermes `tools.registry.registry` object.

    Vendored skill_manager_tool.py and friends end with a
    ``registry.register(name=..., schema=..., handler=...)`` call so the
    upstream tool dispatcher can find them. Our dispatcher lives in
    `engine.core.tool_dispatch` and reads `Tool` dataclass entries off
    `AIAgent._tools`, so registration here is just bookkeeping — we
    collect entries for `iter_registered_tools()` to expose later, and
    the actual wiring to AIAgent happens via Unit 8 helpers.
    """

    def __init__(self) -> None:
        self._entries: dict = {}

    def register(self, *, name: str, handler, schema=None, **_ignored) -> None:
        self._entries[name] = {
            "name": name,
            "schema": schema,
            "handler": handler,
        }

    def get(self, name: str):
        return self._entries.get(name)

    def names(self) -> list:
        return list(self._entries.keys())


registry = _ToolRegistry()
