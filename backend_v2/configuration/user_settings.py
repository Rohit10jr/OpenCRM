"""`frappe.model.utils.user_settings.*`: the per-user, per-doctype UI state
(specs/CONFIGURATION.md section 4.5).

Ported from `backend/crm_app/api/user_settings.py`. A row is keyed on the doctype the
client names, which for grid columns is the parent: `saveUserSettings(parentDoctype, ...)`
nests the child under a `GridView` key, and `getdoctype` reads the settings of
`parent_dt or doctype`. Every read and write is the caller's own row; the doctype is not
validated, as upstream. The write is synchronous: there is no write-behind cache and no
`sync_user_settings` endpoint (the frontend calls none).
"""

from __future__ import annotations

import json

from configuration.models import UserSettings
from core.exceptions import ValidationError

#: The key column's length (upstream's `__UserSettings.doctype`).
DOCTYPE_MAX_LENGTH = 140


def _coerce(user_settings) -> dict:
    """`json.loads(user_settings or "{}")`, upstream's first line, accepting a dict too.
    Valid JSON that is not an object becomes `{}`. A string that is not JSON is refused
    (PE-12b), where the old backend would have raised unhandled."""
    if isinstance(user_settings, dict):
        return user_settings
    try:
        parsed = json.loads(user_settings or "{}")
    except (TypeError, ValueError):
        raise ValidationError("User settings must be valid JSON") from None
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _required(doctype) -> str:
    """PE-12b: a missing doctype is refused (the old call raised on the missing
    argument); otherwise it is used as given, never validated."""
    if doctype is None:
        raise ValidationError("DocType is required")
    return str(doctype)


def _storable(doctype) -> str:
    """PE-12b, on the write only: a doctype longer than the key column is refused rather
    than a database error. A read of one finds nothing and answers `"{}"`, as backend/."""
    doctype = _required(doctype)
    if len(doctype) > DOCTYPE_MAX_LENGTH:
        raise ValidationError("DocType name is too long")
    return doctype


def get_user_settings(doctype, *, user) -> str:
    """The stored JSON string for (user, doctype), `"{}"` when there is none."""
    return UserSettings.load(user, _required(doctype))


def update_user_settings(doctype, user_settings: dict, *, user) -> dict:
    """Merge `user_settings` into the stored dict at the top level and store it, as
    upstream's `current.update(...)`: saving `{"List": ...}` leaves `{"GridView": ...}`
    alone but replaces an existing `"List"` wholesale. Returns the merged dict."""
    doctype = _storable(doctype)
    current = _coerce(get_user_settings(doctype, user=user))
    current.update(user_settings)
    UserSettings.store(user, doctype, json.dumps(current))
    return current


def save(doctype, user_settings=None, *, user) -> dict:
    """`user_settings.save`: answers the **incoming** settings, not the merged ones."""
    parsed = _coerce(user_settings)
    update_user_settings(doctype, parsed, user=user)
    return parsed


def get(doctype, *, user) -> str:
    """`user_settings.get`: the JSON string, verbatim."""
    return get_user_settings(doctype, user=user)
