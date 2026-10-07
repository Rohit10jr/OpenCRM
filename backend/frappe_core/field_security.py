"""Fields that must never reach the wire.

Phase 1 registers ``User`` and ``Email Account`` as doctypes, which makes them routable
through the generic ``/api/resource/`` endpoint. Both carry credentials, and the generic
machinery is deliberately unopinionated: ``fields="__all__"`` on the serializer and
``fields=["*"]`` on a list request would otherwise return
``User.password`` - the hash - to any authenticated caller.

So the block list lives here, applied in **both** places that can emit a column:

* :func:`frappe_core.serializers.build_serializer_class` - document reads and writes
* :func:`frappe_core.query.resolve_fields` - list reads, including explicit ``fields=``

A model adds its own with a class attribute::

    class EmailAccount(BaseDocument):
        SENSITIVE_FIELDS = ("password",)

This is a denylist, which is the weaker design - an allowlist would be safer but would
mean every phase-1 agent enumerating every field of every model, and a forgotten field
would silently vanish from the UI instead of loudly leaking. Given a phase-1 agent adds
models under time pressure, a wrong denylist fails visibly (data missing from a screen)
while a wrong allowlist fails invisibly. Revisit if the model count grows.
"""

from __future__ import annotations

#: Applied to every model regardless of what it declares. ``password`` covers both
#: ``AbstractBaseUser.password`` and ``Email Account.password``.
GLOBAL_SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "last_login",
    }
)


def sensitive_fields(model) -> set[str]:
    """Fieldnames on ``model`` that must not be serialised or selected."""
    declared = getattr(model, "SENSITIVE_FIELDS", ()) or ()
    return set(GLOBAL_SENSITIVE_FIELDS) | set(declared)


def is_sensitive(model, fieldname: str) -> bool:
    return fieldname in sensitive_fields(model)


def readonly_fields(model) -> set[str]:
    """Fieldnames a client may **read but never write** through the generic route.

    The middle ground between "fully exposed" and :data:`SENSITIVE_FIELDS`, which hides a
    field from reads as well. Some fields have to be visible and must still not be
    settable by the person they describe - ``User.enabled`` is the case that forced this::

        class User(...):
            READONLY_FIELDS = ("enabled", "user_type")

    ``enabled`` appears in the Users settings screen, so hiding it breaks that screen. But
    a disabled account still holds a valid refresh token for its remaining lifetime, so if
    the field were writable the account you just disabled could switch itself back on.

    Applied only to :func:`frappe_core.serializers.build_serializer_class`, not to
    ``query.resolve_fields``: reading is exactly what these fields are for. Whatever
    legitimately changes them does so through an endpoint that checks who is asking -
    ``crm_app.api.user.update_user_role`` for roles, for instance.
    """
    declared = getattr(model, "READONLY_FIELDS", ()) or ()
    return set(declared)


#: Roles that see a model's :data:`RESTRICTED_FIELDS`. Overridable per model with
#: ``RESTRICTED_FIELDS_ROLES``; this is the default because it matches the pair already
#: used by ``create_email_account`` and ``crm_app.permissions.metadata_docs``.
DEFAULT_PRIVILEGED_ROLES = frozenset({"System Manager", "Sales Manager"})


def restricted_fields(model) -> set[str]:
    """Fieldnames only a privileged caller may read.

    The third and last of the three field tools, and the one that needs a *user*:

    * :func:`sensitive_fields` - nobody reads it, ever (credentials)
    * :func:`readonly_fields`  - everybody reads it, nobody writes it (``User.enabled``)
    * this                     - managers read it, others do not (``smtp_server``)

    Upstream has no equivalent because it does not need one: it withholds the whole
    record from anyone below System Manager. This port cannot, because the Vue Profile
    screen lists email accounts for every user, so the record has to be readable and the
    infrastructure fields on it do not.
    """
    return set(getattr(model, "RESTRICTED_FIELDS", ()) or ())


