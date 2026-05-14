# Copyright (c) 2026 Ubion ax center
"""Workspace concept — the user's target directory (cwd / workspace).

Distinct from UBION_AGENT_HOME (agent's persistent brain). Setting
UBION_WORKSPACE points the prompt builder at a different set of
context files (SOUL.md / HERMES.md / AGENTS.md / CLAUDE.md / .cursorrules)
so the same agent can talk about different content folders without
rebuilding its skills or memory.

Run:
    python -m unittest tests.unit.test_workspace -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Dict

from engine.core.agent import AIAgent
from engine.storage.agent_home import get_hermes_home, get_workspace


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


def _build_agent() -> AIAgent:
    return AIAgent(
        model="claude-opus-4-7",
        api_key="sk-test-fake",
        quiet_mode=True,
    )


class GetWorkspaceTest(unittest.TestCase):
    def test_defaults_to_cwd(self):
        with _EnvCtx(UBION_WORKSPACE=None):
            self.assertEqual(get_workspace(), Path.cwd())

    def test_env_var_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_WORKSPACE=tmp):
                self.assertEqual(get_workspace(), Path(tmp))

    def test_empty_env_var_falls_back_to_cwd(self):
        with _EnvCtx(UBION_WORKSPACE="   "):
            # Whitespace-only is treated as unset
            self.assertEqual(get_workspace(), Path.cwd())


class WorkspaceVsAgentHomeTest(unittest.TestCase):
    """Two separate paths, two separate env vars, no cross-contamination."""

    def test_independent_overrides(self):
        with tempfile.TemporaryDirectory() as home:
            with tempfile.TemporaryDirectory() as ws:
                with _EnvCtx(UBION_AGENT_HOME=home, UBION_WORKSPACE=ws):
                    self.assertEqual(get_hermes_home(), Path(home))
                    self.assertEqual(get_workspace(), Path(ws))
                    self.assertNotEqual(get_hermes_home(), get_workspace())


class WorkspaceDrivesProjectContextTest(unittest.TestCase):
    """Setting UBION_WORKSPACE flips which project context (HERMES.md /
    AGENTS.md / CLAUDE.md / .cursorrules) the prompt picks up.

    NOTE: SOUL.md lives in UBION_AGENT_HOME (the agent's identity), NOT
    the workspace. The workspace contributes *project* context — the
    user's working folder — which is exactly what we want to flip
    between sessions.
    """

    def test_agents_md_loaded_from_workspace(self):
        with tempfile.TemporaryDirectory() as ws:
            (Path(ws) / "AGENTS.md").write_text(
                "This workspace holds classical poetry drafts.\n",
                encoding="utf-8",
            )
            with _EnvCtx(UBION_WORKSPACE=ws):
                agent = _build_agent()
                composed = agent._build_system_prompt()
                self.assertIn("classical poetry drafts", composed)

    def test_different_workspace_different_project_context(self):
        # Same agent home, different workspace = different AGENTS.md content
        with tempfile.TemporaryDirectory() as home:
            with tempfile.TemporaryDirectory() as ws_a:
                (Path(ws_a) / "AGENTS.md").write_text(
                    "Classical poetry collection.\n", encoding="utf-8"
                )
                with _EnvCtx(UBION_AGENT_HOME=home, UBION_WORKSPACE=ws_a):
                    a = _build_agent()
                    self.assertIn("Classical poetry", a._build_system_prompt())

            with tempfile.TemporaryDirectory() as ws_b:
                (Path(ws_b) / "AGENTS.md").write_text(
                    "Modern free-verse experiments.\n", encoding="utf-8"
                )
                with _EnvCtx(UBION_AGENT_HOME=home, UBION_WORKSPACE=ws_b):
                    b = _build_agent()
                    self.assertIn("Modern free-verse", b._build_system_prompt())


class WorkspaceMissingStillWorksTest(unittest.TestCase):
    """Invariant: workspace pointing nowhere doesn't crash."""

    def test_nonexistent_workspace_no_crash(self):
        with _EnvCtx(UBION_WORKSPACE="/does/not/exist/anywhere"):
            agent = _build_agent()
            # Should not raise — empty SOUL/HERMES/AGENTS, prompt collapses
            composed = agent._build_system_prompt()
            self.assertIsInstance(composed, str)


if __name__ == "__main__":
    unittest.main()
