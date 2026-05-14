# Copyright (c) 2026 Ubion ax center
"""Markdown-backed conversation store.

One conversation = one .md file under ``UBION_AGENT_HOME/conversations/``.

Filename format::

    YYYY-MM-DD-HHmm-<title-slug>.md

The file is the source of truth — there is no separate index. Listing the
directory + parsing frontmatter gives the sidebar what it needs. Saving
a turn rewrites the whole file (these are small — a 50-message session is
under 50 KB).

File schema::

    ---
    id: 2026-05-14-1230-bi-oneun-dosi
    title: 비 오는 도시
    created: 2026-05-14T12:30:11+09:00
    updated: 2026-05-14T12:34:02+09:00
    model: deepseek-v4-flash
    ---

    ## user · 12:30:11
    비 오는 도시를 주제로 시 한 편 써줘.

    ## assistant · 12:30:14
    회색 빌딩 숲, 비가 내린다 ...

Round-tripping rule: we read messages back as plain ``{role, content}``
dicts. Tool calls / tool results from past turns are not replayed into
the API (the agent learns from them via memory + skill index, not the
raw history) — we only persist user + assistant text turns. That keeps
files human-readable and avoids the multi-provider tool-id headaches
across DeepSeek/Anthropic on resume.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.storage.agent_home import get_hermes_home


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------


def get_conversations_dir() -> Path:
    """Return (and ensure) the conversations directory."""
    path = get_hermes_home() / "conversations"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------


@dataclass
class ConversationTurn:
    role: str            # "user" | "assistant"
    content: str
    timestamp: str = ""  # ISO-8601, optional


@dataclass
class ConversationMeta:
    id: str
    title: str
    created: str
    updated: str
    model: str = ""


@dataclass
class Conversation:
    meta: ConversationMeta
    turns: List[ConversationTurn] = field(default_factory=list)


# ----------------------------------------------------------------------
# Slug + filename
# ----------------------------------------------------------------------


_SLUG_DROP = re.compile(r"[^\w\s가-힣ㄱ-ㅎㅏ-ㅣ-]", re.UNICODE)
_SLUG_SPACE = re.compile(r"\s+")
_SLUG_DASH = re.compile(r"-+")


def slugify(text: str, *, max_len: int = 40) -> str:
    """Make a filesystem-safe slug. Keeps Hangul + ASCII word chars."""
    text = text.strip()
    if not text:
        return "untitled"
    text = _SLUG_DROP.sub(" ", text)
    text = _SLUG_SPACE.sub("-", text)
    text = _SLUG_DASH.sub("-", text).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rstrip("-")
    return text or "untitled"


def make_conversation_id(created: dt.datetime, title: str) -> str:
    """Compose the canonical conversation id (also used as filename stem)."""
    return f"{created.strftime('%Y-%m-%d-%H%M')}-{slugify(title)}"


# ----------------------------------------------------------------------
# Title extraction
# ----------------------------------------------------------------------


def derive_title(turns: List[ConversationTurn]) -> str:
    """First user message's first line (trimmed) is the title."""
    for t in turns:
        if t.role == "user" and t.content.strip():
            first_line = t.content.strip().splitlines()[0]
            return first_line[:60].strip() or "새 대화"
    return "새 대화"


# ----------------------------------------------------------------------
# Serialize / parse
# ----------------------------------------------------------------------


def _format_frontmatter(meta: ConversationMeta) -> str:
    lines = [
        "---",
        f"id: {meta.id}",
        # Title is YAML — escape quotes by switching to a double-quoted
        # scalar. Keep it simple: backslash-escape any \" inside.
        f'title: "{meta.title.replace(chr(92), chr(92)*2).replace(chr(34), chr(92)+chr(34))}"',
        f"created: {meta.created}",
        f"updated: {meta.updated}",
    ]
    if meta.model:
        lines.append(f"model: {meta.model}")
    lines.append("---")
    return "\n".join(lines)


def _format_turn(turn: ConversationTurn) -> str:
    header = f"## {turn.role}"
    if turn.timestamp:
        header += f" · {turn.timestamp}"
    return f"{header}\n\n{turn.content.rstrip()}\n"


def serialize(conv: Conversation) -> str:
    parts = [_format_frontmatter(conv.meta), ""]
    for turn in conv.turns:
        parts.append(_format_turn(turn))
    return "\n".join(parts).rstrip() + "\n"


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_TURN_RE = re.compile(r"^## (user|assistant)(?: · ([^\n]+))?\n", re.MULTILINE)


