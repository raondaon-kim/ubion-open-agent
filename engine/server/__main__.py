# Copyright (c) 2026 Ubion ax center
"""CLI entry point — `python -m engine.server`.

Reads:
  UBION_HOST   (default 127.0.0.1)
  UBION_PORT   (default 8000)
  UBION_API_TOKEN (empty = auth disabled)

Run:
    $env:ANTHROPIC_API_KEY = "sk-ant-..."
    python -m engine.server

Quick test (PowerShell):
    Invoke-RestMethod -Uri http://127.0.0.1:8000/health
    Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/chat/completions `
        -Method POST -ContentType "application/json" `
        -Body '{"model":"claude-opus-4-7","messages":[{"role":"user","content":"hi"}]}'
"""

from __future__ import annotations

import logging
import os
import socket
import sys
from pathlib import Path

import uvicorn


def _seed_bundled_env() -> None:
    """First-boot: copy ``engine/.env.bundled`` → ``UBION_AGENT_HOME/.env``.

    The Tauri installer ships an ``.env.bundled`` file inside the
    engine resource tree containing the internal LiteLLM proxy
    credentials. On first boot, when the user's agent-home ``.env``
    doesn't exist yet, we copy the bundled version over so the agent
    can call the proxy without the user manually editing anything.

    Subsequent boots leave the user's ``.env`` alone — once it exists,
    the user owns it. They're free to edit (or delete) it.
    """
    try:
        from engine.storage.agent_home import get_env_path
    except Exception:
        return

    target = get_env_path()
    if target.exists():
        return

    # The bundled file sits next to this engine package — both in dev
    # (engine/.env.bundled) and in prod (the Tauri bundler copies the
    # entire engine/ tree into Resource/, preserving relative layout).
    here = Path(__file__).resolve()
    bundled = here.parents[1] / ".env.bundled"
    if not bundled.exists():
        return

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(bundled.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        # Best-effort — a failure here shouldn't block startup. The
        # user will see "key not set" in Debug Drawer and can fix it.
        pass


def _load_dotenv_files() -> None:
    """Best-effort .env loading so users don't have to export
    ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / LITELLM_API_KEY on every
    shell invocation.

    Resolution order (first hit wins per key — python-dotenv preserves
    already-set values by default):

      1. ``UBION_AGENT_HOME/.env``       → the installed binary's
         per-user secrets. Seeded from the bundled defaults on first
         boot via _seed_bundled_env(); after that, this is the file
         the user edits.
      2. Project-root ``.env``           → dev convenience.
      3. ``sandbox/skill-loop-port/.env`` → Phase 0 backwards compat.

    Falls through silently if python-dotenv isn't installed.
    """
    _seed_bundled_env()

    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    from engine.storage.agent_home import get_hermes_home

    here = Path(__file__).resolve()
    project_root = here.parents[2]
    for candidate in (
        get_hermes_home() / ".env",
        project_root / ".env",
        project_root / "sandbox" / "skill-loop-port" / ".env",
    ):
        if candidate.exists():
            load_dotenv(candidate)


def _setup_logging() -> None:
    """Console + rotating file logger under ``UBION_AGENT_HOME/logs/``.

    The file handler is what makes the installed binary debuggable —
    stdout/stderr from a Tauri sidecar are awkward to capture, but the
    file is in a predictable per-user location the user can attach to
    bug reports.
    """
    level = os.environ.get("UBION_LOG_LEVEL", "INFO").upper()
    fmt = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        from engine.storage.agent_home import get_hermes_home
        logs_dir = get_hermes_home() / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            logs_dir / "server.log",
            maxBytes=2 * 1024 * 1024,  # 2 MB per file
            backupCount=3,
            encoding="utf-8",
        )
        handlers.append(file_handler)
    except Exception:
        # Filesystem failure shouldn't block startup.
        pass
    logging.basicConfig(level=level, format=fmt, handlers=handlers)


def main() -> None:
    _load_dotenv_files()
    _setup_logging()
    # FastAPI is the *internal* backend — the user-facing entry is the
    # Vite dev server on 8803 that proxies /v1, /health to here (사용자
    # 결정 2026-05-13: 단일 포트 8803 정책, FastAPI 는 9000 으로 은닉).
    # `host=127.0.0.1` keeps the internal port off the LAN; the Vite
    # process speaks to it over loopback.
    host = os.environ.get("UBION_HOST", "127.0.0.1")
    requested = int(os.environ.get("UBION_PORT", "9000"))
    if requested == 0:
        # Ask the OS for a free port. We bind+close immediately and pass
        # the number to uvicorn — there is a small TOCTOU window on the
        # port, but on loopback with one supervised child the practical
        # risk is negligible. The supervisor must read the first stdout
        # line (`PORT:<n>`) before falling back to a default.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((host, 0))
        port = s.getsockname()[1]
        s.close()
    else:
        port = requested
    auth_enabled = bool((os.environ.get("UBION_API_TOKEN") or "").strip())
    # PORT line first, then human-readable line. Flush so the supervisor
    # sees it before uvicorn's own startup prints.
    print(f"PORT:{port}", flush=True)
    print(f"[ubion] starting on http://{host}:{port} (auth: {'on' if auth_enabled else 'off'})", flush=True)
    sys.stdout.flush()
    uvicorn.run(
        "engine.server.api:app",
        host=host,
        port=port,
        log_level=os.environ.get("UBION_LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
