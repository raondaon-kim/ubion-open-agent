# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 7 — skill utils wiring + agent_home extensions.

Unit 2 already vendored most of agent/skill_utils.py and
agent/skill_preprocessing.py. Unit 7 closes the gap:
    - agent/skill_commands.py vendor copy (slash command resolution)
    - display_hermes_home() helper in storage/agent_home.py
    - AIAgent.valid_tool_names is the set Unit 4 (prompt builder) reads
    - _attach_memory_manager folds provider tool names into valid_tool_names

Run:
    python -m unittest tests.unit.test_skills_wiring -v
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import Any, Dict, List

from engine.core.agent import AIAgent, Tool
from engine.learning.memory_manager import MemoryManager
from engine.learning.memory_provider import MemoryProvider
from engine.skills.commands import _resolve_skill_commands_platform
from engine.skills.preprocessing import substitute_template_vars
from engine.skills.usage import list_agent_created_skill_names
from engine.skills.utils import (
    get_disabled_skill_names,
    parse_frontmatter,
    skill_matches_platform,
)
from engine.storage.agent_home import (
    display_hermes_home,
    get_hermes_home,
    get_skills_dir,
)


class _StubProviderWithTools(MemoryProvider):
    """Provider that advertises tool schemas so we can verify the AIAgent
    merges them into valid_tool_names on _attach_memory_manager()."""

    def __init__(self, name: str, tool_names: List[str]) -> None:
        self._name = name
        self._tool_names = tool_names

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        return True

    def initialize(self, session_id: str, **kwargs) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def system_prompt_block(self) -> str:
        return ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        return ""

    def sync_turn(self, user_message, assistant_message, *, session_id="", **kwargs):
        return None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [{"name": n, "description": n, "input_schema": {}} for n in self._tool_names]

    def handle_tool_call(self, name: str, args: Dict[str, Any]) -> str:
        return "{}"


def _build_agent(tools=None) -> AIAgent:
    return AIAgent(
        model="claude-opus-4-7",
        api_key="sk-test-fake",
        tools=tools,
        quiet_mode=True,
    )


class AgentHomeDisplayTest(unittest.TestCase):
    def test_display_under_home_uses_tilde(self):
        # Default UBION_AGENT_HOME resolves to ~/.ubion-agent, which sits
        # under Path.home() — display should collapse to ~/...
        with self._with_env(UBION_AGENT_HOME="", HERMES_HOME=""):
            text = display_hermes_home()
            self.assertTrue(text.startswith("~/"), f"got: {text!r}")
            self.assertIn(".ubion-agent", text)

    def test_display_absolute_path_when_outside_home(self):
        # Force a path outside HOME so the tilde shortcut can't apply
        outside = "C:\\TempAgentHomeForTest"
        with self._with_env(UBION_AGENT_HOME=outside):
            text = display_hermes_home()
            self.assertEqual(text.replace("\\", "/").rstrip("/"),
                             outside.replace("\\", "/").rstrip("/"))

    def _with_env(self, **kwargs):
        return _EnvCtx(kwargs)


class _EnvCtx:
    def __init__(self, overrides: Dict[str, str]):
        self.overrides = overrides
        self.original: Dict[str, str | None] = {}

    def __enter__(self):
        for k, v in self.overrides.items():
            self.original[k] = os.environ.get(k)
            if v:
                os.environ[k] = v
            elif k in os.environ:
                del os.environ[k]
        return self

    def __exit__(self, exc_type, exc, tb):
        for k, prev in self.original.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


class SkillImportSurfaceTest(unittest.TestCase):
    def test_commands_module_loads(self):
        # _resolve_skill_commands_platform should be callable and return
        # None when no platform env var is set.
        with _EnvCtx({"HERMES_PLATFORM": ""}):
            self.assertIsNone(_resolve_skill_commands_platform())

    def test_substitute_template_vars(self):
        # substitute_template_vars replaces ${HERMES_SKILL_DIR} with
        # the skill_dir argument and leaves unknown tokens alone.
        out = substitute_template_vars(
            "look at ${HERMES_SKILL_DIR}/SKILL.md",
            skill_dir=Path("/tmp/my-skill"),
            session_id="abc",
        )
        self.assertIn("/tmp/my-skill", out.replace("\\", "/"))

    def test_skill_matches_platform_default(self):
        # No platforms key → skill is universally compatible
        self.assertTrue(skill_matches_platform({}))
        # Explicit empty list → also compatible
        self.assertTrue(skill_matches_platform({"platforms": []}))


class ValidToolNamesTest(unittest.TestCase):
    def test_empty_tools_yields_empty_set(self):
        agent = _build_agent()
        self.assertEqual(agent.valid_tool_names, set())

    def test_tools_populate_set(self):
        t1 = Tool(name="a", description="a", schema={}, handler=lambda x: "")
        t2 = Tool(name="b", description="b", schema={}, handler=lambda x: "")
        agent = _build_agent(tools=[t1, t2])
        self.assertEqual(agent.valid_tool_names, {"a", "b"})

    def test_attach_memory_manager_merges_tool_names(self):
        agent = _build_agent()
        mgr = MemoryManager()
        mgr.add_provider(
            _StubProviderWithTools(name="external", tool_names=["memory", "recall"])
        )
        agent._attach_memory_manager(mgr)
        self.assertIn("memory", agent.valid_tool_names)
        self.assertIn("recall", agent.valid_tool_names)

    def test_attach_memory_manager_none_is_noop(self):
        agent = _build_agent(tools=[Tool(name="a", description="a", schema={}, handler=lambda x: "")])
        agent._attach_memory_manager(None)
        # Original tool set survives
        self.assertEqual(agent.valid_tool_names, {"a"})
        self.assertIsNone(agent._memory_manager)


class DisabledSkillsTest(unittest.TestCase):
    def test_default_returns_empty_set(self):
        # No skills.disabled config → empty set
        self.assertEqual(get_disabled_skill_names(), set())


if __name__ == "__main__":
    unittest.main()