def _parse_frontmatter(block: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        val = val.strip()
        if val.startswith('"') and val.endswith('"') and len(val) >= 2:
            val = val[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        out[key.strip()] = val
    return out


def parse(text: str) -> Conversation:
    """Parse a conversation .md file back into a Conversation object."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("Conversation file missing frontmatter")
    fm = _parse_frontmatter(m.group(1))
    body = text[m.end():]

    meta = ConversationMeta(
        id=fm.get("id", ""),
        title=fm.get("title", ""),
        created=fm.get("created", ""),
        updated=fm.get("updated", ""),
        model=fm.get("model", ""),
    )

    turns: List[ConversationTurn] = []
    matches = list(_TURN_RE.finditer(body))
    for i, mm in enumerate(matches):
        role = mm.group(1)
        ts = mm.group(2) or ""
        start = mm.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        turns.append(ConversationTurn(role=role, content=content, timestamp=ts))

    return Conversation(meta=meta, turns=turns)


# ----------------------------------------------------------------------
# CRUD
# ----------------------------------------------------------------------


def _path_for(conv_id: str) -> Path:
    # conv_id must already be filesystem-safe (made via make_conversation_id);
    # one last guard against traversal.
    if "/" in conv_id or "\\" in conv_id or conv_id.startswith(".."):
        raise ValueError(f"Invalid conversation id: {conv_id!r}")
    return get_conversations_dir() / f"{conv_id}.md"


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def save_conversation(
    *,
    conv_id: Optional[str],
    turns: List[ConversationTurn],
    model: str = "",
    created: Optional[str] = None,
) -> ConversationMeta:
    """Create or overwrite a conversation file. Returns the saved meta.

    - If ``conv_id`` is None, a new id is minted from now + derived title.
    - On overwrite, ``created`` is preserved; ``updated`` is refreshed.
    """
    title = derive_title(turns)
    now = dt.datetime.now().astimezone()
    updated_iso = now.isoformat(timespec="seconds")

    if conv_id:
        created_iso = created or updated_iso
    else:
        created_iso = updated_iso
        conv_id = make_conversation_id(now, title)

    meta = ConversationMeta(
        id=conv_id,
        title=title,
        created=created_iso,
        updated=updated_iso,
        model=model,
    )
    conv = Conversation(meta=meta, turns=turns)
    _path_for(conv_id).write_text(serialize(conv), encoding="utf-8")
    return meta


def load_conversation(conv_id: str) -> Conversation:
    path = _path_for(conv_id)
    if not path.exists():
        raise FileNotFoundError(f"conversation not found: {conv_id}")
    return parse(path.read_text(encoding="utf-8"))


def list_conversations() -> List[ConversationMeta]:
    """List all conversations, most-recently-updated first.

    We parse only the frontmatter, not the body, so this stays fast
    even with a few hundred files.
    """
    out: List[ConversationMeta] = []
    for path in get_conversations_dir().glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
            m = _FRONTMATTER_RE.match(text)
            if not m:
                continue
            fm = _parse_frontmatter(m.group(1))
            out.append(ConversationMeta(
                id=fm.get("id", path.stem),
                title=fm.get("title", path.stem),
                created=fm.get("created", ""),
                updated=fm.get("updated", ""),
                model=fm.get("model", ""),
            ))
        except (OSError, ValueError):
            continue
    out.sort(key=lambda c: c.updated or c.created, reverse=True)
    return out


def delete_conversation(conv_id: str) -> bool:
    path = _path_for(conv_id)
    if not path.exists():
        return False
    path.unlink()
    return True


# ----------------------------------------------------------------------
# Bridge to API payloads
# ----------------------------------------------------------------------


def turns_from_api_messages(messages: List[Dict[str, Any]]) -> List[ConversationTurn]:
    """Convert ``[{role, content}, ...]`` (from the chat completion request)
    into ConversationTurn objects. We only persist user + assistant text."""
    out: List[ConversationTurn] = []
    for m in messages:
        role = m.get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content", "")
        if isinstance(content, list):
            # Defensive — Anthropic-shape content blocks could appear if
            # callers forward raw history. Flatten to text only.
            parts: List[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
            content = "\n".join(parts)
        if not isinstance(content, str):
            content = str(content)
        if not content.strip():
            continue
        out.append(ConversationTurn(role=role, content=content))
    return out


def turns_to_api_messages(turns: List[ConversationTurn]) -> List[Dict[str, str]]:
    """Convert stored turns back into the ``[{role, content}]`` shape the
    chat endpoint expects on resume."""
    return [{"role": t.role, "content": t.content} for t in turns]
