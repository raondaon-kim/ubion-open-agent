# Copyright (c) 2026 Ubion ax center
"""Configuration stub for vendored Hermes modules.

The vendored skill_manager_tool.py (and any future Hermes module we
adopt) imports `cfg_get` from `hermes_cli.config` to read values out of
the user's `config.yaml`. We don't ship a config layer in Phase 1, so
`cfg_get` here always returns the supplied default — every config
lookup acts as if the user has not customised anything.

Phase 2 or later can replace this stub with a real config loader.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def cfg_get(cfg: Optional[Dict[str, Any]], *keys: str, default: Any = None) -> Any:
    """Phase 1 stub — always returns `default`.

    Signature mirrors `hermes_cli.config.cfg_get` so vendored code lands
    unchanged. The real upstream helper traverses a nested config dict;
    we don't have a config dict yet, so callers always see the default.
    """
    return default
