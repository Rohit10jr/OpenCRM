"""``CRM Form Script`` — user-authored client-side JavaScript.

Ported from ``crm/fcrm/doctype/crm_form_script/crm_form_script.py``.

`get_data` returns this to the browser, which executes it. **Nothing here evaluates it**
— storing and serving a script is not running it (`PHASE_4_METADATA.md` §2). The XSS
surface is real and is why write access is gated on the administrative roles: a Sales
User who could save a form script could run code in every colleague's browser.
"""

from __future__ import annotations

from frappe_core.query import base_queryset
from frappe_core.session import get_current_user


def get_form_script(dt: str, view: str = "Form"):
    """``crm_form_script.py:41-57``.

    Returns a **list** when several enabled scripts match and a **bare string** when
    exactly one does — upstream's shape, which the frontend branches on. ``None`` when
    there are none.
    """
    # Through base_queryset rather than the manager: CRM Form Script has no row rule
    # today, so this is identical - but it keeps the "endpoints read through
    # frappe_core.query" invariant true without an exception to explain.
    scripts = list(
        base_queryset("CRM Form Script", get_current_user())
        .filter(dt=dt, view=view, enabled=True)
        .values_list("script", flat=True)
    )
    if not scripts:
        return None
    return scripts if len(scripts) > 1 else scripts[0]
