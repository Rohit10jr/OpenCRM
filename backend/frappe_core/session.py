"""The ambient "current user", the Django equivalent of ``frappe.session.user``.

Frappe reads ``frappe.session.user`` from anywhere - model controllers, the filter
layer, permission hooks. Django has no such ambient. Several phase-0 pieces genuinely
need it:

* ``BaseDocument.save`` stamps ``owner`` / ``modified_by``
* the filter translator resolves the ``@me`` token
* the phase-2 permission hooks take ``user`` as an argument

A ``ContextVar`` gives one value per thread *and* per async task, so it is safe under
both WSGI and ASGI. ``CurrentUserMiddleware`` sets it per request; tests and Celery
tasks use the ``session_user`` context manager.

Unauthenticated resolves to ``GUEST_USER`` ("Guest"), matching Frappe.
"""

from contextlib import contextmanager
from contextvars import ContextVar

GUEST_USER = "Guest"
ADMINISTRATOR = "Administrator"

_current_user: ContextVar[str] = ContextVar("frappe_current_user", default=GUEST_USER)


def get_current_user() -> str:
    """Return the current user's email/PK, or ``"Guest"``."""
    return _current_user.get()


def set_current_user(user: str | None) -> object:
    """Set the current user. Returns the token needed to restore the previous value."""
    return _current_user.set(user or GUEST_USER)


def reset_current_user(token: object) -> None:
    _current_user.reset(token)


@contextmanager
def session_user(user: str | None):
    """Run a block as ``user``.

    >>> with session_user("alice@example.com"):
    ...     doc.save()
    """
    token = set_current_user(user)
    try:
        yield
    finally:
        reset_current_user(token)


class CurrentUserMiddleware:
    """Bind ``request.user`` into the contextvar for the duration of the request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        # DRF authenticates in the view, not middleware, so request.user here is the
        # Django session user. JWTAuthenticatedUserMixin re-binds it once DRF has run;
        # this is the fallback for non-DRF views.
        name = None
        if user is not None and getattr(user, "is_authenticated", False):
            name = user.pk
        token = set_current_user(name)
        try:
            return self.get_response(request)
        finally:
            reset_current_user(token)
