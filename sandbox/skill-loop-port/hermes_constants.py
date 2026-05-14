# Copyright (c) 2026 Ubion ax center
"""Import shim — re-export :func:`agent_home.get_hermes_home`.

The vendored Hermes modules (``curator.py``, ``skill_usage.py``) do
``from hermes_constants import get_hermes_home``.  Instead of patching
those vendored files, we provide a module of the same name here and
re-export our ported implementation from :mod:`agent_home`.  This keeps
the vendored sources byte-identical aside from their license header,
which is the whole point of "Vendor copy" strength.

If we later need additional symbols from the upstream ``hermes_constants``
module, add them here as thin re-exports — never edit the vendored files
to look elsewhere.
"""

from agent_home import get_hermes_home

__all__ = ["get_hermes_home"]
