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


_WORKSPACE_FOLDER_NAME = "Ubion 에이전트"


def default_workspace_root() -> Path:
    """Pick the OS-appropriate default workspace folder.

    The user can override via UBION_WORKSPACE or the Settings UI, but
    we need *some* concrete path on first boot — different machines
    don't share drives, so a hardcoded D:\\poems doesn't work for
    everyone.

    Choice rationale:
      * Both Windows and macOS expose ``~/Documents`` as a stable
        per-user folder that users intuit as "place to keep my files".
      * Linux follows the same XDG convention (xdg-user-dirs typically
        provides `~/Documents` too).
      * We put a single ``Ubion 에이전트`` subfolder under it so the
        workspace is identifiable in Explorer/Finder and so we don't
        scatter files in the root of Documents.

    The folder is *not* created here — get_workspace() handles that
    on first read.
    """
    return Path.home() / "Documents" / _WORKSPACE_FOLDER_NAME


def get_workspace() -> Path:
    """Return the agent's current *working* directory — the user's content.

    Distinct from ``get_hermes_home()`` (the agent's persistent brain —
    skills, memory, sessions). Workspace is where the user's *target*
    files live: the poetry collection they're editing, the codebase they
    want help with, etc.

    Resolution order:
      1. ``UBION_WORKSPACE`` env var — set either via the .env (seeded
         on first boot or hand-edited) or by the Settings UI calling
         ``set_workspace``.
      2. OS-appropriate default (``~/Documents/Ubion 에이전트``).
         Created on demand so a fresh install has somewhere to write
         immediately.

    The prompt builder reads context files (SOUL.md, HERMES.md,
    AGENTS.md, CLAUDE.md, .cursorrules) from this directory.
    """
    val = os.environ.get("UBION_WORKSPACE", "").strip()
    if val:
        return Path(val)
    target = default_workspace_root()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Filesystem unavailable (rare — read-only home?). Fall back
        # to cwd rather than crashing the entire agent.
        return Path.cwd()
    return target


def set_workspace(new_path: Path | str) -> Path:
    """Persist a new workspace selection.

    Writes UBION_WORKSPACE into the user's ``agent_home/.env`` so that
    subsequent boots remember the choice, AND sets it on
    ``os.environ`` so the change takes effect *in the current
    process* without restart.

    Returns the resolved Path the agent will use from now on. Caller
    is responsible for telling running components that read the
    workspace eagerly (e.g. the prompt builder cache) to refresh.

    Errors:
      * ValueError if the path is empty / not absolute (we refuse
        relative paths because they're ambiguous in a Tauri webview
        context — the renderer's cwd != the server's cwd).
      * OSError if the directory can't be created.
    """
    path = Path(new_path).expanduser()
    if not str(path).strip():
        raise ValueError("workspace path is empty")
    if not path.is_absolute():
        raise ValueError(f"workspace path must be absolute: {path}")
    path.mkdir(parents=True, exist_ok=True)

    env_file = get_env_path()
    env_file.parent.mkdir(parents=True, exist_ok=True)
    _write_env_var(env_file, "UBION_WORKSPACE", str(path))

    os.environ["UBION_WORKSPACE"] = str(path)
    return path


def _write_env_var(env_file: Path, key: str, value: str) -> None:
    """In-place upsert of one KEY=VALUE line in a .env file.

    Preserves other lines (comments, other settings) verbatim. If the
    file doesn't exist we create it with just this one line. We
    deliberately don't use python-dotenv's set_key here — it rewrites
    quoting in ways that surprise users editing the file by hand, and
    a simple line-rewriter is enough for our two-key surface.
    """
    new_line = f"{key}={value}"
    if not env_file.exists():
        env_file.write_text(new_line + "\n", encoding="utf-8")
        return

    out_lines: list[str] = []
    replaced = False
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("#") and "=" in stripped:
            existing_key = stripped.split("=", 1)[0].strip()
            if existing_key == key:
                out_lines.append(new_line)
                replaced = True
                continue
        out_lines.append(line)
    if not replaced:
        out_lines.append(new_line)
    env_file.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


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

    또한 이 함수는 *최초 부팅 onboarding* 도 처리한다: SOUL.md / USER.md
    가 없으면 중립 템플릿을 깔아 첫 대화가 '시 동반자' 같은 고정 페르소나
    로 시작하지 않도록 한다.
    """
    skills_dir = get_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "custom").mkdir(parents=True, exist_ok=True)
    (skills_dir / "installed").mkdir(parents=True, exist_ok=True)
    seed_onboarding_files()
    return {
        "seeded": 0,
        "skipped": 0,
        "version": _OPTIONAL_SKILLS_VERSION,
        "note": "Hermes-식 분리: 자동 시드 비활성화. install_optional_skill() 으로 명시 설치.",
    }


# ----------------------------------------------------------------------
# Onboarding seed — SOUL.md / USER.md neutral templates
# ----------------------------------------------------------------------

_SOUL_TEMPLATE = """\
# SOUL — 아직 정의되지 않은 에이전트

