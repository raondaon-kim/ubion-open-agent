# Ported from NousResearch/hermes-agent (MIT License)
# Original: https://github.com/NousResearch/hermes-agent/blob/b06e9993021a8eebd891fc60d52372446315b2f0/hermes_constants.py
# Rewritten in Ubion conventions; behavior of `get_hermes_home` preserved.
#
# Copyright (c) 2025 Nous Research (original algorithm)
# Copyright (c) 2026 Ubion ax center (implementation)
#
# This file is licensed under the MIT License. See NOTICE.md for the full
# license text and attribution.
"""Resolve the agent's persistent home directory.

In the Hermes original, this returns ``~/.hermes`` (or whatever
``HERMES_HOME`` points to).  In this port we keep the same interface name
``get_hermes_home`` because that's what the vendored ``curator.py`` and
``skill_usage.py`` import — but we read our own env var
``UBION_AGENT_HOME`` first.  This lets us run the sandbox without polluting
the real ``~/.hermes`` directory if Hermes itself is installed locally.

The profile/legacy-path logic from the upstream module is intentionally
omitted — we don't use profiles (per PROJECT_SPEC §2.2 option C, our
isolation is per-container, not per-profile inside a single Hermes
install).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def get_hermes_home() -> Path:
    """Return the agent's persistent home directory.

    Resolution order:
      1. ``UBION_AGENT_HOME`` env var (our project's own override)
      2. ``HERMES_HOME`` env var (kept for compatibility with vendored code
         that may set it directly)
      3. ``~/.ubion-agent`` (default for the port)

    The vendored ``curator.py`` and ``skill_usage.py`` import this name as
    ``from hermes_constants import get_hermes_home`` — we shim that import
    by exposing this module path-aliased.  See ``hermes_constants.py`` in
    this directory.
    """
    val = os.environ.get("UBION_AGENT_HOME", "").strip()
    if val:
        return Path(val)

    val = os.environ.get("HERMES_HOME", "").strip()
    if val:
        return Path(val)

    return Path.home() / ".ubion-agent"


# ----------------------------------------------------------------------
# Convenience wrappers used by vendored Hermes modules. Each composes
# get_hermes_home() with a fixed sub-path. Same names as the upstream
# hermes_constants module so vendored code can be edited minimally.
# ----------------------------------------------------------------------


def get_config_path() -> Path:
    """Path to ``config.yaml`` under the agent home."""
    return get_hermes_home() / "config.yaml"


def get_skills_dir() -> Path:
    """Path to the ``skills/`` directory under the agent home."""
    return get_hermes_home() / "skills"


def get_env_path() -> Path:
    """Path to ``.env`` under the agent home."""
    return get_hermes_home() / ".env"


def get_workspace() -> Path:
    """Return the agent's current *working* directory — the user's content.

    Distinct from ``get_hermes_home()`` (the agent's persistent brain —
    skills, memory, sessions). Workspace is where the user's *target*
    files live: the poetry collection they're editing, the codebase they
    want help with, etc.

    Resolution order:
      1. ``UBION_WORKSPACE`` env var (explicit override)
      2. Current process cwd (``Path.cwd()``)

    The user is expected to flip this between sessions (e.g.
    ``set UBION_WORKSPACE=D:\\poems\\classical`` before launching the
    agent), or the agent harness picks a default cwd. The prompt builder
    reads context files (SOUL.md, HERMES.md, AGENTS.md, CLAUDE.md,
    .cursorrules) from this directory.
    """
    val = os.environ.get("UBION_WORKSPACE", "").strip()
    if val:
        return Path(val)
    return Path.cwd()


def display_hermes_home() -> str:
    """Return a user-friendly display string for the current home.

    Uses ``~/`` shorthand for readability when the path lives under the
    user's HOME directory; otherwise returns the absolute path. Vendored
    skill_commands.py reads this for user-facing messages.
    """
    home = get_hermes_home()
    try:
        return "~/" + str(home.relative_to(Path.home())).replace("\\", "/")
    except ValueError:
        return str(home)


# Sentinel that marks a skill folder as "seeded from the optional pool."
# When this exists with a matching version, we don't re-copy on every boot.
# Removing this file (or bumping `_OPTIONAL_SKILLS_VERSION` below) makes the
# next boot re-seed any *missing* skills — existing user-modified skills
# are never overwritten.
_OPTIONAL_SKILLS_VERSION = "2026-05-14.3"  # bumped: Hermes-style optional split
_SEED_MARKER = ".ubion-installed-skills.lock"


def get_optional_skills_dir() -> Optional[Path]:
    """Locate the *optional* skill pool — Hermes-style "not activated by default".

    Hermes-식 분리 (사용자 결정 2026-05-14):
        - 이 디렉터리의 86개 스킬은 **자동 시드되지 않는다**. 사용자가
          ``skills_install`` 도구 또는 `/skills install <name>` 슬래시
          명령으로 *명시 설치* 해야 ``<agent_home>/skills/installed/`` 로
          복사된다.
        - 자기진화 가시성을 최대화 — 에이전트가 빈 풀에서 시작해 사용
          패턴에 따라 스스로 ``skills/custom/`` 을 만들어 간다.

    Resolution order:
      1. ``UBION_SKILLS_BUNDLE`` env var (explicit path override)
      2. ``<repo_root>/skills-bundle-optional/`` — Phase 1 dev location
      3. ``<agent_home>/.skill-cache/skills-bundle-optional/`` — Phase 3
         coordinator download cache
      4. Returns ``None`` when no local pool exists yet.
    """
    val = os.environ.get("UBION_SKILLS_BUNDLE", "").strip()
    if val:
        p = Path(val)
        return p if p.is_dir() else None

    # (2) repo dev location
    repo_root = Path(__file__).resolve().parents[2]
    dev = repo_root / "skills-bundle-optional"
    if dev.is_dir():
        return dev

    # (3) per-user cache (filled by coordinator download)
    cache = get_hermes_home() / ".skill-cache" / "skills-bundle-optional"
    if cache.is_dir():
        return cache

    return None


# Backward-compatibility shim — older code paths and tests may still call
# ``get_bundled_skills_dir()``. We forward to the new name so nothing breaks
# in flight while the rest of the tree is migrated.
def get_bundled_skills_dir() -> Optional[Path]:  # pragma: no cover — shim
    """Deprecated alias for ``get_optional_skills_dir()``."""
    return get_optional_skills_dir()


def get_installed_skills_dir() -> Path:
    """Where explicitly-installed skills land. Phase 1 (B) starts empty."""
    return get_skills_dir() / "installed"


def get_custom_skills_dir() -> Path:
    """Where self-evolution writes new skills. Phase 1 (B) starts empty."""
    return get_skills_dir() / "custom"


def _hub_lock_path() -> Path:
    return get_hermes_home() / ".hub" / "lock.json"


def _load_hub_lock() -> dict:
    p = _hub_lock_path()
    if not p.exists():
        return {"schema_version": 1, "installed": {}}
    try:
        import json
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, Exception):
        return {"schema_version": 1, "installed": {}}


def _save_hub_lock(data: dict) -> None:
    import json
    p = _hub_lock_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def list_optional_skills() -> list:
    """Enumerate the optional pool — name, category, description, installed?

    Used by the ``skills_search`` / ``skills_list`` tools so the model can
    propose installations. Lightweight — only reads each SKILL.md's
    frontmatter (cached in `.skill-index.json` once it exists).
    """
    src = get_optional_skills_dir()
    if src is None or not src.is_dir():
        return []
    lock = _load_hub_lock()
    installed_names = set(lock.get("installed", {}).keys())
    out: list = []
    for category_dir in sorted(p for p in src.iterdir() if p.is_dir()):
        for skill_dir in sorted(p for p in category_dir.iterdir() if p.is_dir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            name = skill_dir.name
            description = ""
            try:
                # Read just the first ~800 bytes to grab the description line
                head = skill_md.read_text(encoding="utf-8", errors="replace")[:1200]
                for line in head.splitlines():
                    if line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip('"').strip("'")
                        break
            except OSError:
                pass
            out.append({
                "name": name,
                "category": category_dir.name,
                "description": description,
                "installed": name in installed_names,
            })
    return out


def install_optional_skill(name: str) -> dict:
    """Copy a single optional skill into ``<agent_home>/skills/installed/``.

    Hermes-식: 사용자(또는 LLM 도구)가 명시 호출. ``name`` 은 스킬 폴더
    이름 (예: ``"creative-ideation"``). 중복 설치는 거부. lock 파일에
    출처/버전 기록.

    Returns ``{"status": "installed"|"already_installed"|"not_found", ...}``.
    """
    src = get_optional_skills_dir()
    if src is None or not src.is_dir():
        return {"status": "unavailable", "reason": "no optional skill pool"}

    # 검색 (선형 — 86 개라 OK)
    match = None
    for category_dir in src.iterdir():
        if not category_dir.is_dir():
            continue
        cand = category_dir / name
        if cand.is_dir() and (cand / "SKILL.md").exists():
            match = (category_dir.name, cand)
            break
    if match is None:
        return {"status": "not_found", "name": name}

    category, src_skill = match
    dst_root = get_installed_skills_dir()
    dst_root.mkdir(parents=True, exist_ok=True)
    dst = dst_root / name
    if dst.exists():
        return {"status": "already_installed", "name": name, "path": str(dst)}

    import shutil
    shutil.copytree(src_skill, dst)

    # Lock 갱신
    lock = _load_hub_lock()
    from datetime import datetime, timezone
    lock.setdefault("installed", {})[name] = {
        "category": category,
        "source": "optional-pool",
        "version": _OPTIONAL_SKILLS_VERSION,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "path": str(dst.relative_to(get_hermes_home())),
    }
    _save_hub_lock(lock)
    return {"status": "installed", "name": name, "category": category, "path": str(dst)}


def uninstall_skill(name: str) -> dict:
    """Remove an installed skill from ``<agent_home>/skills/installed/``.

    Only touches skills installed via ``install_optional_skill``. Custom
    self-evolved skills under ``skills/custom/`` are never removed by this
    call — they require explicit user action.
    """
    lock = _load_hub_lock()
    installed = lock.get("installed", {})
    if name not in installed:
        return {"status": "not_installed", "name": name}

    rel = installed[name].get("path", f"skills/installed/{name}")
    target = get_hermes_home() / rel
    if target.exists():
        import shutil
        shutil.rmtree(target)
    installed.pop(name, None)
    lock["installed"] = installed
    _save_hub_lock(lock)
    return {"status": "uninstalled", "name": name}


def list_installed_skills() -> list:
    """Read the hub lock file. Returns the ``installed`` dict as a list."""
    lock = _load_hub_lock()
    return [
        {"name": k, **(v or {})}
        for k, v in lock.get("installed", {}).items()
    ]


def ensure_bundled_skills_seeded() -> dict:
    """**Deprecated as of 2026-05-14** — Hermes-식 분리 정책 적용 후 자동
    시드를 하지 않는다.

    호출자 호환을 위해 함수는 남기지만 *아무 것도 복사하지 않는다*. 사용자가
    명시적으로 ``install_optional_skill(name)`` 또는 슬래시 명령으로 스킬을
    설치해야 ``<agent_home>/skills/installed/`` 에 들어온다.

    Phase 1 (B) (시 시나리오) — 빈 풀에서 시작해 자기진화로 ``skills/custom/``
    이 채워지는 과정을 관찰하는 것이 핵심 검증 게이트 (§9 (B)).
    """
    # 빈 디렉터리만 보장 — `skill_view` / `skill_manage` 가 디렉터리 부재 시 깨지지 않도록.
    skills_dir = get_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "custom").mkdir(parents=True, exist_ok=True)
    (skills_dir / "installed").mkdir(parents=True, exist_ok=True)
    return {
        "seeded": 0,
        "skipped": 0,
        "version": _OPTIONAL_SKILLS_VERSION,
        "note": "Hermes-식 분리: 자동 시드 비활성화. install_optional_skill() 으로 명시 설치.",
    }


# (Original bulk-seed routine — kept here for one-shot recovery if a user
# really wants to dump the whole optional pool into their agent home. Not
# wired into any caller by default.)
def seed_all_optional_skills() -> dict:
    """Bulk-copy *every* optional skill into ``skills/installed/``.

    Provided for *manual* use only (e.g. user types `/skills install --all` or
    runs a one-off CLI). Never called automatically. Returns a summary.
    """
    src = get_optional_skills_dir()
    if src is None or not src.is_dir():
        return {"seeded": 0, "skipped": 0, "reason": "no optional skill pool"}

    dst_root = get_installed_skills_dir()
    dst_root.mkdir(parents=True, exist_ok=True)

    seeded: list[str] = []
    skipped: list[str] = []
    for category_dir in sorted(p for p in src.iterdir() if p.is_dir()):
        for skill_dir in sorted(p for p in category_dir.iterdir() if p.is_dir()):
            target = dst_root / skill_dir.name
            if target.exists():
                skipped.append(skill_dir.name)
                continue
            import shutil
            shutil.copytree(skill_dir, target)
            seeded.append(skill_dir.name)
            # lock 도 갱신
            lock = _load_hub_lock()
            from datetime import datetime, timezone
            lock.setdefault("installed", {})[skill_dir.name] = {
                "category": category_dir.name,
                "source": "optional-pool",
                "version": _OPTIONAL_SKILLS_VERSION,
                "installed_at": datetime.now(timezone.utc).isoformat(),
                "path": f"skills/installed/{skill_dir.name}",
                "bulk_seeded": True,
            }
            _save_hub_lock(lock)

    return {
        "seeded": len(seeded),
        "skipped": len(skipped),
        "version": _OPTIONAL_SKILLS_VERSION,
        "source": str(src),
    }


# Legacy entry kept to remain wire-compatible with anything that still
# expects the original signature.
def _legacy_bulk_seed_impl() -> dict:  # pragma: no cover — historical record
    src = get_optional_skills_dir()
    if src is None or not src.is_dir():
        return {"seeded": 0, "skipped": 0, "reason": "no optional skill pool"}

    dst_root = get_skills_dir()
    dst_root.mkdir(parents=True, exist_ok=True)

    seeded: list[str] = []
    skipped: list[str] = []
    for category in sorted(p for p in src.iterdir() if p.is_dir()):
        for skill_dir in sorted(p for p in category.iterdir() if p.is_dir()):
            rel = f"{category.name}/{skill_dir.name}"
            target = dst_root / rel
            if target.exists():
                skipped.append(rel)
                continue
            import shutil
            shutil.copytree(skill_dir, target)
            seeded.append(rel)

    # Drop the version marker (informational, not gating — we always do
    # the per-folder existence check above).
    marker = dst_root / _SEED_MARKER
    marker.write_text(
        f"optional_skills_version: {_OPTIONAL_SKILLS_VERSION}\n"
        f"last_seed_skills_added: {len(seeded)}\n"
        f"source: {src}\n",
        encoding="utf-8",
    )
    return {
        "seeded": len(seeded),
        "skipped": len(skipped),
        "version": _OPTIONAL_SKILLS_VERSION,
        "source": str(src),
    }


# Backward-compat constant — keep symbol so external callers don't break.
_BUNDLED_SKILLS_VERSION = _OPTIONAL_SKILLS_VERSION


def download_skills_bundle(
    *,
    base_url: str,
    bearer_token: Optional[str] = None,
    timeout: float = 30.0,
) -> dict:
    """Download the skill bundle from a coordinator (or local) endpoint.

    Used by Phase 3 Tauri tray app on first launch. Resolution flow:

      1. GET ``<base_url>/v1/ubion/skills/bundle/info`` with current ETag
      2. If 304 → bundle already up-to-date, return early
      3. If 200 → GET ``<base_url>/v1/ubion/skills/bundle`` (tar.gz)
      4. Extract to ``<agent_home>/.skill-cache/skills-bundle/``
      5. Drop ``.etag`` next to the bundle so future calls send If-None-Match

    Phase 1 callers can pass ``base_url="http://127.0.0.1:9000"`` (same
    FastAPI server). Phase 3 passes the coordinator URL.

    Returns ``{"status": "downloaded"|"up_to_date"|"unavailable", ...}``.
    Network errors raise — caller decides whether to fall back to a
    pre-bundled local copy or surface to the user.
    """
    try:
        import urllib.request  # noqa: PLC0415 — only needed when downloading
        import urllib.error  # noqa: PLC0415
        import tarfile  # noqa: PLC0415
    except ImportError as exc:
        return {"status": "unavailable", "reason": f"import failure: {exc}"}

    cache_root = get_hermes_home() / ".skill-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    etag_path = cache_root / ".etag"
    bundle_dir = cache_root / "skills-bundle"

    headers: dict = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    if etag_path.exists() and bundle_dir.is_dir():
        headers["If-None-Match"] = etag_path.read_text(encoding="utf-8").strip()

    info_url = base_url.rstrip("/") + "/v1/ubion/skills/bundle"
    req = urllib.request.Request(info_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 304:
                return {"status": "up_to_date", "bundle_dir": str(bundle_dir)}
            new_etag = resp.headers.get("ETag", "").strip()
            data = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return {"status": "up_to_date", "bundle_dir": str(bundle_dir)}
        return {"status": "unavailable", "reason": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001 — network errors are user-facing
        return {"status": "unavailable", "reason": str(exc)}

    # Extract atomically: write to a temp dir then swap into place so a
    # crash mid-extract can't leave a half-written bundle.
    import io
    import shutil
    tmp_dir = cache_root / ".skills-bundle.partial"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(tmp_dir)

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    # tarball wraps everything under top-level "skills-bundle/" — move that up.
    extracted_root = tmp_dir / "skills-bundle"
    if extracted_root.is_dir():
        extracted_root.rename(bundle_dir)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        tmp_dir.rename(bundle_dir)

    if new_etag:
        etag_path.write_text(new_etag, encoding="utf-8")
    return {
        "status": "downloaded",
        "bundle_dir": str(bundle_dir),
        "etag": new_etag,
    }


_wsl_detected: bool | None = None


def is_wsl() -> bool:
    """Return True when running inside WSL (Windows Subsystem for Linux).

    Checks ``/proc/version`` for the ``microsoft`` marker that both WSL1
    and WSL2 inject. Result is cached for the process lifetime. On
    Windows-proper (no /proc) this returns False.

    Vendored ``agent/prompt_builder.py`` imports this for environment hints.
    """
    global _wsl_detected
    if _wsl_detected is not None:
        return _wsl_detected
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            _wsl_detected = "microsoft" in f.read().lower()
    except Exception:
        _wsl_detected = False
    return _wsl_detected
