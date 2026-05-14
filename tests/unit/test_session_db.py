# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 9 — SessionDB + session_search wiring.

Tests the vendored SessionDB end-to-end (create session → log message →
FTS5 search) plus AIAgent integration:
    - register_default_tools includes session_search by default
    - _ensure_session_db is lazy + idempotent
    - SessionDB respects UBION_AGENT_HOME (multi-tenant isolation)
    - FTS5 query roundtrip on a fresh SessionDB
    - sanitize_fts5_query handles user input safely

Run:
    python -m unittest tests.unit.test_session_db -v
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Dict

from engine.core.agent import AIAgent
from engine.storage.session_db import SessionDB


def _build_agent() -> AIAgent:
    return AIAgent(
        model="claude-opus-4-7",
        api_key="sk-test-fake",
        quiet_mode=True,
    )


import contextlib


@contextlib.contextmanager
def _temp_session_db():
    """Yield a SessionDB whose temp directory survives until the DB closes.

    On Windows, sqlite3 keeps an open handle on state.db until close().
    The naive pattern
        with tempfile.TemporaryDirectory() as tmp:
            db = SessionDB(db_path=Path(tmp) / "state.db")
            ... use db ...
    races: the TemporaryDirectory __exit__ fires before db.close(), so
    rmtree hits WinError 32 (file in use). We invert the lifecycle here
    — yield the db, close it on exit, then drop the directory.
    """
    tmp = tempfile.mkdtemp(prefix="sessiondb_test_")
    db = SessionDB(db_path=Path(tmp) / "state.db")
    try:
        yield db
    finally:
        db.close()
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass


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


class RegisterSessionSearchToolTest(unittest.TestCase):
    def test_session_search_in_default_catalogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                agent = _build_agent()
                agent.register_default_tools()
                self.assertIn("session_search", agent._tools)
                self.assertIn("session_search", agent.valid_tool_names)

    def test_opt_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _EnvCtx(UBION_AGENT_HOME=tmp):
                agent = _build_agent()
                agent.register_default_tools(include_session_search=False)
                self.assertNotIn("session_search", agent._tools)


class EnsureSessionDbTest(unittest.TestCase):
    def test_lazy(self):
        agent = _build_agent()
        self.assertIsNone(agent._session_db)

    def test_idempotent(self):
        # _ensure_session_db reads DEFAULT_DB_PATH at module level —
        # which has already been resolved to ~/.ubion-agent/state.db.
        # That's fine here: we only assert the same DB instance is
        # reused across calls, not the path itself. Close it for
        # cleanup so the next test run doesn't inherit our handle.
        agent = _build_agent()
        db1 = agent._ensure_session_db()
        try:
            db2 = agent._ensure_session_db()
            self.assertIs(db1, db2)
            self.assertIsNotNone(agent._session_db)
        finally:
            db1.close()


class SessionDbIsolationTest(unittest.TestCase):
    """Multi-tenant invariant: UBION_AGENT_HOME per process → DB per user.

    NOTE: engine.storage.session_db freezes DEFAULT_DB_PATH at module
    import time. Real multi-tenant deployment uses a fresh process per
    user (Phase 3 containerisation), so a single-process test must pass
    an explicit `db_path` to SessionDB to simulate two homes.
    """

    def test_db_path_follows_explicit_argument(self):
        with _temp_session_db() as alice_db:
            with _temp_session_db() as bob_db:
                self.assertNotEqual(alice_db.db_path, bob_db.db_path)
                self.assertTrue(alice_db.db_path.exists())
                self.assertTrue(bob_db.db_path.exists())


class Fts5SanitiseTest(unittest.TestCase):
    """The sanitise helper protects against malformed FTS5 input."""

    def test_strips_unmatched_quotes(self):
        with _temp_session_db() as db:
            cleaned = db._sanitize_fts5_query('hello " world')
            self.assertNotEqual(cleaned.count('"') % 2, 1,
                                msg=f"got: {cleaned!r}")

    def test_empty_input(self):
        with _temp_session_db() as db:
            self.assertEqual(db._sanitize_fts5_query(""), "")


class Fts5RoundtripTest(unittest.TestCase):
    """End-to-end smoke: create session, append a message, search for it."""

    def test_search_finds_logged_message(self):
        with _temp_session_db() as db:
            db.create_session(
                session_id="20260513_test_001",
                source="cli",
                model="claude-opus-4-7",
            )
            db.append_message(
                session_id="20260513_test_001",
                role="user",
                content="The poet writes about pomegranates and rain.",
            )
            results = db.search_messages("pomegranates", limit=5)
            self.assertTrue(len(results) >= 1, msg=f"results: {results}")
            hit_sessions = {r.get("session_id") for r in results}
            self.assertIn("20260513_test_001", hit_sessions)

    def test_search_returns_empty_on_miss(self):
        with _temp_session_db() as db:
            results = db.search_messages("nothing-was-ever-logged", limit=5)
            self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
