"""Model-declared field visibility and write-access rules."""

from __future__ import annotations

GLOBAL_SENSITIVE_FIELDS = frozenset({"password", "last_login"})
DEFAULT_PRIVILEGED_ROLES = frozenset({"System Manager", "Sales Manager"})


def sensitive_fields(model) -> set[str]:
    declared = getattr(model, "SENSITIVE_FIELDS", ()) or ()
    return set(GLOBAL_SENSITIVE_FIELDS) | set(declared)


def is_sensitive(model, fieldname: str) -> bool:
    return fieldname in sensitive_fields(model)


def readonly_fields(model) -> set[str]:
    return set(getattr(model, "READONLY_FIELDS", ()) or ())


def restricted_fields(model) -> set[str]:
    return set(getattr(model, "RESTRICTED_FIELDS", ()) or ())


def privileged_roles(model) -> set[str]:
    declared = getattr(model, "RESTRICTED_FIELDS_ROLES", None)
    return set(declared or DEFAULT_PRIVILEGED_ROLES)


def _is_privileged(user, roles: set[str]) -> bool:
    if user is None:
        return False
    if user.name == "Administrator":
        return True
    return bool(user.get_roles() & roles)


def hidden_from(model, user) -> set[str]:
    blocked = sensitive_fields(model)
    restricted = restricted_fields(model)
    if restricted and not _is_privileged(user, privileged_roles(model)):
        blocked |= restricted
    return blocked


def is_hidden(model, fieldname: str, user) -> bool:
    # Credentials never require a role lookup. Besides avoiding needless work, this
    # keeps the most important guard independent of database availability.
    if is_sensitive(model, fieldname):
        return True
    if fieldname not in restricted_fields(model):
        return False
    return not _is_privileged(user, privileged_roles(model))


def privileged_write_fields(model) -> set[str]:
    return set(getattr(model, "PRIVILEGED_WRITE_FIELDS", ()) or ())


def privileged_write_roles(model) -> set[str]:
    declared = getattr(model, "PRIVILEGED_WRITE_ROLES", None)
    return set(declared or privileged_roles(model))


def unwritable_by(model, user) -> set[str]:
    fields = privileged_write_fields(model)
    if fields and not _is_privileged(user, privileged_write_roles(model)):
        return fields
    return set()


def encrypted_fields(model) -> set[str]:
    """Concrete fields whose Django type encrypts their stored value."""
    from core.fields import EncryptedFieldMixin

    return {
        field.name
        for field in model._meta.get_fields()
        if isinstance(field, EncryptedFieldMixin)
    }
