"""``frappe.model.utils.user_settings.*`` - the per-user, per-doctype UI state.

Ported from ``frappe/model/utils/user_settings.py``. The frontend calls exactly one of
these, ``save`` (``frontend/src/stores/meta.js:saveUserSettings``), to remember a child
table's grid columns.

**A row is keyed on the doctype the client names, which for grid columns is the
*parent*.** ``saveUserSettings(parentDoctype, ...)`` posts the parent and nests the child
under a ``GridView`` key, so ``CRM Deal``'s row holds the columns for ``CRM Contacts``.
That is why ``getdoctype`` reads the settings of ``parent_dt or doctype``: asked about
the child with ``with_parent``, it must answer with the row the save wrote, which is the
parent's. Nothing here knows or cares what the JSON inside means.

**What is not ported, and why.** Upstream keeps the authoritative copy in Redis and
flushes it to the ``__UserSettings`` table from ``sync_user_settings``, which the browser
calls periodically. That is a write-behind cache, not a behaviour: the values a client
can observe are identical either way, and a cache that only one process may write is a
liability under Django's multi-worker deployment. So the write is synchronous here and
there is no ``sync_user_settings`` endpoint - the frontend never calls one.

Storage is :class:`frappe_platform.models.UserSettings`, a plain Django model. Upstream's
``__UserSettings`` is not a DocType and must not become an ``/api/resource/`` route; the
model's own docstring has the reasoning.

Permissions: none beyond being logged in, as upstream - every read and write is scoped
to ``frappe.session.user``, so a user can only ever reach their own row.
"""

from __future__ import annotations

import json

from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist


def _coerce(user_settings) -> dict:
    """``json.loads(user_settings or "{}")`` - upstream's ``save``, first line.

    A dict is accepted as well as the JSON string: ``/api/method`` parses JSON-encoded
    query parameters before dispatch (``frappe_core/query.py:parse_json_param``), so the
    very same value arrives as a string in a POST body and as a dict on a GET.

    A string that is not JSON at all raises, and is meant to: upstream's ``json.loads``
    raises on it too. Swallowing it into ``{}`` would silently wipe the caller's saved
    state on a typo instead of telling them the call was malformed. A *stored* value can
    never reach that branch - the only writer is :func:`update_user_settings`, which
    always writes ``json.dumps`` output.
    """
    if isinstance(user_settings, dict):
        return user_settings
    parsed = json.loads(user_settings or "{}")
    if not isinstance(parsed, dict):
        # "corrupt due to old code" - update_user_settings guards the same way.
        return {}
    return parsed


def get_user_settings(doctype: str, user: str | None = None) -> str:
    """The stored JSON string for ``(user, doctype)``, ``"{}"`` when there is none.

    ``frappe/model/utils/user_settings.py:get_user_settings``. Upstream's second
    argument is ``for_update``, which only decides whether the value read from the
    database is written back into the Redis cache; with no cache the argument has
    nothing to select, so it is replaced by the user whose row to read - which upstream
    takes from ``frappe.session.user`` unconditionally.
    """
    from frappe_platform.models import UserSettings

    return UserSettings.load(user or get_current_user(), doctype)


def update_user_settings(doctype: str, user_settings: dict, user: str | None = None) -> dict:
    """Merge ``user_settings`` into the stored dict **at the top level** and store it.

    ``frappe/model/utils/user_settings.py:update_user_settings`` - ``current.update(...)``
    is a one-level merge, so saving ``{"List": ...}`` leaves an existing ``{"GridView":
    ...}`` alone but replaces an existing ``"List"`` wholesale. The frontend relies on
    both halves of that: it sends one view key at a time and expects the others to
    survive.

    **Read-modify-write, and deliberately not locked.** Two saves of *different* top-level
    keys landing at once can lose one of them. Upstream has the same race and a wider
    window - it merges against a Redis copy and flushes to the table later, so a lost
    update survives until the next write. Closing it here would mean a row lock around a
    table that has no row until the first save, for a document only its own owner can
    write, from one browser tab at a time. Left as it is, on purpose.

    Returns the merged dict.
    """
    from frappe_platform.models import UserSettings

    user = user or get_current_user()
    current = _coerce(get_user_settings(doctype, user))
    current.update(user_settings)
    UserSettings.store(user, doctype, json.dumps(current))
    return current


@whitelist("frappe.model.utils.user_settings.save")
def save(doctype: str, user_settings=None):
    """``frappe/model/utils/user_settings.py:save``.

    Returns the **incoming** settings, not the merged ones - upstream returns its own
    parsed argument. ``stores/meta.js`` ignores the return value and keeps the object it
    sent, so the two agree.
    """
    parsed = _coerce(user_settings)
    update_user_settings(doctype, parsed)
    return parsed


@whitelist("frappe.model.utils.user_settings.get")
def get(doctype: str):
    """``frappe/model/utils/user_settings.py:get`` - the JSON string, verbatim.

    The frontend does not call this: it reads the same string off ``getdoctype``'s
    ``user_settings`` response key. Ported anyway because upstream whitelists it, so it
    is part of the surface a client may legitimately use, and it costs three lines.
    """
    return get_user_settings(doctype)
