# Copyright (c) 2026 Ubion ax center
"""Import-path shim for vendored Hermes modules that do
``from tools import skill_usage``.

In the upstream Hermes layout ``tools/`` is a large package with 102 files.
We only need ``skill_usage`` for the curator port — but we keep the
``tools.skill_usage`` import path intact so the vendored ``curator.py``
doesn't need to be patched.

This shim re-exports the top-level ``skill_usage`` module so that
``from tools import skill_usage`` resolves to the same module object as
``import skill_usage``.
"""

import skill_usage  # noqa: F401

__all__ = ["skill_usage"]