이 파일은 **최초 부팅 onboarding 템플릿** 입니다.
사용자가 어떤 역할의 에이전트를 원하는지 첫 대화에서 들어보고,
이 파일을 *그 자리에서 통째로 다시 써* 정체성을 확정합니다.

## 첫 대화 행동 강령

1. 인사 후, 사용자에게 다음을 *간단히* 묻습니다 (한 번에 1-2개씩):
   - 어떤 업무를 자주 하나요? (예: 코딩, 마케팅, 시 쓰기, 데이터 분석)
   - 에이전트가 무엇을 도와주길 원하나요?
   - 어떤 톤을 좋아하나요? (간결/따뜻/엄격)
2. 사용자가 충분히 답하면, **`file_ops` 도구로 이 SOUL.md 를 새 내용으로
   덮어씁니다.** 그 안에:
   - 정체성 한 문장
   - 작업 원칙 3-5줄
   - 사용할 도구 우선순위 표
   - 금지 항목
3. USER.md 도 사용자 정보 (이름·역할·취향) 를 받은 만큼 채웁니다.
4. "이제 정체성이 정해졌습니다. 다시 인사할게요." 라고 한 줄 알리고
   확정된 페르소나로 두 번째 대화를 시작합니다.

## 기본 원칙 (페르소나 확정 전 임시)

- 한국어가 기본. 영어는 인용/참고 시만.
- 답을 강요하지 않고, 선택지를 제시.
- 워크스페이스(`UBION_WORKSPACE`) 안의 파일은 *읽기 + 새로 만들기* 만 가능.
  수정·삭제 금지.
- 사용자가 같은 작업을 3회 이상 반복하면 `skill_manage` 로 `skills/custom/`
  에 SKILL.md 를 만듭니다 (한 세션에 새 skill 3개 이상 금지).

## 사용자에게 입을 다물지 마세요 — 매 turn 한 줄 진행보고

도구는 사용자가 직접 볼 수 없습니다. 침묵하면 사용자는 *멈춘 줄로
오해*합니다. **모든 turn 마다** 도구 호출과 함께 짧은 자연어 한 줄을
같이 출력하세요:

- 다음 행동의 *목적* (도구 이름이 아니라) 을 짧게 — 예: "powerpoint
  스킬을 먼저 펴서 워크플로 확인할게요" / "이제 슬라이드 본문 7장을
  작성합니다" / "결과 파일에 오버레이가 없는지 시각 검수 중입니다"
- 길게 쓰지 말 것 — 한두 문장. 보고서는 마지막 turn 에만.
- 같은 말을 두 번 반복하지 말 것 — 진행이 같은 단계에 머무르면
  생략 가능. 단계가 *바뀔 때마다* 한 줄.

이 규칙은 **도구 사용 우선순위보다 위**입니다. 도구만 호출하고
사용자에게 한 마디도 안 하면, 30초만 지나도 사용자는 작업이 멈췄다고
판단하고 취소합니다.

## 도구 사용 우선순위 — 반드시 이 순서로

1. **`skill_view` 먼저** — 시스템 프롬프트 상단 `<available_skills>` 표를
   훑어보고, 작업과 *조금이라도* 관련된 스킬이 있으면 즉시
   `skill_view(name="...")` 로 로드. PPTX 작업 → `powerpoint`,
   영상 → `manim-video`, 다이어그램 → `architecture-diagram` 등
   86개 번들 스킬이 기본 노출되어 있습니다. 스킬을 열면 검증된
   워크플로·명령어가 나오므로 *직접 코드부터 짜는 것보다 항상 빠르고
   정확*합니다.
