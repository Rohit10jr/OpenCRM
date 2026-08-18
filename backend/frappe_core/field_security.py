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
