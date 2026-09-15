"""Ported ``crm/api/*.py`` endpoints - phase 3.

Importing this package runs the ``@whitelist`` decorators, which is what makes each
dotted path resolvable. ``CrmAppConfig.ready`` imports it.

Module layout mirrors the source so a path maps to a file by inspection:
``crm.api.contact.get_linked_deals`` lives in ``crm_app/api/contact.py``. The exception
is ``misc.py``, which holds the endpoints defined directly in ``crm/api/__init__.py``
(their dotted paths have no module segment: ``crm.api.invite_by_email``).

``crm.api.doc.get_data`` is **not** here - phase 0 built it, in
``frappe_core/api/doc.py``.
"""

from crm_app.api import (  # noqa: F401
    activities,
    assignment_rule,
    auth,
    auth_pages,
    call_log,
    client,
    comment,
    contact,
    dashboard,
    deal,
    doc,
    exchange_rate,
    fields_layout,
    form_script,
    lead,
    misc,
    notifications,
    onboarding,
    session,
    settings,
    user,
    view_settings,
    views,
)
