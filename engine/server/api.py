# Copyright (c) 2026 Ubion ax center
#
# Inspiration: NousResearch/hermes-agent OpenAI-compatible API surface
# (MIT). This is NOT a Vendor copy — we re-author the FastAPI surface
# from scratch with our AIAgent as the backend. Phase 1 Reference unit.
"""OpenAI-compatible HTTP server.

Endpoints:
    POST /v1/chat/completions  — Anthropic-backed chat completion
    GET  /v1/models            — list of available models
    GET  /health               — liveness probe

Auth: `Authorization: Bearer <token>` matched against UBION_API_TOKEN.
When the env var is empty, auth is disabled (Phase 1 local-only default).

Streaming: pass `stream: true` in the request body to receive Server-Sent
Events (`text/event-stream`) with chunked deltas. Non-streaming returns
the full ChatCompletion JSON in one response.

Concurrency: one AIAgent instance is built per request. Phase 2 will add
a LRU cache keyed by session_id once the gateway pattern is needed; for
Phase 1 (poet-agent CLI) the per-request cost (~50 ms object construction)
is acceptable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import string
import sys
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from engine.core.agent import AIAgent
from engine.storage.agent_home import get_workspace, set_workspace

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Request / response schemas (OpenAI-compatible subset)
# ----------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: str | List[Dict[str, Any]] | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "deepseek-v4-flash"
    messages: List[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    # Pass-through fields we accept but don't yet wire up — keeps callers
    # happy when they use richer OpenAI SDK clients.
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    top_p: Optional[float] = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "ubion"


class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


class FsEntry(BaseModel):
    name: str
    path: str
    is_dir: bool


class FsListResponse(BaseModel):
    path: str
    parent: Optional[str]
    entries: List[FsEntry]
    roots: List[str]


class WorkspaceResponse(BaseModel):
    workspace: str


class WorkspaceUpdateRequest(BaseModel):
    path: str


class SkillBundleInfo(BaseModel):
    version: str
    skill_count: int
    available: bool


class ConversationMetaModel(BaseModel):
    id: str
    title: str
    created: str
    updated: str
    model: str = ""


class ConversationListResponse(BaseModel):
    conversations: List[ConversationMetaModel]


class ConversationTurnModel(BaseModel):
    role: str
    content: str
    timestamp: str = ""


class ConversationDetail(BaseModel):
    meta: ConversationMetaModel
    turns: List[ConversationTurnModel]


class ConversationSaveRequest(BaseModel):
    id: Optional[str] = None
    model: str = ""
    created: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)


# ----------------------------------------------------------------------
# Auth
# ----------------------------------------------------------------------


def _expected_token() -> str:
    """Resolve the bearer token. Empty string disables auth (default)."""
    return (os.environ.get("UBION_API_TOKEN") or "").strip()


async def _require_bearer(request: Request) -> None:
    """Dependency that enforces Bearer auth when UBION_API_TOKEN is set."""
    expected = _expected_token()
    if not expected:
        return  # Auth disabled
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    supplied = header.split(" ", 1)[1].strip()
    if supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


# ----------------------------------------------------------------------
# Helpers — OpenAI shape adapters
# ----------------------------------------------------------------------


def _to_user_message(messages: List[ChatMessage]) -> str:
    """Collapse the last user turn into a plain string for AIAgent.

    AIAgent.run_conversation() takes a single user_message and an
    optional conversation_history. We split the request's messages list
    accordingly — preceding user/assistant turns become the history.
    """
    for msg in reversed(messages):
        if msg.role == "user":
            return _flatten_content(msg.content)
    return ""


def _to_conversation_history(messages: List[ChatMessage]) -> List[Dict[str, Any]]:
    """Build the conversation_history list AIAgent expects.

    Skips the trailing user message (it's the new turn) and any system
    messages (AIAgent reads its system prompt from prompt_builder).
    """
    history: List[Dict[str, Any]] = []
    last_user_seen = False
    # Walk from the end backwards so we can drop only the LAST user turn.
    for msg in reversed(messages):
        if msg.role == "user" and not last_user_seen:
            last_user_seen = True
            continue
        if msg.role == "system":
            continue
        history.append({"role": msg.role, "content": _flatten_content(msg.content)})
    history.reverse()
    return history


def _flatten_content(content: Any) -> str:
    """Coerce OpenAI content (str or list-of-parts) to a flat string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    return ""


def _agent_factory(model: str) -> AIAgent:
    """Build a fresh AIAgent for one request.

    Future caching: hash the (api_key, model, system_prompt, tools) tuple
    and cache for ~60 s so back-to-back turns reuse the same agent. Not
    needed for Phase 1 single-user testing.
    """
    agent = AIAgent(
        model=model or "deepseek-v4-flash",
        quiet_mode=True,
    )
    agent.register_default_tools()
    return agent


# ----------------------------------------------------------------------
# Streaming
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# Filesystem browser (workspace picker)
# ----------------------------------------------------------------------


def _windows_drive_roots() -> List[str]:
    """Return existing Windows drives (C:\\, D:\\, ...) for the picker root."""
    roots: List[str] = []
    if sys.platform != "win32":
        return roots
    for letter in string.ascii_uppercase:
        candidate = f"{letter}:\\"
        if Path(candidate).exists():
            roots.append(candidate)
    return roots


def _resolve_browse_path(raw: Optional[str]) -> Path:
    """Resolve a browse target. Empty/None => home directory."""
    if not raw:
        # Default landing: user home (most users want to pick something nearby)
        return Path.home().resolve()
    candidate = Path(raw).expanduser()
    try:
        return candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=404, detail=f"Path not found: {raw}") from exc


