"""``crm.demo.api.clear_demo_data`` - the "Clear demo data" button.

One endpoint, and the reason it is short is recorded in its docstring rather than left
to be guessed at: the guard is real and ported verbatim; the body is a no-op because the
state it clears is never created in this port.
"""

from __future__ import annotations

from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.whitelist import whitelist

#: ``crm/demo/api.py`` - ``frappe.only_for(["Sales Manager", "System Manager"], True)``.
#: Order matters: it is the order the roles appear in the sentence the user sees.
DEMO_ROLES = ("Sales Manager", "System Manager")


@whitelist("crm.demo.api.clear_demo_data", methods=("POST",))
def clear_demo_data():
    """``crm/demo/api.py:clear_demo_data`` - wipe the seeded demo records.

    Upstream does three things in order:

    1. ``frappe.only_for(["Sales Manager", "System Manager"], True)``.
    2. ``if not frappe.db.get_default("crm_demo_data_created"): return`` - the marker
       ``create_demo_data`` sets after seeding.
    3. Delete the demo leads, notes, tasks, call logs, activities, deals and users, then
       clear the seven ``crm_demo_*`` defaults.

    **Step 1 is ported exactly. Steps 2 and 3 cannot happen here, and that is by design,
    not a stub.** ``create_demo_data`` is not in this port: ``PORT_PLAN.md`` section 2
    rules the whole of ``crm/demo/`` (1,393 LOC) "Regenerate - seed data, use factories",
    so demo records are made by fixtures rather than by a ported seeder. Nor does this
    port have a defaults store - Frappe's ``tabDefaultValue`` / ``frappe.db.get_default``
    has no equivalent here - so the ``crm_demo_data_created`` marker is never written,
    and never set. Upstream on such a site takes the early return at step 2 and deletes
    nothing. This endpoint therefore returns ``None`` for every caller who passes the
    gate, which is upstream's own behaviour for a site with no recorded demo state.

    If demo seeding is ever ported, the deletions come back with it - the seeder and the
    cleaner have to agree on what was created, and only the seeder knows.

    ``frontend/src/composables/demoData.js`` reads no value off the answer; it reloads
    the page. POST only - it is a destructive action upstream, and must not be reachable
    by a link or a prefetch.

    The refusal is ``frappe.only_for``'s ``message=True`` form
    (``frappe/__init__.py:947-970``): each role wrapped in ``frappe.bold``
    (``frappe/__init__.py:2360``) and joined with ", ", titled "Not Permitted".
    Administrator passes without holding either role, as upstream's second line allows.
    """
    from crm_app.api.user import _roles_of
    from frappe_core.session import get_current_user

    user = get_current_user()
    if user == "Administrator":
        return None
    if _roles_of(user).isdisjoint(DEMO_ROLES):
        roles = ", ".join(f"<strong>{role}</strong>" for role in DEMO_ROLES)
        raise FrappePermissionError(
            f"This action is only allowed for {roles}", title="Not Permitted"
        )
    return None
