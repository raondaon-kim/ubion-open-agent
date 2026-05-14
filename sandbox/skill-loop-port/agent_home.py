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
