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


def patch_file(
    path: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
) -> str:
    """Tool handler — replace ``old_string`` with ``new_string`` in a file.

    Why this exists: Hermes' patch tool routed through a sandbox shell
    backend (``tools.terminal_tool``) we never vendored, so every call
    died at import time. Six consecutive failures in one session told
    us the model couldn't tell the tool was structurally dead — it
    just kept retrying. This native rewrite is ~50 lines, no shell,
    and matches the workspace policy expected by the rest of file_ops.

    Matching:
      - Exact byte match first (Anthropic's contract for "old_string").
      - If no exact match, try whitespace-tolerant match
        (collapse all whitespace runs to a single space) — common
        failure mode is the model paraphrasing indentation/newlines.
      - Still no match → return error WITH the closest candidate
        line from difflib so the model can re-target instead of
        retrying the same broken anchor.

    Policy:
      - Path must already exist (creation is for write_file /
        create_workspace_file).
      - Writes inside workspace are REFUSED — workspace stays
        create-only by user policy. Use this tool to edit files
        under agent_home (scripts, references, scratch).
      - Reads (the pre-patch read) are allowed anywhere so the
        model can patch files that live elsewhere if the caller
        explicitly placed them outside both roots — but the write
        only goes back if the file is inside agent_home.
    """
    if not path or not isinstance(path, str):
        return tool_error("missing or invalid 'path'")
    if has_traversal_component(path):
        return tool_error("path contains '..' traversal — refused")
    if old_string is None or new_string is None:
        return tool_error("both 'old_string' and 'new_string' are required")
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = (get_hermes_home() / path).resolve()
    if not target.exists():
        return tool_error(f"path does not exist: {target}")
    if not target.is_file():
        return tool_error(f"not a regular file: {target}")
    workspace = get_workspace()
    try:
        target_resolved = target.resolve()
        workspace_resolved = workspace.resolve()
    except OSError as exc:
        return tool_error(f"cannot resolve paths: {exc}")
    try:
        target_resolved.relative_to(workspace_resolved)
        in_workspace = True
    except ValueError:
        in_workspace = False
    if in_workspace:
        return tool_error(
            f"refusing to patch workspace file {target}. Workspace is "
            "create-only by policy — make a new file with "
            "create_workspace_file instead of modifying existing ones."
        )
    try:
        original = target.read_text(encoding="utf-8")
    except OSError as exc:
        return tool_error(f"cannot read {target}: {exc}")
    # ── Pass 1: exact match ──────────────────────────────────────
    exact_count = original.count(old_string)
    if exact_count > 0:
        if exact_count > 1 and not replace_all:
            return tool_error(
                f"old_string matched {exact_count} times in {target}; "
                "either pass replace_all=true or give a longer/more "
                "unique anchor."
            )
        new_content = (
            original.replace(old_string, new_string)
            if replace_all
            else original.replace(old_string, new_string, 1)
        )
        match_mode = "exact"
        match_count = exact_count if replace_all else 1
    else:
        # ── Pass 2: line-aligned whitespace-tolerant match ─────────
        # Model paraphrasing usually hits indentation / trailing
        # whitespace within a line, not across newlines. Match
        # line-by-line so we never merge two distinct lines into
        # one window (the bug a naive \\s+ collapse hits, which
        # silently fuses ``alpha\\nbeta`` into ``alpha beta``).
        import re as _re
        inline_ws = _re.compile(r"[ \t]+")
        def _norm_line(s: str) -> str:
            return inline_ws.sub(" ", s).strip()
        old_lines = old_string.splitlines()
        # Drop trailing blank lines from the anchor so a missing
        # final newline doesn't ruin the match. Keep internal
        # blank lines — they're meaningful structure.
        while old_lines and not old_lines[-1].strip():
            old_lines.pop()
        if not old_lines:
            return tool_error(
                f"old_string contains only whitespace — provide a "
                "non-empty anchor."
            )
        norm_anchor = [_norm_line(ln) for ln in old_lines]
        # Walk original line-by-line. ``splitlines(keepends=True)``
        # preserves the newline characters so byte spans are
        # exact for re-assembly.
        original_lines = original.splitlines(keepends=True)
        positions: list[tuple[int, int]] = []
        offsets: list[int] = [0]
        for ln in original_lines:
            offsets.append(offsets[-1] + len(ln))
        i = 0
        while i <= len(original_lines) - len(norm_anchor):
            window = [_norm_line(original_lines[i + j]) for j in range(len(norm_anchor))]
            if window == norm_anchor:
                start = offsets[i]
                end = offsets[i + len(norm_anchor)]
                positions.append((start, end))
                i += len(norm_anchor)
            else:
                i += 1
        if not positions:
            # ── Pass 3: no match anywhere → give the model a hint
            # built from the closest line so it can re-anchor.
            import difflib
            haystack_lines = original.splitlines()
            first_old_line = old_string.splitlines()[0].strip() if old_string.strip() else ""
            close = (
                difflib.get_close_matches(first_old_line, haystack_lines, n=3, cutoff=0.5)
                if first_old_line
                else []
            )
            hint = ""
            if close:
                hint = "\nClosest lines in file:\n" + "\n".join(
                    f"  • {ln[:120]}" for ln in close
                )
            return tool_error(
                f"old_string not found in {target} (tried exact + "
                f"whitespace-tolerant match).{hint}\nUse read_file to "
                "verify current content before retrying."
            )
        if len(positions) > 1 and not replace_all:
            return tool_error(
                f"old_string matched {len(positions)} times via "
                "whitespace-tolerant match; pass replace_all=true or "
                "give a more unique anchor."
            )
        # Line-aligned spans always end at a newline boundary. If the
        # model's ``new_string`` doesn't end with one, the next line
        # after the patch gets glued onto the last replaced line.
        # Auto-append a newline whenever the original span ended with
        # one and the replacement doesn't.
        effective_new = new_string
        if positions and original[positions[0][1] - 1:positions[0][1]] == "\n" \
                and not effective_new.endswith("\n"):
            effective_new = effective_new + "\n"
        # Apply replacements right-to-left so earlier offsets stay valid.
        new_content = original
        targets = positions if replace_all else positions[:1]
        for start, end in reversed(targets):
            new_content = new_content[:start] + effective_new + new_content[end:]
        match_mode = "whitespace-tolerant"
        match_count = len(targets)
    # ── Write back ───────────────────────────────────────────────
    try:
        target.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        return tool_error(f"cannot write {target}: {exc}")
    delta = len(new_content) - len(original)
    logger.info(
        "patch_file: PATCHED %s (match=%s count=%d Δ=%+d bytes)",
        target, match_mode, match_count, delta,
    )
    return tool_result(
        path=str(target),
        match_mode=match_mode,
        replacements=match_count,
        bytes_before=len(original.encode("utf-8")),
        bytes_after=len(new_content.encode("utf-8")),
    )


