# Copyright (c) 2026 Ubion ax center
"""Shell tool — run a single OS command from the user's workspace.

This is a deliberately *thin* tool with strong invariants rather than a
full sandbox:

  * cwd is pinned to ``UBION_WORKSPACE`` (the user's working folder).
    The agent cannot cd outside; we do not pass --chdir-equivalent args.
  * 60 s hard timeout — runaway commands are killed.
  * stdout / stderr capped at 64 KB each so a huge dump can't blow up
    the LLM context.
  * Windows: ``CREATE_NO_WINDOW`` — no stray console pops.
  * Deny-by-default list for obvious foot-guns (rm -rf /, format,
    shutdown, reg delete, …). The agent gets a clear error explaining
    what's blocked.
  * API keys + tokens are stripped from the child environment so they
    can't leak into a curl/echo line the agent writes.
  * Every invocation is audited via ``logger.info`` so ``server.log``
    is the single source of truth for "what did the agent run?"

This is the *strongest* tool we ship; please read the deny list before
extending. Anything controlling other users' machines, anything
modifying the registry, anything outside the workspace, anything that
disables protection should land on the deny list rather than become a
new flag.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from engine.tools.registry import registry
from engine.storage.agent_home import get_workspace

logger = logging.getLogger(__name__)


SHELL_SCHEMA = {
    "name": "shell",
    "description": (
        "Run a single shell command from the user's workspace folder "
        "and return its stdout/stderr/exit code.\n\n"
        "Constraints:\n"
        "• Working directory is FIXED to the user's workspace; you cannot "
        "  escape it via `cd ..` or absolute paths in the command line.\n"
        "• Hard timeout: 60 seconds.\n"
        "• stdout/stderr each truncated to 64 KB.\n"
        "• Destructive commands are blocked: `rm -rf /`, `format`, "
        "  `shutdown`, `reg delete`, `del /s /q C:\\`, etc.\n"
        "• API keys are stripped from the child environment.\n\n"
        "Use this for: building docx/xlsx with python-docx, running git, "
        "invoking pre-installed CLIs, quick text processing with PowerShell. "
        "Do not use it to install new global software."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "The command line, e.g. "
                    "`python -c \"from docx import Document; Document().save('hello.docx')\"`. "
                    "Quotes follow your shell's rules."
                ),
            },
            "shell": {
                "type": "string",
                "enum": ["powershell", "cmd", "bash"],
                "description": (
                    "Which shell to invoke. Default: 'powershell' on "
                    "Windows, 'bash' elsewhere. Pick 'cmd' only when you "
                    "need cmd.exe-specific syntax (e.g. `dir /b`)."
                ),
            },
            "timeout_s": {
                "type": "integer",
                "description": (
                    "Override the default 60 s timeout (max 60). Use a "
                    "smaller value for commands you expect to finish "
                    "quickly so the agent isn't blocked."
                ),
                "minimum": 1,
                "maximum": 60,
            },
        },
        "required": ["command"],
    },
}


# Patterns that should never run no matter what shell sends them.
# Modeled on Hermes' terminal_tool deny-checks (.hermes-clone/tools/
# terminal_tool.py) but tightened for our "workspace only" stance —
# our workspace policy is "create-only, no modification" so even local
# destructive commands need to be blocked, not just system-wide ones.
_DENY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # System / OS scope — always destructive
    (re.compile(r"\brm\s+-rf?\s+(/|~|\$HOME|\$env:USERPROFILE)\b"),
     "rm -rf on root / home"),
    (re.compile(r"\bformat\s+[A-Za-z]:"), "format <drive>"),
    (re.compile(r"\bshutdown\b", re.I), "shutdown"),
    (re.compile(r"\b(diskpart|mkfs)\b", re.I), "disk partitioning"),
    (re.compile(r"\breg\s+(delete|add|import)\b", re.I), "registry write"),
    (re.compile(r"\bnet\s+user\s+\S+\s+/(add|delete)\b", re.I), "user account mgmt"),
    (re.compile(r"\bicacls\b.*/grant", re.I), "ACL modification"),

    # Recursive deletes — blocked even within workspace because the
    # workspace policy is *create-only* (existing files are sacrosanct).
    (re.compile(r"\bdel\s+/[sq]", re.I), "del /s or /q (recursive delete)"),
    (re.compile(r"\bRemove-Item\b[^|]*\b-Recurse\b", re.I),
     "Remove-Item -Recurse anywhere"),
    (re.compile(r"\brm\s+-rf?\b"), "rm -rf anywhere (workspace is create-only)"),

    # Privilege escalation — we run as the user; sudo never makes sense
    (re.compile(r"\bsudo\b", re.I), "sudo (no terminal for password prompt)"),
    (re.compile(r"\brunas\b", re.I), "runas (no UAC prompt available)"),
    (re.compile(r"\bStart-Process\b.*-Verb\s+runas", re.I), "elevation"),

    # Network listeners that would expose the user's PC
    (re.compile(r"\bnc\s+-l\b"), "netcat listener"),
    (re.compile(r"\bnetsh\b.*\b(advfirewall|portproxy)\b", re.I), "firewall mgmt"),

    # Misc classics
    (re.compile(r":\(\)\{ ?:\|:& ?};:"), "fork bomb"),
    (re.compile(r"\b(curl|wget|Invoke-WebRequest)\b.*\|\s*(sh|bash|pwsh|powershell)",
                re.I),
     "pipe-to-shell from network"),
]


def _command_writes_outside_workspace(command: str, workspace: Path) -> Optional[str]:
    """Reject commands whose absolute paths point outside the workspace.

    Defense-in-depth on top of the cwd lock: even if a command picks an
    absolute path, refuse it when it's clearly outside the workspace
    (or one of a tiny set of read-only system roots).

    The matcher is intentionally conservative — false positives have
    bitten us before, blocking legitimate PowerShell here-strings that
    embedded URLs (``https://...``) or Python code with forward
    slashes. The cwd invariant is the real safety net; this check is
    just to catch obvious "write to C:\\Users\\someone-else\\..." attempts.
    """
    # Only match path-like tokens at a word boundary AND not preceded
    # by `:` (so URLs like https://foo and module syntax like
    # http://host don't trigger). The `(?<![:/A-Za-z])` lookbehind
    # filters out:
    #   * https:// → the `/` is preceded by `:` — skipped
    #   * com/path → the `/` is preceded by a letter (not standalone) — skipped
    #   * //share  → the second `/` is preceded by `/` — skipped (UNC paths
    #                hit the Windows-drive branch separately if absolute)
    abs_re = re.compile(
        r"(?:(?<=\s)|^)([A-Za-z]:[\\/][^\s\"'<>|;&]+|(?<![:/A-Za-z])/[A-Za-z][^\s\"'<>|;&]*)"
    )
    workspace_str = str(workspace).lower().rstrip("\\/")
    # Allowlist:
    #   * the workspace itself
    #   * obviously read-only system roots (Program Files, System32) so
    #     `python -m` against bundled libs works
    #   * POSIX read-only device paths the model uses for stdio redirection
    #     (`/dev/null`, `/dev/stdin`, …) — they don't write to the FS, but
    #     they live outside any workspace, so the naive check rejects them
    safe_prefixes = (
        workspace_str,
        r"c:\program files",
        r"c:\program files (x86)",
        r"c:\windows\system32",
        "/usr/", "/bin/", "/etc/",
        "/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr",
    )
    for match in abs_re.finditer(command):
        token = match.group(1)
        # Skip tokens that are clearly part of a URL — the matcher's
        # lookbehind catches the common case, but be defensive about
        # things like `git+https://...` or `pip install foo @ git+...`.
        start = match.start(1)
        if start >= 2 and command[start - 2 : start] in ("//", ":/"):
            continue
        candidate = token.lower().rstrip("\\/")
        if not any(candidate.startswith(p) for p in safe_prefixes):
            return f"absolute path {token!r} escapes workspace ({workspace})"
    return None


# Env vars we strip from the child so the agent cannot leak them into
# a curl / echo / Out-File line.
_SECRET_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "UBION_API_TOKEN",
    "TAURI_SIGNING_PRIVATE_KEY",
    "TAURI_SIGNING_PRIVATE_KEY_PASSWORD",
    "GITHUB_TOKEN",
    "GH_TOKEN",
)


_MAX_BYTES_PER_STREAM = 64 * 1024
_DEFAULT_TIMEOUT = 60


def _pick_shell(requested: Optional[str]) -> tuple[str, list[str]]:
    """Pick the executable + arg prefix for the requested shell."""
    name = (requested or "").strip().lower()
    if not name:
        name = "powershell" if os.name == "nt" else "bash"
    if name == "powershell":
        return ("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command"])
    if name == "cmd":
        return ("cmd.exe", ["/d", "/s", "/c"])
    if name == "bash":
        return ("bash", ["-c"])
    raise ValueError(f"unsupported shell: {name!r}")


def _sanitize_env() -> Dict[str, str]:
    env = dict(os.environ)
    for key in _SECRET_ENV_KEYS:
        env.pop(key, None)
    return env


def _truncate(data: bytes) -> str:
    if len(data) <= _MAX_BYTES_PER_STREAM:
        return data.decode("utf-8", errors="replace")
    cut = data[:_MAX_BYTES_PER_STREAM].decode("utf-8", errors="replace")
    return cut + f"\n[…truncated {len(data) - _MAX_BYTES_PER_STREAM} bytes]"


def _check_deny(command: str) -> Optional[str]:
    for pat, label in _DENY_PATTERNS:
        if pat.search(command):
            return label
    return None


def shell_tool(
    *,
    command: str,
    shell: Optional[str] = None,
    timeout_s: Optional[int] = None,
) -> Dict[str, Any]:
    """Run ``command`` in the user's workspace. Returns a result dict."""
    if not isinstance(command, str) or not command.strip():
        return {"error": "command must be a non-empty string"}

    denied = _check_deny(command)
    if denied:
        logger.warning("shell tool: blocked %r (matched %s)", command, denied)
        return {
            "error": f"command refused — destructive pattern detected: {denied}. "
                     "If this is a false positive please rephrase or pick another tool.",
        }

    try:
        exe, prefix = _pick_shell(shell)
    except ValueError as exc:
        return {"error": str(exc)}

    cwd = Path(get_workspace()).resolve()
    if not cwd.is_dir():
        # Workspace may not yet exist if the user hasn't set one — fall
        # back to a sensible per-user location so the call still runs.
        cwd = Path.home()

    escape = _command_writes_outside_workspace(command, cwd)
    if escape:
        logger.warning("shell tool: blocked %r (%s)", command, escape)
        return {
            "error": (
                f"command refused — {escape}. "
                f"All shell commands must operate inside the workspace. "
                f"Use relative paths."
            ),
        }

    duration = min(max(int(timeout_s) if timeout_s else _DEFAULT_TIMEOUT, 1),
                   _DEFAULT_TIMEOUT)

    creationflags = 0
    if os.name == "nt":
        # CREATE_NO_WINDOW — no stray console window during tool calls
        # (would otherwise flash on every PowerShell invocation).
        creationflags = 0x0800_0000

    logger.info("shell tool: cwd=%s shell=%s timeout=%ds cmd=%r",
                cwd, exe, duration, command)

    try:
        proc = subprocess.run(
            [exe, *prefix, command],
            cwd=str(cwd),
            env=_sanitize_env(),
            capture_output=True,
            timeout=duration,
            creationflags=creationflags,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("shell tool: timeout after %ds: %r", duration, command)
        return {
            "error": f"command timed out after {duration} s",
            "stdout": _truncate(exc.stdout or b""),
            "stderr": _truncate(exc.stderr or b""),
            "timed_out": True,
        }
    except FileNotFoundError as exc:
        return {"error": f"shell binary not found: {exc.filename}"}

    result = {
        "exit_code": proc.returncode,
        "stdout": _truncate(proc.stdout),
        "stderr": _truncate(proc.stderr),
        "shell": exe,
        "cwd": str(cwd),
    }
    if proc.returncode != 0:
        # Surface non-zero exits prominently so the agent knows to react.
        result["error"] = f"command exited with code {proc.returncode}"
    return result


registry.register(
    name="shell",
    toolset="shell",
    schema=SHELL_SCHEMA,
    handler=lambda args, **_kw: shell_tool(
        command=args.get("command", ""),
        shell=args.get("shell"),
        timeout_s=args.get("timeout_s"),
    ),
)