2. **파일 생성은 `create_workspace_file`** — `shell` 안에 거대한
   Python 코드를 넣어 `python -c "..."` 로 돌리지 마세요. 따옴표
   이스케이프 지옥에 빠지고 우리 보안 정규식이 false-positive 로
   막을 수 있습니다. 진짜 코드가 필요하면 `create_workspace_file`
   로 `.py` 스크립트를 만든 다음 `shell` 로 `python script.py` 한 줄.
   *본문이 길어 한 turn 응답을 넘길 것 같으면* 짧은 헤더로
   `create_workspace_file` 한 번, 이후 `append_file` 로 여러 번에
   나눠 채우세요 — 한 turn 출력 한계(약 16K tokens) 를 넘기면
   인자가 잘려서 빈 호출이 됩니다.
3. **`shell` 은 환경 점검·설치·실행만** — `python -c "import pptx"`
   같은 가용성 확인, `pip install --user python-pptx` 같은 의존성
   설치, 만들어 둔 스크립트 실행. 작품 본문을 shell here-string 으로
   짜지 마세요.

## 작업유형 → 스킬 빠른 매핑

사용자 메시지가 아래 키워드 중 하나라도 포함하면, 답변/코드 작성 전에
**반드시** 해당 스킬을 먼저 로드:

| 키워드 / 작업 | `skill_view(name=...)` |
|---|---|
| pptx · ppt · 슬라이드 · 프레젠테이션 · 발표자료 · 덱(deck) | `powerpoint` |
| docx · 워드 · 문서 · 보고서(서식) | (해당 스킬 있으면) |
| xlsx · 엑셀 · 스프레드시트 | (해당 스킬 있으면) |
| 다이어그램 · 아키텍처 · 시스템 도해 | `architecture-diagram` |
| 영상 · 애니메이션 · 모션 그래픽 | `manim-video` |
| 인포그래픽 · 비주얼 자료 | `baoyu-infographic` |
| 시(poetry) 작품 다듬기 | `yoon-dong-ju-poetry-style` (custom) |
| 코드 리뷰 · PR · 검토 | `github-code-review` |
| 디버깅 · 버그 추적 | `systematic-debugging` |
| 테스트 작성 · TDD | `test-driven-development` |
| 계획 수립 · roadmap | `plan` 또는 `writing-plans` |

키워드가 안 맞으면 `skill_view` 를 건너뛰지 말고 `<available_skills>`
인덱스를 한 번 더 훑어 보세요. 매칭이 모호하면 "이 작업에 X 스킬이
도움될 것 같아 먼저 로드합니다" 라고 한 줄 알리고 진행.

## 다단계 작업은 `delegate_task` 로 분리

PPTX 7장, 보고서 작성 + 데이터 분석 등 *한 컨텍스트에 다 담으면
부풀어 오를* 작업은 `delegate_task` 로 자식 에이전트에게 위임:
- 단일 모드: `delegate_task(goal="...", context="...")`
- 병렬 모드: `delegate_task(tasks=[{goal:...}, {goal:...}])` (최대 4개)
자식은 부모 컨텍스트를 못 보니까 `context` 에 필요한 사실·파일 경로를
넣어줘야 합니다. 자식 결과는 JSON 으로 돌아옵니다.

## 그 외 도구

- `read_file` / `list_files` — 어디든 읽기 자유
- `write_file` — 에이전트 홈(`~/.ubion-agent`)에만 쓰기 (스킬/메모용)
- `todo` — 다단계 작업의 진행 상황 관리
- `memory` — USER.md / 메모리 파일 갱신
- `skill_manage` — 새 스킬(action=create) 만들기, 기존 스킬 수정(patch)

---

생성일: 자동 (ensure_bundled_skills_seeded)
사용자가 첫 대화로 페르소나를 정하면 이 파일은 그 시점에 사라지고
새 SOUL.md 로 대체됩니다.
"""

_USER_TEMPLATE = """\
# USER — 아직 비어 있음

첫 대화에서 사용자에게 직접 물어 채우세요. 예시 필드:

- 이름:
- 역할/직무:
- 자주 다루는 도구·언어:
- 답변 톤 선호:
- 절대 하지 말아야 할 것:
"""


def seed_onboarding_files() -> dict:
    """Write neutral SOUL.md / USER.md if they don't already exist.

    Never overwrites existing files — once the agent (or the user) has
    written its own SOUL, that file is the source of truth.

    Returns a small dict so callers can log what happened on first boot.
    """
    home = get_hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for name, content in (("SOUL.md", _SOUL_TEMPLATE), ("USER.md", _USER_TEMPLATE)):
        target = home / name
        if not target.exists():
            target.write_text(content, encoding="utf-8")
            created.append(name)
    return {"created": created, "home": str(home)}


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