def _list_directory(target: Path) -> List[FsEntry]:
    """List immediate children of `target`, directories first, alpha-sorted.

    Files are included too (so the user can confirm they picked the right
    place) but only directories are *selectable* on the frontend.
    """
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {target}")
    entries: List[FsEntry] = []
    try:
        children = sorted(
            target.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    for child in children:
        # Skip hidden entries on POSIX; on Windows the FILE_ATTRIBUTE_HIDDEN
        # check is more involved — keep all entries there and let the user
        # judge.
        if sys.platform != "win32" and child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        entries.append(FsEntry(name=child.name, path=str(child), is_dir=is_dir))
    return entries


def _sse_chunk(data: Dict[str, Any]) -> str:
    """Format one Server-Sent Event payload line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_with_progress(
    *,
    agent: Any,
    user_message: str,
    history: List[Dict[str, Any]],
    request_id: str,
    model: str,
) -> AsyncGenerator[str, None]:
    """Stream real AIAgent progress events as SSE.

    The agent loop runs in a worker thread; its ``progress_callback``
    pushes events onto an ``asyncio.Queue``. We drain the queue here,
    convert each event into the OpenAI-compatible chunk shape (so the
    web client's existing SSE parser keeps working), and finally emit
    the assistant's full text once the loop finishes.

    Event → SSE chunk shape:

        * ``llm_call_started``   → progress chunk with ``stage: "thinking"``
        * ``tool_call_started``  → progress chunk with ``stage: "tool"``,
                                   ``tool_name``
        * ``tool_call_finished`` → progress chunk with ``stage: "tool_done"``
        * ``final_text``         → real content delta (sliced)
        * ``done``               → ``finish_reason`` + ``[DONE]``

    All progress chunks carry an ``ubion`` namespaced object so OpenAI-
    only clients ignore them and only see the final text deltas.
    """
    created = int(time.time())
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _on_event(event_type: str, payload: Dict[str, Any]) -> None:
        # AIAgent runs on a worker thread, so we have to hop back onto
        # the event loop to safely enqueue.
        loop.call_soon_threadsafe(queue.put_nowait, (event_type, payload))

    # Kick the agent off on a worker thread; we don't await this — the
    # result still lands via the `done` event.
    fut = asyncio.create_task(
        asyncio.to_thread(
            agent.run_conversation,
            user_message=user_message,
            conversation_history=history or None,
            progress_callback=_on_event,
        )
    )

    # Initial role chunk so the client knows the assistant turn started.
    yield _sse_chunk({
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": ""},
            "finish_reason": None,
        }],
    })

    final_text = ""
    finish_reason = "stop"
    while True:
        event_type, payload = await queue.get()

        if event_type == "final_text":
            final_text = payload.get("text", "") or ""
            chunk_size = 50
            for i in range(0, len(final_text), chunk_size):
                yield _sse_chunk({
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": final_text[i:i + chunk_size]},
                        "finish_reason": None,
                    }],
                })
                await asyncio.sleep(0)
            continue

        if event_type == "done":
            if payload.get("exit_reason") not in (None, "completed"):
                finish_reason = "length"
            break

        # Progress (thinking / tool) — carried in a side-channel object
        # so OpenAI-only clients can ignore it.
        stage_map = {
            "llm_call_started":   "thinking",
            "tool_call_started":  "tool",
            "tool_call_finished": "tool_done",
        }
        stage = stage_map.get(event_type)
        if stage is None:
            continue
        yield _sse_chunk({
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": None,
            }],
            "ubion": {
                "stage": stage,
                "tool_name": payload.get("name"),
                "ok": payload.get("ok"),
                "turn": payload.get("turn"),
            },
        })

    # Make sure the worker future finishes (cleans up the thread).
    try:
        await fut
    except Exception:
        # Errors are already surfaced via the `done` event's payload.
        pass

    yield _sse_chunk({
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": finish_reason,
        }],
    })
    yield "data: [DONE]\n\n"


async def _stream_chat_completion(
    request_id: str,
    model: str,
    text: str,
) -> AsyncGenerator[str, None]:
    """Stream a completed response as SSE deltas.

    AIAgent runs synchronously — we already have the full text by the
    time streaming starts. We chunk it into ~50 char pieces so OpenAI
    clients see incremental deltas (real token-by-token streaming lands
    when we wire AnthropicClient.chat to its native streaming API in
    Phase 2 or a future sub-unit).
    """
    created = int(time.time())

    # Initial chunk with role
    yield _sse_chunk({
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": ""},
            "finish_reason": None,
        }],
    })

    chunk_size = 50
    for i in range(0, len(text), chunk_size):
        piece = text[i:i + chunk_size]
        yield _sse_chunk({
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": piece},
                "finish_reason": None,
            }],
        })
        # Yield to the event loop so clients see one chunk at a time.
        await asyncio.sleep(0)

    # Final chunk with finish_reason
    yield _sse_chunk({
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop",
        }],
    })
    yield "data: [DONE]\n\n"


# ----------------------------------------------------------------------
# FastAPI app
# ----------------------------------------------------------------------


def _install_idle_shutdown(app: FastAPI) -> None:
    """Wire the idle-shutdown middleware + background watcher onto an app.

    Skipped entirely when `UBION_IDLE_TIMEOUT_S=0` so unit tests and the
    pre-Tauri dev flow stay deterministic.
    """
    timeout = int(os.environ.get("UBION_IDLE_TIMEOUT_S", "1800") or 0)
    if timeout <= 0:
        return

    state = {"last": time.monotonic()}
    # `/health` deliberately *does not* count — the Tauri supervisor uses
    # it as a liveness probe and would otherwise keep the server alive
    # forever even when the user is gone.
    skip_paths = {"/health"}

    @app.middleware("http")
    async def _bump_idle(request: Request, call_next):
        if request.url.path not in skip_paths:
            state["last"] = time.monotonic()
        return await call_next(request)

    def _watchdog() -> None:
        import logging as _logging
        log = _logging.getLogger("engine.server.idle")
        # Sleep in shorter chunks so the daemon thread doesn't delay
        # interpreter shutdown by an arbitrary amount.
        check_interval = min(30, max(5, timeout // 10))
        while True:
            __import__("time").sleep(check_interval)
            idle = time.monotonic() - state["last"]
            if idle >= timeout:
                log.info(
                    "idle for %.0fs (>= %.0fs threshold) — exiting so the "
                    "Tauri supervisor can reclaim the process",
                    idle, timeout,
                )
                # Hard exit. uvicorn's graceful shutdown is overkill here
                # because we want the OS to release the port + memory
                # immediately. Subsequent user activity triggers a fresh
                # spawn via the supervisor.
                os._exit(0)

    t = __import__("threading").Thread(target=_watchdog, name="ubion-idle-watchdog", daemon=True)
    t.start()


def create_app() -> FastAPI:
    """Build the FastAPI application.

    Exposed as a factory so callers can mount additional middleware
    (CORS, logging, auth providers) before running.
    """
    app = FastAPI(title="Ubion Agent API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Idle shutdown — PROJECT_SPEC §2.7 (Phase 3 NFR: 사용자가 안 쓰면
    # Python 알맹이가 메모리를 내놓아야 함). Every non-health request
    # bumps a counter, a daemon thread polls every 30 s, and if more
    # than `UBION_IDLE_TIMEOUT_S` (default 1800 = 30 min) has elapsed
    # since the last bump we self-terminate. The Tauri supervisor will
    # see the dead child on its next poll and respawn on demand.
    _install_idle_shutdown(app)

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/ubion/debug/info")
    async def debug_info(_: None = Depends(_require_bearer)) -> Dict[str, Any]:
        """Surface enough state for the Debug drawer to help a user
        (or developer) understand *why* something went wrong: which keys
        are loaded, where logs live, current backend version + agent home.
        Secrets are never echoed back — only their presence.
        """
        from engine.storage.agent_home import get_hermes_home, get_workspace
        home = get_hermes_home()
        return {
            "agent_home": str(home),
            "workspace": str(get_workspace()),
            "log_file": str(home / "logs" / "server.log"),
            "soul_md_exists": (home / "SOUL.md").exists(),
            "user_md_exists": (home / "USER.md").exists(),
            "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "deepseek_key_set": bool(os.environ.get("DEEPSEEK_API_KEY")),
            "idle_timeout_s": int(os.environ.get("UBION_IDLE_TIMEOUT_S", "1800") or 0),
        }

    @app.get("/v1/ubion/debug/log")
    async def debug_log(
        tail: int = 200,
        _: None = Depends(_require_bearer),
    ) -> Dict[str, Any]:
        """Return the last ``tail`` lines of the rotating server log so
        the Debug drawer can show them without the user shelling out to
        find ``%LOCALAPPDATA%\\.ubion-agent\\logs\\server.log``."""
        from engine.storage.agent_home import get_hermes_home
        log_path = get_hermes_home() / "logs" / "server.log"
        if not log_path.exists():
            return {"path": str(log_path), "lines": []}
        try:
            with log_path.open(encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        n = max(1, min(int(tail) or 200, 2000))
        return {
            "path": str(log_path),
            "lines": [line.rstrip("\n") for line in lines[-n:]],
        }

    @app.get("/v1/ubion/fs/list", response_model=FsListResponse)
    async def fs_list(
        path: Optional[str] = None,
        _: None = Depends(_require_bearer),
    ) -> FsListResponse:
        """Browse the server-side filesystem for the workspace picker.

        - `path` omitted → lands on the user's home directory.
        - On Windows, `roots` is populated with all available drive letters
          so the picker can offer a top-level "C:\\, D:\\, ..." breadcrumb.
        - Only existing absolute paths are returned; relative input is
          expanded relative to home.
        """
        target = _resolve_browse_path(path)
        parent = str(target.parent) if target.parent != target else None
        return FsListResponse(
            path=str(target),
            parent=parent,
            entries=_list_directory(target),
            roots=_windows_drive_roots(),
        )

    @app.get("/v1/ubion/workspace", response_model=WorkspaceResponse)
    async def get_workspace_endpoint(
        _: None = Depends(_require_bearer),
    ) -> WorkspaceResponse:
        """Return the currently resolved UBION_WORKSPACE (env var or cwd).

        UI uses this so the picker opens *near* the user's actual context
        instead of always defaulting to the home folder.
        """
        return WorkspaceResponse(workspace=str(get_workspace()))

    @app.post("/v1/ubion/workspace", response_model=WorkspaceResponse)
    async def set_workspace_endpoint(
        body: WorkspaceUpdateRequest,
        _: None = Depends(_require_bearer),
    ) -> WorkspaceResponse:
        """Persist a new workspace folder.

        Writes UBION_WORKSPACE into ``agent_home/.env`` AND updates
        ``os.environ`` so the change applies immediately to the next
        chat turn without restarting the server. Returns the resolved
        path the agent will use.

        Errors:
          * 400 — path empty / not absolute / not creatable
        """
        try:
            resolved = set_workspace(body.path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"could not create workspace: {exc}")
        logger.info("workspace updated to %s", resolved)
        return WorkspaceResponse(workspace=str(resolved))

    @app.get("/v1/ubion/skills/bundle/info", response_model=SkillBundleInfo)
    async def skills_bundle_info(
        _: None = Depends(_require_bearer),
    ) -> SkillBundleInfo:
        """Return metadata for the bundled skill set (Phase 3 coordinator API).

        Phase 1: served by the same FastAPI process as the agent. Phase 3:
        moves to the central coordinator server — the Tauri tray app polls
        this on first launch + on `If-None-Match` updates to know whether
        to re-download the bundle. ETag is the version string.
        """
        from engine.storage.agent_home import (
            _BUNDLED_SKILLS_VERSION,
            get_bundled_skills_dir,
        )
        src = get_bundled_skills_dir()
        count = 0
        if src is not None and src.is_dir():
            count = sum(1 for _ in src.rglob("SKILL.md"))
        return SkillBundleInfo(
            version=_BUNDLED_SKILLS_VERSION,
            skill_count=count,
            available=count > 0,
        )

    @app.get("/v1/ubion/skills/bundle")
    async def skills_bundle_download(
        request: Request,
        _: None = Depends(_require_bearer),
    ):
        """Stream the bundled skills as a tar.gz, ETag-aware.

        - 200 + ``application/gzip`` body when bundle exists
        - 304 ``Not Modified`` when client supplies a matching ``If-None-Match``
        - 503 when no bundle source is available on this host

        Tray apps cache the tar.gz under ``~/.ubion-agent/.skill-cache/`` and
        extract it on first run. Subsequent boots compare ETag and skip the
        download if unchanged. Phase 3 coordinator implements the same
        contract behind authenticated SSO.
        """
        from engine.storage.agent_home import (
            _BUNDLED_SKILLS_VERSION,
            get_bundled_skills_dir,
        )
        src = get_bundled_skills_dir()
        if src is None or not src.is_dir():
            raise HTTPException(status_code=503, detail="no skill bundle available")

        etag = f'"{_BUNDLED_SKILLS_VERSION}"'
        client_etag = request.headers.get("if-none-match", "").strip()
        if client_etag and client_etag == etag:
            # Quick path — client already has this version.
            from fastapi import Response
            return Response(status_code=304, headers={"ETag": etag})

        # Stream a tar.gz instead of zip — same files, half the size on
        # text-heavy markdown bundles, native to every OS.
        import io
        import tarfile

        def _build_tar_bytes() -> bytes:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                tar.add(src, arcname="skills-bundle")
            return buf.getvalue()

        data = await asyncio.to_thread(_build_tar_bytes)
        return StreamingResponse(
            iter([data]),
            media_type="application/gzip",
            headers={
                "ETag": etag,
                "Content-Disposition": "attachment; filename=skills-bundle.tar.gz",
                "X-Ubion-Skill-Count": str(sum(1 for _ in src.rglob("SKILL.md"))),
            },
        )

    @app.get("/v1/models", response_model=ModelsResponse)
    async def list_models(_: None = Depends(_require_bearer)) -> ModelsResponse:
        return ModelsResponse(data=[
            ModelInfo(id="deepseek-v4-flash"),
            ModelInfo(id="deepseek-v4-pro"),
            ModelInfo(id="claude-opus-4-7"),
            ModelInfo(id="claude-sonnet-4-6"),
            ModelInfo(id="claude-haiku-4-5-20251001"),
        ])

    @app.post("/v1/chat/completions")
    async def chat_completions(
        req: ChatCompletionRequest,
        _: None = Depends(_require_bearer),
    ):
        if not req.messages:
            raise HTTPException(status_code=400, detail="messages must be non-empty")

        user_message = _to_user_message(req.messages)
        history = _to_conversation_history(req.messages)
        agent = _agent_factory(req.model)
        request_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

        if req.stream:
            return StreamingResponse(
                _stream_with_progress(
                    agent=agent,
                    user_message=user_message,
                    history=history,
                    request_id=request_id,
                    model=req.model,
                ),
                media_type="text/event-stream",
            )

        # Non-streaming: just run synchronously and return the full result.
        result = await asyncio.to_thread(
            agent.run_conversation,
            user_message=user_message,
            conversation_history=history or None,
        )
        text = result.get("final_response", "") or ""
        return ChatCompletionResponse(
            id=request_id,
            created=int(time.time()),
            model=req.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=text),
                    finish_reason="stop" if result.get("exit_reason") == "completed" else "length",
                ),
            ],
        )

    # ------------------------------------------------------------------
    # Conversations (markdown-backed history)
    # ------------------------------------------------------------------

    @app.get("/v1/ubion/conversations", response_model=ConversationListResponse)
    async def conversations_list(
        _: None = Depends(_require_bearer),
    ) -> ConversationListResponse:
        from engine.storage.conversations import list_conversations
        metas = list_conversations()
        return ConversationListResponse(
            conversations=[ConversationMetaModel(**vars(m)) for m in metas]
        )

    @app.get("/v1/ubion/conversations/{conv_id}", response_model=ConversationDetail)
    async def conversations_get(
        conv_id: str,
        _: None = Depends(_require_bearer),
    ) -> ConversationDetail:
        from engine.storage.conversations import load_conversation
        try:
            conv = load_conversation(conv_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ConversationDetail(
            meta=ConversationMetaModel(**vars(conv.meta)),
            turns=[ConversationTurnModel(**vars(t)) for t in conv.turns],
        )

    @app.post("/v1/ubion/conversations", response_model=ConversationMetaModel)
    async def conversations_save(
        req: ConversationSaveRequest,
        _: None = Depends(_require_bearer),
    ) -> ConversationMetaModel:
        from engine.storage.conversations import (
            save_conversation,
            turns_from_api_messages,
        )
        raw_messages = [m.model_dump() for m in req.messages]
        turns = turns_from_api_messages(raw_messages)
        if not turns:
            raise HTTPException(status_code=400, detail="No persistable turns")
        try:
            meta = save_conversation(
                conv_id=req.id,
                turns=turns,
                model=req.model,
                created=req.created,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ConversationMetaModel(**vars(meta))

    @app.delete("/v1/ubion/conversations/{conv_id}")
    async def conversations_delete(
        conv_id: str,
        _: None = Depends(_require_bearer),
    ) -> Dict[str, bool]:
        from engine.storage.conversations import delete_conversation
        try:
            ok = delete_conversation(conv_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not ok:
            raise HTTPException(status_code=404, detail="conversation not found")
        return {"deleted": True}

    return app


app = create_app()
