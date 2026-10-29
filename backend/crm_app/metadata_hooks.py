"""Phase-4 metadata providers, registered through the phase-0 extension points.

`get_data`'s step 3 — "else the user's saved `CRM View Settings`" — was left by phase 0
as a **registered provider**, precisely so this phase would not have to edit `get_data`.
It does not: :func:`register` wires the provider and the four-step resolution order is
untouched.

The lookup key is upstream's, verbatim (`crm/api/doc.py:324-331`)::

    {"dt": doctype, "type": view_type or "list", "is_standard": 1, "user": session_user}

Two consequences of that key worth stating, because both are load-bearing:

* it is **per user**, so one person's saved columns are invisible to everybody else;
* it matches only ``is_standard`` rows — a named view the user switches to is passed in
  by the caller as explicit ``columns``/``rows``, which short-circuits this branch
  entirely (`get_data`'s ``if not custom_view`` guard).
"""

from __future__ import annotations


from frappe_core.query import parse_json_param
from frappe_core.registry import register_metadata_hooks, routable_doctypes


def saved_view_columns(doctype: str, user: str, view_type: str = "list"):
    """Return ``{"columns": [...], "rows": [...]}`` or ``None`` to fall through.

    ``None`` is the fall-through signal, and an empty saved view must return it too:
    a row with no columns would otherwise render a list with no columns, where
    upstream's ``elif`` would have used the controller default.
    """
    from crm_app.models import CRMViewSettings

    row = (
        CRMViewSettings._default_manager.filter(
            dt=doctype, type=view_type or "list", is_standard=True, user=user
        )
        .order_by("-modified")
        .first()
    )
    if row is None:
        return None

    columns = parse_json_param(row.columns, []) or []
    rows = parse_json_param(row.rows, []) or []
    if not columns and not rows:
        return None

    return {"columns": columns, "rows": rows, "load_default_columns": row.load_default_columns}


def register() -> None:
    """Register the provider for every routable doctype.

    Upstream's lookup is not doctype-specific — any doctype can have a saved view — so
    this registers broadly rather than for a hand-picked list, which would silently
    exclude whichever doctype someone added last.
    """
    for doctype in routable_doctypes():
        register_metadata_hooks(doctype, list_columns_provider=saved_view_columns)
