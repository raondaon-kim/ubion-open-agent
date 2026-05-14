# Copyright (c) 2026 Ubion ax center
"""Import shim — re-export :class:`mock_agent.AIAgent`.

The vendored ``curator.py`` does ``from run_agent import AIAgent`` (line
1663). To avoid editing the vendored file we provide a module of the same
name here that re-exports our mock implementation.

When the full engine port lands in ``engine/`` later, this shim will be
deleted and ``run_agent`` will be a real module backed by the ported
Hermes engine.
"""

from mock_agent import AIAgent

__all__ = ["AIAgent"]
