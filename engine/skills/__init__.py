# Copyright (c) 2026 Ubion ax center
"""Skill subsystem entry points.

`build_default_skill_tools()` returns the Phase 1 default tool catalogue
the AIAgent should register so the poet-agent scenario has working
`skill_view` + `skill_manage` access. Importing the module triggers
side-effects in skill_manager.py (it registers itself with the registry
stub), so callers don't need to import the module directly.

Companion accelerator: ``engine.skills.index`` keeps a cached frontmatter
table in ``<agent_home>/.skill-index.json`` so repeated enumerations cost
~67 ms instead of ~488 ms (85-skill measurement, dev hardware). See that
module's docstring for the cache invalidation rules.
"""

from __future__ import annotations

from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.core.agent import Tool


def build_default_skill_tools() -> "List[Tool]":
    """Construct the Phase 1 default skill toolset.

    Includes:
      - `skill_view` (Unit 2, lives in engine/tools/skill_view.py)
      - `skill_manage` (Unit 8, vendored manager.py registers itself via
        engine.tools.registry at import time)

    The skill_view module brings its own Tool factory; skill_manage we
    shape here from the registry entry so the schema/handler stay in
    sync with the upstream definition.
    """
    from engine.core.agent import Tool
    # Trigger skill_manage registration as a side effect of importing
    # the module — registry.register() runs at module top level.
    from engine.skills import manager as _manager  # noqa: F401
    from engine.tools.registry import registry
    from engine.tools.skill_view import build_skill_view_tool

    tools: List[Tool] = [build_skill_view_tool()]

    entry = registry.get("skill_manage")
    if entry is not None:
        schema = entry.get("schema") or {}
        params = schema.get("parameters") or {"type": "object", "properties": {}}
        tools.append(
            Tool(
                name=schema.get("name", "skill_manage"),
                description=schema.get("description", "Manage skills."),
                schema=params,
                handler=lambda args, _h=entry["handler"]: _h(args or {}),
            )
        )

    # Hermes-식 분리 (사용자 결정 2026-05-14) — optional 풀에서 명시 설치만
    # 활성. 다음 세 도구가 모델에게 "필요한 스킬을 골라서 들여놔" 의 인터페이스.
    tools.extend(_build_optional_skill_tools())
    return tools


def _build_optional_skill_tools() -> "List[Tool]":
    """Tools that let the agent search / install / uninstall optional skills."""
    import json as _json
    from engine.core.agent import Tool
    from engine.storage.agent_home import (
        list_optional_skills,
        install_optional_skill,
        uninstall_skill,
        list_installed_skills,
    )

    def _skills_search(args):
        query = ((args or {}).get("query") or "").strip().lower()
        category = ((args or {}).get("category") or "").strip().lower()
        installed_only = bool((args or {}).get("installed_only", False))
        results = list_optional_skills()
        if installed_only:
            results = [r for r in results if r.get("installed")]
        if category:
            results = [r for r in results if r["category"].lower() == category]
        if query:
            results = [
                r for r in results
                if query in r["name"].lower() or query in (r.get("description") or "").lower()
            ]
        # 결과 30 개로 제한 (LLM 컨텍스트 보호)
        return _json.dumps({"matches": results[:30], "total": len(results)}, ensure_ascii=False)

    def _skills_install(args):
        name = ((args or {}).get("name") or "").strip()
        if not name:
            return _json.dumps({"error": "missing 'name'"})
        return _json.dumps(install_optional_skill(name), ensure_ascii=False)

    def _skills_uninstall(args):
        name = ((args or {}).get("name") or "").strip()
        if not name:
            return _json.dumps({"error": "missing 'name'"})
        return _json.dumps(uninstall_skill(name), ensure_ascii=False)

    def _skills_installed(args):
        return _json.dumps({"installed": list_installed_skills()}, ensure_ascii=False)

    return [
        Tool(
            name="skills_search",
            description=(
                "Search the optional skill pool (86 SKILL.md bundles from "
                "Hermes Agent, MIT). The agent starts with NO skills "
                "installed — call this when the user asks for help with a "
                "task that might benefit from an existing skill, then call "
                "`skills_install` to bring it into the active pool. Returns "
                "name / category / description / installed flag."
            ),
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Substring match on name + description."},
                    "category": {"type": "string", "description": "Filter by category (e.g. creative, productivity)."},
                    "installed_only": {"type": "boolean", "description": "When true, only return already-installed skills."},
                },
            },
            handler=_skills_search,
        ),
        Tool(
            name="skills_install",
            description=(
                "Install a skill from the optional pool into the active "
                "agent_home so its SKILL.md becomes loadable. Idempotent — "
                "re-installing returns 'already_installed'. Records "
                "provenance in `~/.ubion-agent/.hub/lock.json`."
            ),
            schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill folder name from skills_search results."},
                },
                "required": ["name"],
            },
            handler=_skills_install,
        ),
        Tool(
            name="skills_uninstall",
            description=(
                "Remove a previously installed optional skill. Does NOT "
                "touch user-authored or self-evolved skills under "
                "`skills/custom/`."
            ),
            schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Installed skill name."},
                },
                "required": ["name"],
            },
            handler=_skills_uninstall,
        ),
        Tool(
            name="skills_installed",
            description="List skills currently installed from the optional pool, with provenance.",
            schema={"type": "object", "properties": {}},
            handler=_skills_installed,
        ),
    ]
