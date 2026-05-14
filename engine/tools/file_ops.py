# Copyright (c) 2026 Ubion ax center
#
# Inspiration: NousResearch/hermes-agent tools/file_tools.py + file_operations.py
# (MIT). Upstream is 2,600+ lines covering text/binary/image reads, fuzzy
# match patches, atomic snapshots, line-range slicing, image preview,
# Office-format parsing, etc. — far beyond the poet-agent scenario's needs.
#
# This Port covers the minimal trio the Phase 1 poet agent might invoke
# when adding `references/*.md` material under a skill it just created:
#     - read_file(path)
#     - write_file(path, content)
#     - list_files(path)
#
# Writes are confined to the agent home directory via path_security so a
# stray skill instruction can't drop files outside ~/.ubion-agent/. Reads
# are allowed anywhere (typically used to pull in a SOUL.md or user
# template the user pointed at from chat).
"""Phase 1 file operations toolset (read/write/list) with write whitelist."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List as _List

from engine.core.agent import Tool
from engine.storage.agent_home import get_hermes_home, get_workspace
from engine.tools.path_security import has_traversal_component, validate_within_dir
from engine.tools.registry import tool_error, tool_result

logger = logging.getLogger(__name__)


_MAX_READ_BYTES = 200_000  # 200KB cap — enough for SKILL.md / README / SOUL


def _resolve_for_write(raw_path: str) -> Path | str:
    """Return a resolved Path inside the agent home, or an error string.

    Writes inside the agent home are unrestricted (overwrite allowed) —
    this is the agent's own brain (skills, references, scratch). For
    user-facing workspace writes, use :func:`_resolve_for_workspace_create`.
    """
    if not raw_path or not isinstance(raw_path, str):
        return "missing or invalid 'path'"
    if has_traversal_component(raw_path):
        return "path contains '..' traversal — refused"
    root = get_hermes_home()
    candidate = (root / raw_path) if not Path(raw_path).is_absolute() else Path(raw_path)
    err = validate_within_dir(candidate, root)
    if err:
        return err
    return candidate


def _resolve_for_workspace_create(raw_path: str) -> Path | str:
    """Return a resolved Path inside the workspace, but ONLY if it doesn't yet
    exist.

    Workspace policy (사용자 결정 2026-05-14):
        - 새 파일 생산만 허용. 이미 존재하는 경로는 거부.
        - 수정/삭제는 거부 (별도 도구로도 막아야 함).
        - 읽기는 자유 (``read_file`` 은 별도 제한 없음).

    이렇게 분리해 두면 agent_home 안에선 자기진화용 자유로운 read/write
    이 가능하고, 사용자의 workspace 는 "기존 자료는 건드리지 않고 새
    산출물만 추가" 라는 안전한 계약이 코드 레벨에서 강제됩니다.
    """
    if not raw_path or not isinstance(raw_path, str):
        return "missing or invalid 'path'"
    if has_traversal_component(raw_path):
        return "path contains '..' traversal — refused"
    workspace = get_workspace()
    candidate = (workspace / raw_path) if not Path(raw_path).is_absolute() else Path(raw_path)
    err = validate_within_dir(candidate, workspace)
    if err:
        return err
    # Create-only: 이미 존재하면 거부 (디렉터리든 파일이든).
    if candidate.exists():
        return (
            f"workspace path already exists: {candidate}. Workspace writes are "
            "create-only by policy — modifying or overwriting existing files "
            "is refused. Pick a new filename or write under the agent home."
        )
    return candidate


def _resolve_for_read(raw_path: str) -> Path | str:
    """Return a resolved Path for reading (no whitelist)."""
    if not raw_path or not isinstance(raw_path, str):
        return "missing or invalid 'path'"
    try:
        return Path(raw_path).expanduser()
    except Exception as exc:
        return f"invalid path: {exc}"


def read_file(path: str) -> str:
    """Tool handler — return file content as JSON string."""
    resolved = _resolve_for_read(path)
    if isinstance(resolved, str):
        return tool_error(resolved)
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        return tool_error(f"cannot stat {path!r}: {exc}")
    if size > _MAX_READ_BYTES:
        return tool_error(
            f"file too large ({size} bytes > {_MAX_READ_BYTES} cap)",
            size=size,
        )
    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return tool_error(f"cannot read {path!r}: {exc}")
    return tool_result(content=text, path=str(resolved), size=size)


def write_file(path: str, content: str) -> str:
    """Tool handler — write text to a file inside the agent home."""
    resolved = _resolve_for_write(path)
    if isinstance(resolved, str):
        return tool_error(resolved)
    if content is None:
        return tool_error("missing 'content'")
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except OSError as exc:
        return tool_error(f"cannot write {path!r}: {exc}")
    return tool_result(path=str(resolved), bytes_written=len(content.encode("utf-8")))


def create_workspace_file(path: str, content: str, *, binary_b64: bool = False) -> str:
    """Tool handler — create a NEW file under the user's workspace.

    Workspace = ``UBION_WORKSPACE`` (env) → cwd. The path must not already
    exist; overwriting is refused so user-owned files can't be silently
    modified.

    Args:
        path:     Relative (resolved under workspace) or absolute (must be
                  inside workspace) path. The target must NOT exist yet.
        content:  Either text (``binary_b64=False``) or base64-encoded bytes
                  (``binary_b64=True``) — the latter is how the agent
                  produces .xlsx / .pptx / images.
        binary_b64: True to decode ``content`` as base64 and write bytes.
    """
    resolved = _resolve_for_workspace_create(path)
    if isinstance(resolved, str):
        logger.info("create_workspace_file: REFUSED %r — %s", path, resolved)
        return tool_error(resolved)
    if content is None:
        return tool_error("missing 'content'")
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        if binary_b64:
            import base64
            try:
                data = base64.b64decode(content, validate=True)
            except Exception as exc:
                return tool_error(f"content is not valid base64: {exc}")
            resolved.write_bytes(data)
            written = len(data)
        else:
            resolved.write_text(content, encoding="utf-8")
            written = len(content.encode("utf-8"))
    except OSError as exc:
        logger.warning("create_workspace_file: write failed %s: %s", resolved, exc)
        return tool_error(f"cannot create {path!r}: {exc}")
    logger.info(
        "create_workspace_file: CREATED %s (%d bytes%s)",
        resolved, written, ", binary" if binary_b64 else "",
    )
    return tool_result(
        path=str(resolved),
        bytes_written=written,
        binary=binary_b64,
        workspace=str(get_workspace()),
    )


def append_workspace_file(path: str, content: str, *, binary_b64: bool = False) -> str:
    """Append text/bytes to an existing workspace file the agent created
    earlier in this same conversation.

    Why this exists: max_tokens caps each LLM turn at ~16K tokens. A full
    PPTX/HTML/markdown body often blows past that on a single
    ``create_workspace_file`` call, so the JSON arguments arrive truncated
    and the file write silently fails. ``append_file`` lets the model
    seed the file with a small first chunk and then top it up across
    multiple turns — each chunk well under the per-call cap.

    Policy: the target must already exist inside the workspace (i.e.
    created by an earlier ``create_workspace_file``). We do NOT let the
    agent append to arbitrary user-owned files — that would silently
    modify pre-existing content and break the workspace's create-only
    invariant.
    """
    if not path or not isinstance(path, str):
        return tool_error("missing or invalid 'path'")
    if has_traversal_component(path):
        return tool_error("path contains '..' traversal — refused")
    workspace = get_workspace()
    candidate = (workspace / path) if not Path(path).is_absolute() else Path(path)
    err = validate_within_dir(candidate, workspace)
    if err:
        return tool_error(err)
    if not candidate.exists():
        return tool_error(
            f"append target does not exist: {candidate}. Use create_workspace_file "
            "for the first chunk; append_file is only for topping up a file you "
            "already created in this session."
        )
    if not candidate.is_file():
        return tool_error(f"append target is not a regular file: {candidate}")
    if content is None:
        return tool_error("missing 'content'")
    try:
        if binary_b64:
            import base64
            try:
                data = base64.b64decode(content, validate=True)
            except Exception as exc:
                return tool_error(f"content is not valid base64: {exc}")
            with candidate.open("ab") as fp:
                fp.write(data)
            written = len(data)
        else:
            with candidate.open("a", encoding="utf-8") as fp:
                fp.write(content)
            written = len(content.encode("utf-8"))
    except OSError as exc:
        logger.warning("append_workspace_file: write failed %s: %s", candidate, exc)
        return tool_error(f"cannot append to {path!r}: {exc}")
    new_size = candidate.stat().st_size
    logger.info(
        "append_workspace_file: APPENDED %s (+%d bytes, total=%d%s)",
        candidate, written, new_size, ", binary" if binary_b64 else "",
    )
    return tool_result(
        path=str(candidate),
        bytes_appended=written,
        total_size=new_size,
        binary=binary_b64,
    )


def list_files(path: str = ".") -> str:
    """Tool handler — list files in a directory."""
    resolved = _resolve_for_read(path or ".")
    if isinstance(resolved, str):
        return tool_error(resolved)
    if not resolved.exists():
        return tool_error(f"path does not exist: {path!r}")
    if not resolved.is_dir():
        return tool_error(f"not a directory: {path!r}")
    try:
        raw_entries = list(resolved.iterdir())
    except OSError as exc:
        return tool_error(f"cannot list {path!r}: {exc}")
    entries = [
        {
            "name": entry.name,
            "type": "dir" if entry.is_dir() else "file",
            "size": entry.stat().st_size if entry.is_file() else None,
        }
        for entry in sorted(raw_entries, key=lambda p: (not p.is_dir(), p.name.lower()))
    ]
    return tool_result(path=str(resolved), entries=entries)


def build_default_file_tools() -> "list[Tool]":
    """Return Phase 1 file tools as a list of Tool dataclass entries."""
    return [
        Tool(
            name="read_file",
            description=(
                "Read a UTF-8 text file (max 200KB). Use this to pull "
                "external reference material a user pointed at (SOUL.md, "
                "templates, prior drafts)."
            ),
            schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to read. Tilde-expansion supported.",
                    },
                },
                "required": ["path"],
            },
            handler=lambda args: read_file((args or {}).get("path", "")),
        ),
        Tool(
            name="write_file",
            description=(
                "Write text to a file UNDER the agent home directory. "
                "Use this to drop `references/<topic>.md` or other "
                "supporting material alongside skills you create. Writes "
                "outside the agent home are refused."
            ),
            schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Path under the agent home (relative is "
                            "resolved under ~/.ubion-agent/). Absolute "
                            "paths must already be inside the agent home."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "Text to write.",
                    },
                },
                "required": ["path", "content"],
            },
            handler=lambda args: write_file(
                (args or {}).get("path", ""),
                (args or {}).get("content", ""),
            ),
        ),
        Tool(
            name="list_files",
            description="List entries in a directory.",
            schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to list. Defaults to '.'.",
                    },
                },
            },
            handler=lambda args: list_files((args or {}).get("path", ".") or "."),
        ),
        Tool(
            name="create_workspace_file",
            description=(
                "Create a NEW file inside the user's workspace folder "
                "(UBION_WORKSPACE). Overwriting an existing file is REFUSED "
                "by policy — workspace writes are create-only. Use this to "
                "produce .xlsx / .pptx / .docx / images / reports for the "
                "user. Set binary_b64=true to write bytes (content must be "
                "base64-encoded); set false (default) to write UTF-8 text. "
                "For scratch files, references, or skill assets, prefer "
                "write_file (under the agent home, free to overwrite)."
            ),
            schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Path under UBION_WORKSPACE (relative) or an "
                            "absolute path that must be inside it. Must "
                            "not already exist."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "File body. Plain UTF-8 text unless "
                            "binary_b64=true, in which case it's base64-"
                            "encoded bytes."
                        ),
                    },
                    "binary_b64": {
                        "type": "boolean",
                        "description": (
                            "When true, decode `content` from base64 and "
                            "write raw bytes — required for .xlsx, .pptx, "
                            "images, PDFs, etc."
                        ),
                        "default": False,
                    },
                },
                "required": ["path", "content"],
            },
            handler=lambda args: create_workspace_file(
                (args or {}).get("path", ""),
                (args or {}).get("content", ""),
                binary_b64=bool((args or {}).get("binary_b64", False)),
            ),
        ),
        Tool(
            name="append_file",
            description=(
                "Append text or bytes to a workspace file you ALREADY created "
                "in this session with create_workspace_file. Use when a single "
                "create call would exceed the per-response token budget — "
                "seed with create_workspace_file, then top up with one or more "
                "append_file calls. Refuses to create new files (use "
                "create_workspace_file for that) and refuses to touch files "
                "you didn't create (workspace stays create-only by policy). "
                "Set binary_b64=true to append base64-decoded bytes."
            ),
            schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Path of the file to append to. Must already "
                            "exist inside UBION_WORKSPACE."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Text to append, OR base64-encoded bytes when "
                            "binary_b64=true."
                        ),
                    },
                    "binary_b64": {
                        "type": "boolean",
                        "description": (
                            "When true, decode `content` from base64 and "
                            "append raw bytes."
                        ),
                        "default": False,
                    },
                },
                "required": ["path", "content"],
            },
            handler=lambda args: append_workspace_file(
                (args or {}).get("path", ""),
                (args or {}).get("content", ""),
                binary_b64=bool((args or {}).get("binary_b64", False)),
            ),
        ),
    ]
