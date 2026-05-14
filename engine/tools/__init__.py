# Copyright (c) 2026 Ubion ax center
"""Tool subsystem entry points."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from engine.core.agent import Tool


def build_session_search_tool() -> "Tool":
    """Construct the Tool wrapper for the vendored session_search handler.

    Importing engine.tools.session_search triggers a side-effect that
    registers the tool with our registry stub; we then reshape the
    OpenAI-style schema into our Tool dataclass.
    """
    from engine.core.agent import Tool
    from engine.tools import session_search as _ss  # noqa: F401 — register side-effect
    from engine.tools.registry import registry

    entry = registry.get("session_search")
    if entry is None:
        raise RuntimeError("session_search registration missing — module import failed")
    schema = entry["schema"]
    params = schema.get("parameters") or {"type": "object", "properties": {}}
    return Tool(
        name=schema.get("name", "session_search"),
        description=schema.get("description", "Search prior sessions."),
        schema=params,
        handler=lambda args, _h=entry["handler"]: _h(args or {}),
    )