def privileged_roles(model) -> set[str]:
    return set(getattr(model, "RESTRICTED_FIELDS_ROLES", None) or DEFAULT_PRIVILEGED_ROLES)


def hidden_from(model, user: str | None = None) -> set[str]:
    """Every field ``user`` may not read: the sensitive ones, plus the restricted ones
    unless they hold a privileged role.

    ``user`` defaults to the ambient session user, which is what makes this usable from
    the serializer - serializer classes are built once per model and cached, so the
    decision cannot be baked into the class and has to be taken per request.
    """
    blocked = sensitive_fields(model)
    restricted = restricted_fields(model)
    if not restricted:
        return blocked

    from frappe_core.session import get_current_user

    user = user or get_current_user()
    if user == "Administrator":
        return blocked

    if _roles_of(user) & privileged_roles(model):
        return blocked
    return blocked | restricted


def is_hidden(model, fieldname: str, user: str | None = None) -> bool:
    """Whether ``user`` may not read ``fieldname``. Prefer this to ``fieldname in
    hidden_from(...)`` when checking one name.

    **A sensitive field answers without touching the database.** Its answer does not
    depend on who is asking - nobody may read it - so the role lookup is only reached for
    a field that is merely *restricted*. That keeps the credential guard free of a query
    on every filter entry, and keeps the tests covering it runnable without a database.
    """
    if fieldname in sensitive_fields(model):
        return True
    if fieldname not in restricted_fields(model):
        return False
    return fieldname in hidden_from(model, user)


def privileged_write_fields(model) -> set[str]:
    """Fieldnames everybody reads and only a privileged role writes: upstream's
    permlevel-1 fields.

    The fourth tool, between :func:`readonly_fields` (nobody writes) and plain writable.
    ``User.user_emails`` forced it: the Profile screen shows every user their outgoing
    accounts and lets them add one, but upstream keeps the table at permlevel 1
    (``user.json``), where System Manager alone may write it, so a Sales User cannot
    attach an outgoing account to themselves. Anyone else's value is **dropped before
    validation**, which is what upstream does: ``document.py:_validate_perm_levels``
    resets a field the caller may not write to its stored value, silently, and the save
    goes through. Declared per model::

        class User(...):
            PRIVILEGED_WRITE_FIELDS = ("user_emails",)
            PRIVILEGED_WRITE_ROLES = ("System Manager",)

    ``PRIVILEGED_WRITE_ROLES`` defaults to :func:`privileged_roles`.
    """
    return set(getattr(model, "PRIVILEGED_WRITE_FIELDS", ()) or ())


def privileged_write_roles(model) -> set[str]:
    return set(getattr(model, "PRIVILEGED_WRITE_ROLES", None) or privileged_roles(model))


def unwritable_by(model, user: str | None = None) -> set[str]:
    """The privileged-write fields ``user`` may not write; empty for a privileged caller.
    ``user`` defaults to the session user, for the same reason :func:`hidden_from` does."""
    fields = privileged_write_fields(model)
    if not fields:
        return set()
    from frappe_core.session import get_current_user

    user = user or get_current_user()
    if user == "Administrator" or _roles_of(user) & privileged_write_roles(model):
        return set()
    return fields


def _roles_of(user: str) -> set[str]:
    """Memoised per request, the way ``crm_app.permissions.platform_docs._roles`` is.

    This is called once per *filter entry* as well as once per read, so an unmemoised
    lookup would be a query per filter - the N+1 shape C9 exists to avoid. The answer is
    identical for every call within a request.
    """
    from frappe_core.session import get_request_cache

    cache = get_request_cache()
    key = ("field_security.roles", user)
    if key not in cache:
        from frappe_platform.models import User

        found = User._default_manager.filter(pk=user).first()
        cache[key] = found.get_roles() if found is not None else set()
    return cache[key]
