"""JWT auth - PHASE_0_FOUNDATION.md section 7.

The one sanctioned deviation from Frappe's wire protocol (PORT_PLAN.md section 10):
tokens replace the ``sid`` session cookie.

Endpoints, with the paths the frontend already uses:

* ``POST /api/method/login``          -> ``{"message": {"access": ..., "refresh": ...}}``
* ``POST /api/method/logout``
* ``POST /api/method/token/refresh``
* ``GET  /api/method/frappe.auth.get_logged_user`` -> ``{"message": "user@example.com"}``

``frontend/src/stores/session.js:19,32`` calls ``login`` and ``logout`` by those bare
names; frappe-ui expands a non-dotted resource URL to ``/api/method/<url>``.

Parameter names are Frappe's (``usr`` / ``pwd``) because that is what the Frappe login
form posts. This SPA has no login page of its own - it redirects to the desk's
(``session.js:35``) - so those names are the contract.
"""

from __future__ import annotations

from django.contrib.auth import authenticate
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from frappe_core.exceptions import AuthenticationError, ValidationError
from frappe_core.session import GUEST_USER, get_current_user
from frappe_core.whitelist import whitelist


@whitelist("login", allow_guest=True, methods=("POST",))
def login(usr: str = "", pwd: str = "", **extra) -> dict:
    """Exchange credentials for a token pair.

    Returns Frappe's ``full_name`` / ``message`` keys alongside the tokens so a client
    written against the original response keeps working.
    """
    username = usr or extra.get("username") or extra.get("email") or ""
    password = pwd or extra.get("password") or ""

    if not username or not password:
        raise ValidationError("Both usr and pwd are required")

    user = authenticate(username=username, password=password)
    if user is None:
        # Frappe's own wording on a failed desk login.
        raise AuthenticationError("Invalid login credentials")
    if not user.is_active:
        raise AuthenticationError("User is disabled")

    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "message": "Logged In",
        "home_page": "/crm",
        "full_name": user.full_name or user.name,
        "user": user.name,
    }


@whitelist("logout", methods=("POST", "GET"))
def logout(refresh: str = "", **extra) -> dict:
    """Blacklist the refresh token when blacklisting is installed; always succeed.

    With stateless JWTs the access token stays valid until it expires; the client drops
    it. ``token_blacklist`` is not in INSTALLED_APPS in phases 0-4, so this is a no-op
    beyond validating the token, and is documented as such rather than pretending to
    revoke.
    """
    token = refresh or extra.get("refresh_token") or ""
    if token:
        try:
            RefreshToken(token).blacklist()
        except (TokenError, AttributeError):
            # AttributeError: blacklist app not installed. Not an error for the client.
            pass
    return {"message": "Logged Out"}


@whitelist("token/refresh", allow_guest=True, methods=("POST",))
def refresh_token(refresh: str = "", **extra) -> dict:
    token = refresh or extra.get("refresh_token") or ""
    if not token:
        raise ValidationError("refresh token is required")
    try:
        parsed = RefreshToken(token)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from None
    return {"access": str(parsed.access_token), "refresh": str(parsed)}


@whitelist("frappe.auth.get_logged_user", methods=("GET", "POST"))
def get_logged_user() -> str:
    """``{"message": "user@example.com"}``. Guests get ``"Guest"``, as in Frappe."""
    return get_current_user() or GUEST_USER
