# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 8 — tool system: skill_view + skill_manage + file ops.

Covers:
    - AIAgent.register_default_tools() registers 5 tools (idempotent)
    - skill_view returns 'not found' on empty home (graceful)
    - skill_manage create writes a real SKILL.md under a temp home
    - read_file reads back what write_file wrote (round-trip)
    - write_file refuses paths outside the agent home
    - write_file refuses '..' traversal
    - list_files returns a sorted directory listing

Run:
    python -m unittest tests.unit.test_tools_unit8 -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Dict

from engine.core.agent import AIAgent


def _build_agent() -> AIAgent:
    return AIAgent(
        model="claude-opus-4-7",
        api_key="sk-test-fake",
        quiet_mode=True,
    )


class _EnvCtx:
    def __init__(self, **kwargs):
        self.overrides = kwargs
        self.original: Dict[str, str | None] = {}

    def __enter__(self):
        for k, v in self.overrides.items():
            self.original[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *args):
        for k, prev in self.original.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


class RegisterDefaultToolsTest(unittest.TestCase):
    def test_registers_full_phase1_catalogue(self):
        agent = _build_agent()
        agent.register_default_tools()
        names = set(agent._tools.keys())
        expected = {
            "skill_view", "skill_manage",
            "read_file", "write_file", "list_files",
            "session_search",
        }
        self.assertEqual(expected, names)
        self.assertEqual(agent.valid_tool_names, expected)

    def test_idempotent(self):
        agent = _build_agent()
        agent.register_default_tools()
        first = set(agent._tools.keys())
        agent.register_default_tools()
        agent.register_default_tools()
        self.assertEqual(set(agent._tools.keys()), first)

    def test_skill_only(self):
        agent = _build_agent()
        agent.register_default_tools(
            include_file_ops=False,
            include_session_search=False,
        )
        self.assertEqual(set(agent._tools.keys()), {"skill_view", "skill_manage"})


class SkillViewGracefulTest(unittest.TestCase):
    def test_returns_not_found_on_empty_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                agent = _build_agent()
                agent.register_default_tools(include_file_ops=False)
                tool = agent._tools["skill_view"]
                raw = tool.handler({"name": "anything"})
                data = json.loads(raw)
                self.assertFalse(data["success"])
                self.assertIn("not found", data["error"])


class SkillManageCreateTest(unittest.TestCase):
    def test_create_writes_skill_md(self):
        # NOTE: engine.skills.manager freezes its SKILLS_DIR constant at
        # module import time. To exercise this test in a temp directory we
        # have to patch that constant as well as UBION_AGENT_HOME.
        import engine.skills.manager as _mgr
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                original_hermes_home = _mgr.HERMES_HOME
                original_skills_dir = _mgr.SKILLS_DIR
                _mgr.HERMES_HOME = Path(tmp)
                _mgr.SKILLS_DIR = Path(tmp) / "skills"
                try:
                    agent = _build_agent()
                    agent.register_default_tools(include_file_ops=False)
                    tool = agent._tools["skill_manage"]
                    payload = {
                        "action": "create",
                        "name": "test-skill",
                        "content": (
                            "---\nname: test-skill\ndescription: a test skill\n---\n\n"
                            "# Test skill body\n\n## Step 1\nDo something useful.\n"
                        ),
                    }
                    raw = tool.handler(payload)
                    data = raw if isinstance(raw, dict) else json.loads(raw)
                    self.assertTrue(data.get("success"), msg=data)
                    skill_md = Path(tmp) / "skills" / "test-skill" / "SKILL.md"
                    self.assertTrue(skill_md.exists())
                    self.assertIn(
                        "Test skill body", skill_md.read_text(encoding="utf-8"),
                    )
                finally:
                    _mgr.HERMES_HOME = original_hermes_home
                    _mgr.SKILLS_DIR = original_skills_dir


class FileOpsRoundtripTest(unittest.TestCase):
    def test_write_then_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                agent = _build_agent()
                agent.register_default_tools()
                # Write under the agent home
                wr = agent._tools["write_file"].handler(
                    {"path": "memo.txt", "content": "hello"}
                )
                wr_data = json.loads(wr)
                self.assertNotIn("error", wr_data)
                # Read it back
                rd = agent._tools["read_file"].handler(
                    {"path": wr_data["path"]}
                )
                rd_data = json.loads(rd)
                self.assertEqual(rd_data.get("content"), "hello")


class FileOpsSecurityTest(unittest.TestCase):
    def test_write_outside_agent_home_refused(self):
        with tempfile.TemporaryDirectory() as agent_home:
            with tempfile.TemporaryDirectory() as outside:
                with _EnvCtx(UBION_AGENT_HOME=agent_home):
                    agent = _build_agent()
                    agent.register_default_tools()
                    out_path = str(Path(outside) / "leaked.txt")
                    raw = agent._tools["write_file"].handler(
                        {"path": out_path, "content": "x"}
                    )
                    data = json.loads(raw)
                    self.assertIn("error", data)
                    self.assertIn("escapes", data["error"])
                    # And the file MUST NOT exist
                    self.assertFalse(Path(out_path).exists())

    def test_write_traversal_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                agent = _build_agent()
                agent.register_default_tools()
                raw = agent._tools["write_file"].handler(
                    {"path": "../escape.txt", "content": "x"}
                )
                data = json.loads(raw)
                self.assertIn("error", data)
                self.assertIn("traversal", data["error"])


class ListFilesTest(unittest.TestCase):
    def test_list_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                agent = _build_agent()
                agent.register_default_tools()
                # Drop two files
                (Path(tmp) / "z.txt").write_text("z", encoding="utf-8")
                (Path(tmp) / "a.txt").write_text("a", encoding="utf-8")
                (Path(tmp) / "subdir").mkdir()
                raw = agent._tools["list_files"].handler({"path": tmp})
                data = json.loads(raw)
                names = [e["name"] for e in data["entries"]]
                # Directories sort first, then files alphabetically
                self.assertEqual(names[0], "subdir")
                self.assertIn("a.txt", names)
                self.assertIn("z.txt", names)
                # File entries report size; dir entries report None
                for e in data["entries"]:
                    if e["type"] == "dir":
                        self.assertIsNone(e["size"])
                    else:
                        self.assertIsInstance(e["size"], int)


if __name__ == "__main__":
    unittest.main()
