# Copyright (c) 2026 Ubion ax center
"""Skill frontmatter index — cached enumeration of SKILL.md files.

Re-parsing 86 SKILL.md files on every skill_view / skill_list call costs
roughly 480 ms (Phase 1 measurement on dev hardware). For the §2.8 NFR
target (boot → chat-ready in 3 s) this is too expensive even though it
runs lazily. We persist a JSON index keyed by absolute path, with mtime
+ size as the invalidation signature.

Cache location: ``<agent_home>/.skill-index.json``

Invalidation rules (any one trips a re-parse for that skill):
  - file mtime changed
  - file size changed
  - skill removed → entry dropped
  - SKILL.md path added → entry built

The cache is a *side accelerator* — every consumer should still treat
``parse_frontmatter()`` as the source of truth. If the cache file is
missing or corrupt, we transparently fall back to fresh parsing and
rewrite the cache.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.storage.agent_home import get_hermes_home, get_skills_dir
from engine.skills.utils import parse_frontmatter

logger = logging.getLogger(__name__)


_INDEX_FILENAME = ".skill-index.json"
_INDEX_SCHEMA_VERSION = 1


@dataclass
class SkillIndexEntry:
    """Single SKILL.md row in the index."""

    path: str                                  # absolute path to SKILL.md
    mtime_ns: int                              # file mtime (ns precision)
    size: int                                  # file size in bytes
    frontmatter: Dict[str, Any] = field(default_factory=dict)


def _index_path() -> Path:
    return get_hermes_home() / _INDEX_FILENAME


def _load_index() -> Dict[str, SkillIndexEntry]:
    """Read the on-disk index, or return an empty dict if missing/corrupt."""
    p = _index_path()
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("skill-index: failed to load %s (%s) — rebuilding", p, exc)
        return {}
    if raw.get("schema_version") != _INDEX_SCHEMA_VERSION:
        logger.info("skill-index: schema mismatch — rebuilding")
        return {}
    out: Dict[str, SkillIndexEntry] = {}
    for entry in raw.get("entries", []):
        try:
            out[entry["path"]] = SkillIndexEntry(
                path=entry["path"],
                mtime_ns=int(entry["mtime_ns"]),
                size=int(entry["size"]),
                frontmatter=entry.get("frontmatter") or {},
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _save_index(entries: Dict[str, SkillIndexEntry]) -> None:
    """Atomically replace the index file."""
    p = _index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _INDEX_SCHEMA_VERSION,
        "entries": [
            {
                "path": e.path,
                "mtime_ns": e.mtime_ns,
                "size": e.size,
                "frontmatter": e.frontmatter,
            }
            for e in entries.values()
        ],
    }
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _scan_skill_files() -> List[Path]:
    """Enumerate all SKILL.md files across every active skills directory.

    Walks the same union ``get_all_skills_dirs()`` returns — writable
    pool first, then the bundled read-only pool, then any external
    dirs. The EXCLUDED_SKILL_DIRS filter (.archive, .hub, ...) is
    applied uniformly so excluded names never sneak into the index
    from one of the alternate roots.
    """
    from engine.skills.utils import EXCLUDED_SKILL_DIRS, get_all_skills_dirs
    out: List[Path] = []
    for skills_dir in get_all_skills_dirs():
        if not skills_dir.exists():
            continue
        for skill_md in skills_dir.rglob("SKILL.md"):
            if any(part in EXCLUDED_SKILL_DIRS for part in skill_md.parts):
                continue
            out.append(skill_md)
    return out


def get_index(*, force_refresh: bool = False) -> Dict[str, SkillIndexEntry]:
    """Return the current skill index, refreshing changed entries.

    Called by skill_view / skill_list / skill_manage when they need
    frontmatter for many skills at once. Cost on a warm cache is just an
    `os.stat()` per file plus a JSON load — typically <20 ms for 86
    skills. Cold cache re-parses everything (~500 ms once).
    """
    cached = {} if force_refresh else _load_index()
    skill_files = _scan_skill_files()
    seen_paths: set[str] = set()
    dirty = False

    for skill_md in skill_files:
        key = str(skill_md.resolve())
        seen_paths.add(key)
        try:
            stat = skill_md.stat()
        except OSError:
            continue
        entry = cached.get(key)
        if (
            entry is not None
            and entry.mtime_ns == stat.st_mtime_ns
            and entry.size == stat.st_size
        ):
            continue  # cache hit
        # cache miss — re-parse
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
            fm, _body = parse_frontmatter(content)
        except OSError as exc:
            logger.warning("skill-index: read failed for %s (%s)", skill_md, exc)
            continue
        cached[key] = SkillIndexEntry(
            path=key,
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
            frontmatter=fm or {},
        )
        dirty = True

    # Drop entries for skills that have been removed.
    stale = set(cached.keys()) - seen_paths
    if stale:
        for k in stale:
            cached.pop(k, None)
        dirty = True

    if dirty:
        try:
            _save_index(cached)
        except OSError as exc:
            logger.warning("skill-index: persist failed (%s) — continuing in-memory", exc)

    return cached


def find_by_name(name: str) -> Optional[SkillIndexEntry]:
    """Lookup a skill by its frontmatter `name` field. None if absent.

    Cheaper than full enumeration when the caller already knows the
    target name.
    """
    for entry in get_index().values():
        if entry.frontmatter.get("name") == name:
            return entry
    return None


def invalidate() -> None:
    """Force the next ``get_index()`` call to rebuild from scratch.

    Called by skill_manage handlers right after they write/edit/remove
    a SKILL.md so subsequent reads see the new state immediately.
    """
    p = _index_path()
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass
