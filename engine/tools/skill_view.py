# Inspired by NousResearch/hermes-agent tools/skills_tool.py (MIT License)
# — schema and intent only; implementation is independent.
#
# Copyright (c) 2026 Ubion ax center
"""skill_view tool — lazy-load a skill's SKILL.md body for the LLM.

This is the agent-facing half of the progressive-disclosure pattern:
  - System prompt lists `(name, description)` for every available skill.
  - When the LLM decides a skill is relevant, it calls
    ``skill_view(name="foo")`` and gets the full SKILL.md.
  - Bumps ``use_count`` + ``last_used_at`` in ``.usage.json`` so the
    curator (engine.learning.curator) can later decide lifecycle.

Phase 1 Unit 2 scope:
  - Main body load only. ``file_path`` parameter for references/templates/
    scripts is accepted but not implemented yet (returns
    ``unsupported_in_unit_2`` error). That lands in Unit 8 along with the
    file-read tool family.
  - Template variable substitution (``${HERMES_SKILL_DIR}`` etc.) is
    applied via engine.skills.preprocessing.preprocess_skill_content.
  - Inline-shell expansion (``!`cmd``) stays OFF — security risk, opt-in
    only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from engine.core.agent import Tool
from engine.skills import usage as skill_usage
from engine.skills import utils as skill_utils


SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": (
                "The skill name as listed in the system prompt's "
                "<available_skills> block."
            ),
        },
        "file_path": {
            "type": "string",
            "description": (
                "OPTIONAL: Path to a linked file inside the skill directory "
                "(e.g. 'references/api.md'). Not yet supported in Phase 1 "
                "Unit 2 — leave empty for now."
            ),
        },
    },
    "required": ["name"],
}

DESCRIPTION = (
    "Load a skill's full SKILL.md content. Skills are class-level "
    "instructions and experiential knowledge persisted under the agent "
    "home. Call this when a skill listed in <available_skills> is "
    "relevant to the current task; follow its instructions."
)


def _find_skill_dir(name: str) -> Optional[Path]:
    """Locate the directory of skill ``name``. Returns None if not found."""
    skills_root = skill_utils.get_skills_dir()
    if not skills_root.exists():
        return None
    # Match either a flat ``<root>/<name>/SKILL.md`` or any nested layout.
    for skill_md in skills_root.rglob("SKILL.md"):
        try:
            rel = skill_md.relative_to(skills_root)
        except ValueError:
            continue
        if rel.parts and rel.parts[0].startswith("."):
            # Skip .archive, .hub, .git, etc.
            continue
        # Try frontmatter `name:` first, then directory name as fallback.
        # _read_skill_name lives in engine.skills.usage (vendored from
        # tools/skill_usage.py).
        frontmatter_name = skill_usage._read_skill_name(  # noqa: SLF001
            skill_md, fallback=skill_md.parent.name
        )
        if frontmatter_name == name or skill_md.parent.name == name:
            return skill_md.parent
    return None


def _handler(args: Dict[str, Any]) -> str:
    """Tool handler. Returns a JSON string (Anthropic tool_result content)."""
    name = (args or {}).get("name", "").strip()
    file_path = (args or {}).get("file_path", "").strip()

    if not name:
        return json.dumps({"success": False, "error": "missing 'name'"})

    if file_path:
        return json.dumps(
            {
                "success": False,
                "error": "file_path is unsupported_in_unit_2",
            }
        )

    skill_dir = _find_skill_dir(name)
    if skill_dir is None:
        return json.dumps(
            {"success": False, "error": f"skill not found: {name!r}"}
        )

    skill_md_path = skill_dir / "SKILL.md"
    try:
        raw = skill_md_path.read_text(encoding="utf-8")
    except OSError as exc:
        return json.dumps(
            {"success": False, "error": f"cannot read SKILL.md: {exc}"}
        )

    # Template substitution (no inline shell — security). session_id is
    # not yet exposed in Unit 2; pass None and let unresolved tokens remain.
    from engine.skills.preprocessing import (
        substitute_template_vars,
    )

    body = substitute_template_vars(raw, skill_dir, None)

    # Telemetry — best-effort, never break the tool call.
    try:
        skill_usage.bump_use(name)
        skill_usage.bump_view(name)
    except Exception:
        pass

    # Enumerate linked files so the LLM knows what else is available even
    # though Unit 2 can't load them.
    linked_files = {
        sub.name: sorted(p.name for p in sub.iterdir() if p.is_file())
        for sub in (skill_dir / s for s in ("references", "templates", "scripts", "assets"))
        if sub.exists() and sub.is_dir()
    }

    return json.dumps(
        {
            "success": True,
            "name": name,
            "content": body,
            "skill_dir": str(skill_dir),
            "linked_files": linked_files,
        },
        ensure_ascii=False,
    )


TOOL: Tool = Tool(
    name="skill_view",
    description=DESCRIPTION,
    schema=SCHEMA,
    handler=_handler,
)


def build_skill_view_tool() -> Tool:
    """Return the singleton skill_view Tool entry.

    Factory exposed so engine.skills.build_default_skill_tools() can
    grab skill_view + skill_manage as a pair without each call site
    importing the constant directly.
    """
    return TOOL
