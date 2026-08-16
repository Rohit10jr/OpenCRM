"""``crm.api.auth.oauth_providers``. Ported from ``crm/api/auth.py``.

``Social Login Key`` is a framework doctype this port does not model, so there are no
providers to enumerate and this returns ``[]`` - which is exactly what upstream returns
on a site with no social login configured, and what the login page renders as "no
third-party providers".

Kept rather than dropped because the endpoint is ``allow_guest`` and the login page
calls it before authenticating; a 404 there would surface as a broken login screen.
"""

from __future__ import annotations

from frappe_core.whitelist import whitelist


@whitelist("crm.api.auth.oauth_providers", allow_guest=True)
def oauth_providers():
    """``crm/api/auth.py:4-39``. Always empty - see the module docstring."""
    return []