def search_files(
    pattern: str,
    path: str = ".",
    *,
    file_glob: str | None = None,
    limit: int = 50,
    case_insensitive: bool = False,
) -> str:
    """Tool handler — grep for a regex across text files under ``path``.

    Pure-Python replacement for the Hermes ``search_files`` that died
    on the missing ``tools.terminal_tool`` import. Scans up to ``limit``
    matches and returns them as ``{path, line, text}`` records.
    """
    if not pattern or not isinstance(pattern, str):
        return tool_error("missing or invalid 'pattern'")
    resolved = _resolve_for_read(path or ".")
    if isinstance(resolved, str):
        return tool_error(resolved)
    if not resolved.exists():
        return tool_error(f"path does not exist: {path!r}")
    import re as _re
    try:
        flags = _re.IGNORECASE if case_insensitive else 0
        regex = _re.compile(pattern, flags)
    except _re.error as exc:
        return tool_error(f"invalid regex {pattern!r}: {exc}")
    # Default glob keeps the search to reasonable text files so we
    # don't spend minutes scanning node_modules / .venv / __pycache__
    # binaries on a bare directory call. The model can still override
    # with file_glob='*' to opt back in.
    if file_glob:
        candidate_iter = resolved.rglob(file_glob) if resolved.is_dir() else [resolved]
    elif resolved.is_dir():
        text_exts = (".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".txt", ".json",
                     ".yaml", ".yml", ".toml", ".rs", ".go", ".java", ".kt",
                     ".cs", ".html", ".css", ".sh", ".ps1")
        candidate_iter = (
            p for p in resolved.rglob("*")
            if p.is_file() and p.suffix.lower() in text_exts
        )
    else:
        candidate_iter = [resolved]
    matches: list[dict] = []
    skip_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__",
                 ".pytest_cache", "target", "dist", "build"}
    for fp in candidate_iter:
        if any(part in skip_dirs for part in fp.parts):
            continue
        if not fp.is_file():
            continue
        try:
            with fp.open("r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, start=1):
                    if regex.search(line):
                        matches.append({
                            "path": str(fp),
                            "line": lineno,
                            "text": line.rstrip("\n")[:300],
                        })
                        if len(matches) >= limit:
                            break
        except OSError:
            continue
        if len(matches) >= limit:
            break
    truncated = len(matches) >= limit
    logger.info(
        "search_files: pattern=%r path=%s matches=%d%s",
        pattern, resolved, len(matches), " (truncated)" if truncated else "",
    )
    return tool_result(
        pattern=pattern,
        path=str(resolved),
        matches=matches,
        match_count=len(matches),
        truncated=truncated,
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
        Tool(
            name="patch",
            description=(
                "Replace `old_string` with `new_string` in an existing file. "
                "Tries exact match first, then a whitespace-tolerant match "
                "(handles indentation/newline drift). On no match, returns "
                "the closest line as a hint so you can re-target. Use this "
                "instead of read_file + write_file when changing a small "
                "piece of a file. Workspace files are REFUSED by policy "
                "(workspace is create-only); use this on files under the "
                "agent home (your scripts, references, scratch)."
            ),
            schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Path to the file. Relative is resolved under "
                            "the agent home; absolute is used as-is."
                        ),
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Text to find. Must be unique unless replace_all=true.",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Text to replace `old_string` with.",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace every match instead of just the first.",
                        "default": False,
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
            handler=lambda args: patch_file(
                (args or {}).get("path", ""),
                (args or {}).get("old_string", ""),
                (args or {}).get("new_string", ""),
                replace_all=bool((args or {}).get("replace_all", False)),
            ),
        ),
        Tool(
            name="search_files",
            description=(
                "Grep for a regex across text files. Returns up to `limit` "
                "matches as {path, line, text} records. Defaults to text "
                "file extensions (.py/.md/.json/.js/.ts/...) when path is "
                "a directory; override with file_glob to search anything. "
                "Skips common heavy dirs (node_modules, .venv, target, "
                "__pycache__) automatically."
            ),
            schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Python-flavored regex to match.",
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory to search (default '.').",
                        "default": ".",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": (
                            "Optional rglob pattern (e.g. '*.py'). When "
                            "omitted, restricts to common text extensions."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Stop after this many matches (default 50).",
                        "default": 50,
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "Case-insensitive matching.",
                        "default": False,
                    },
                },
                "required": ["pattern"],
            },
            handler=lambda args: search_files(
                (args or {}).get("pattern", ""),
                (args or {}).get("path", ".") or ".",
                file_glob=(args or {}).get("file_glob"),
                limit=int((args or {}).get("limit", 50) or 50),
                case_insensitive=bool((args or {}).get("case_insensitive", False)),
            ),
        ),
    ]
