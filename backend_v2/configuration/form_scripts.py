"""`get_form_script`, an internal helper (specs/CONFIGURATION.md section 4.6).

Ported from `backend/crm_app/api/form_script.py:17-34` (upstream
`crm_form_script.py:41-57`). Not a route: neither backend nor upstream exposes it;
`get_data` (milestone 8) sends its answer to the browser. Every form script is readable
by everyone, so there is no row rule to apply.
"""

from __future__ import annotations

from configuration.models import CRMFormScript


def get_form_script(dt: str, view: str = "Form"):
    """A bare string for one enabled script, a list for several, `None` for none:
    upstream's shapes, which the frontend branches on."""
    scripts = CRMFormScript.enabled_scripts(dt, view)
    if not scripts:
        return None
    return scripts if len(scripts) > 1 else scripts[0]
