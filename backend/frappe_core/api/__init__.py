"""Whitelisted ``/api/method/`` endpoints owned by phase 0.

Phase 0 ships only what its spec calls for: ``crm.api.doc.get_data`` (section 6b) and
the auth methods (section 7). The other 51 endpoints in ``crm/api/`` are phase 3's.
"""

from frappe_core.api import auth, doc  # noqa: F401  (import registers the methods)
