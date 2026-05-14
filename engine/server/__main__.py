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


def _load_dotenv_files() -> None:
    """Best-effort .env loading so users don't have to export
    ANTHROPIC_API_KEY / DEEPSEEK_API_KEY on every shell invocation.

    Resolution order (first hit wins per key — python-dotenv preserves
    already-set values by default):

      1. ``UBION_AGENT_HOME/.env``       → the installed binary's
         per-user secrets. This is the canonical location once the
         Tauri package is in the wild — each user keeps keys inside
         their own agent home (~/.ubion-agent by default).
      2. Project-root ``.env``           → dev convenience.
      3. ``sandbox/skill-loop-port/.env`` → Phase 0 backwards compat.

    Falls through silently if python-dotenv isn't installed.
    """
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


def main() -> None:
    _load_dotenv_files()
    logging.basicConfig(
        level=os.environ.get("UBION_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )
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
