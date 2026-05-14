# Copyright (c) 2026 Ubion ax center
"""Phase 1 Unit 10 — OpenAI-compatible API server.

Covers:
    - /health probe (no auth)
    - /v1/models lists Claude variants
    - /v1/chat/completions returns ChatCompletion JSON in non-stream mode
    - /v1/chat/completions streams SSE in stream mode
    - Bearer auth: 401 without token when UBION_API_TOKEN is set
    - Bearer auth: 200 with correct token
    - Empty messages → 400
    - Conversation history is passed through to AIAgent

AIAgent.run_conversation is monkey-patched per test so we don't hit the
real Anthropic API.

Run:
    python -m unittest tests.unit.test_api_server -v
"""

from __future__ import annotations

import json
import os
import unittest
from typing import Any, Dict, List
from unittest.mock import patch

from fastapi.testclient import TestClient

from engine.server.api import create_app


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


class _FakeAgent:
    """Stand-in for AIAgent that the server can construct cheaply.

    The real AIAgent.__init__ validates ANTHROPIC_API_KEY presence — we
    can't paper over that with a mock on run_conversation alone, so we
    replace the whole factory in tests.
    """

    def __init__(self, response_text: str = "hello back"):
        self._response_text = response_text
        self.calls: List[Dict[str, Any]] = []

    def register_default_tools(self) -> None:
        pass

    def run_conversation(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "final_response": self._response_text,
            "exit_reason": "completed",
            "api_calls": 1,
            "tool_calls_made": 0,
            "error": None,
            "task_id": "test-task",
        }


def _patch_factory(response_text: str = "hello back") -> tuple:
    """Patch _agent_factory with a FakeAgent. Returns (patch_ctx, fake)."""
    fake = _FakeAgent(response_text=response_text)
    ctx = patch(
        "engine.server.api._agent_factory",
        lambda model: fake,
    )
    return ctx, fake


class HealthTest(unittest.TestCase):
    def test_health_ok(self):
        client = TestClient(create_app())
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})

    def test_health_no_auth_required(self):
        with _EnvCtx(UBION_API_TOKEN="secret-token"):
            client = TestClient(create_app())
            r = client.get("/health")
            self.assertEqual(r.status_code, 200)


class ModelsTest(unittest.TestCase):
    def test_models_listing(self):
        client = TestClient(create_app())
        r = client.get("/v1/models")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        ids = {m["id"] for m in data["data"]}
        self.assertIn("claude-opus-4-7", ids)
        self.assertEqual(data["object"], "list")


class ChatCompletionsNonStreamTest(unittest.TestCase):
    def test_basic_non_stream(self):
        ctx, _fake = _patch_factory("hello back")
        with _EnvCtx(UBION_API_TOKEN=None):
            with ctx:
                client = TestClient(create_app())
                r = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "claude-opus-4-7",
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["object"], "chat.completion")
        self.assertEqual(body["choices"][0]["message"]["content"], "hello back")
        self.assertEqual(body["choices"][0]["finish_reason"], "stop")
        self.assertTrue(body["id"].startswith("chatcmpl-"))

    def test_empty_messages_returns_400(self):
        with _EnvCtx(UBION_API_TOKEN=None):
            client = TestClient(create_app())
            r = client.post(
                "/v1/chat/completions",
                json={"model": "claude-opus-4-7", "messages": []},
            )
        self.assertEqual(r.status_code, 400)

    def test_conversation_history_forwarded(self):
        ctx, fake = _patch_factory("ok")
        with _EnvCtx(UBION_API_TOKEN=None):
            with ctx:
                client = TestClient(create_app())
                client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "claude-opus-4-7",
                        "messages": [
                            {"role": "system", "content": "you are a poet"},
                            {"role": "user", "content": "old"},
                            {"role": "assistant", "content": "reply"},
                            {"role": "user", "content": "follow up"},
                        ],
                    },
                )
        self.assertEqual(len(fake.calls), 1)
        kw = fake.calls[0]
        # The last user message is the new user_message
        self.assertEqual(kw["user_message"], "follow up")
        hist = kw.get("conversation_history") or []
        roles = [m["role"] for m in hist]
        self.assertEqual(roles, ["user", "assistant"])
        self.assertEqual(hist[0]["content"], "old")
        self.assertEqual(hist[1]["content"], "reply")


class ChatCompletionsStreamTest(unittest.TestCase):
    def test_sse_stream_yields_chunks(self):
        ctx, _fake = _patch_factory("hello streaming world")
        with _EnvCtx(UBION_API_TOKEN=None):
            with ctx:
                client = TestClient(create_app())
                with client.stream(
                    "POST",
                    "/v1/chat/completions",
                    json={
                        "model": "claude-opus-4-7",
                        "stream": True,
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                ) as r:
                    self.assertEqual(r.status_code, 200)
                    self.assertTrue(
                        r.headers["content-type"].startswith("text/event-stream"),
                        msg=r.headers,
                    )
                    body = b"".join(r.iter_bytes()).decode("utf-8")

        # Parse SSE lines
        lines = [ln for ln in body.split("\n") if ln.startswith("data:")]
        self.assertTrue(any(ln.strip() == "data: [DONE]" for ln in lines))
        # Reassemble the streamed content
        reassembled = ""
        for ln in lines:
            payload = ln[len("data:"):].strip()
            if payload == "[DONE]":
                continue
            chunk = json.loads(payload)
            delta = chunk["choices"][0].get("delta", {})
            if "content" in delta:
                reassembled += delta["content"]
        self.assertEqual(reassembled, "hello streaming world")


class BearerAuthTest(unittest.TestCase):
    def test_chat_requires_bearer_when_token_set(self):
        with _EnvCtx(UBION_API_TOKEN="s3cret"):
            client = TestClient(create_app())
            r = client.post(
                "/v1/chat/completions",
                json={"model": "claude-opus-4-7", "messages": [{"role": "user", "content": "hi"}]},
            )
        self.assertEqual(r.status_code, 401)

    def test_chat_accepts_valid_bearer(self):
        ctx, _fake = _patch_factory("authed")
        with _EnvCtx(UBION_API_TOKEN="s3cret"):
            with ctx:
                client = TestClient(create_app())
                r = client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": "Bearer s3cret"},
                    json={"model": "claude-opus-4-7", "messages": [{"role": "user", "content": "hi"}]},
                )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["choices"][0]["message"]["content"], "authed")

    def test_chat_rejects_wrong_bearer(self):
        with _EnvCtx(UBION_API_TOKEN="s3cret"):
            client = TestClient(create_app())
            r = client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer wrong"},
                json={"model": "claude-opus-4-7", "messages": [{"role": "user", "content": "hi"}]},
            )
        self.assertEqual(r.status_code, 401)

    def test_models_endpoint_also_protected(self):
        with _EnvCtx(UBION_API_TOKEN="s3cret"):
            client = TestClient(create_app())
            r = client.get("/v1/models")
            self.assertEqual(r.status_code, 401)
            r2 = client.get(
                "/v1/models",
                headers={"Authorization": "Bearer s3cret"},
            )
            self.assertEqual(r2.status_code, 200)


if __name__ == "__main__":
    unittest.main()
