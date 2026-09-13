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
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from frappe_core.exceptions import AuthenticationError, ValidationError
from frappe_core.session import GUEST_USER, get_current_user
from frappe_core.security import (
    check_login_allowed,
    get_client_ip,
    record_login_failure,
    record_login_success,
)
from frappe_core.whitelist import whitelist


@whitelist("login", allow_guest=True, methods=("POST",))
def login(usr: str = "", pwd: str = "", **extra) -> dict:
    """Exchange credentials for a token pair.

    Returns Frappe's ``full_name`` / ``message`` keys alongside the tokens so a client
    written against the original response keeps working.

    **Brute-force protection.** Upstream builds a tracker for the IP *and* for the
    account (``frappe/auth.py:260,269``) and either being locked stops the attempt - that
    pairing is what stops an attacker rotating usernames from one address, or one
    username from many addresses. Ported here; phase 3 left this endpoint unprotected
    entirely, which mattered more than the ``change_password`` gap it did record, because
    this one needs no session to reach.

    No ``@rate_limit`` on top, matching upstream: the tracker already stops brute force,
    and a hard request cap here is what locks out a whole office behind one NAT address.
    """
    username = usr or extra.get("username") or extra.get("email") or ""
    password = pwd or extra.get("password") or ""

    if not username or not password:
        raise ValidationError("Both usr and pwd are required")

    # Frappe lowercases the email to form the User PK, so the tracker key must match or
    # "Ada@x.com" and "ada@x.com" would count as two separate accounts.
    account_key = str(username).strip().lower()
    ip_key = get_client_ip()
    check_login_allowed(ip_key, account_key)

    # Upstream's ``User.find_by_credentials`` (user.py) looks the name up with
    # ``frappe.db.get_value``, and MariaDB's default collation compares case-insensitively,
    # so "Ada@Example.com" logs in as ada@example.com. Django's ModelBackend matches
    # ``USERNAME_FIELD`` exactly, so resolve the stored spelling first. Not a blanket
    # ``.lower()``: the built-in ``Administrator`` keeps its capital.
    from django.contrib.auth import get_user_model

    existing = (
        get_user_model()._default_manager.filter(name__iexact=str(username).strip()).first()
    )
    user = authenticate(
        username=existing.name if existing is not None else username, password=password
    )

    if user is None:
        # Django's ModelBackend rejects inactive users inside authenticate(), so a
        # disabled account and a wrong password both arrive here as None. They are not
        # the same event and must not be counted the same: a disabled account cannot be
        # logged into by anyone, so counting those attempts only serves to keep it locked
        # after an admin re-enables it. Distinguish them by the lookup above.
        if existing is not None and not existing.is_active:
            raise AuthenticationError("User is disabled")

        record_login_failure(ip_key, account_key)
        # Frappe's own wording on a failed desk login.
        raise AuthenticationError("Invalid login credentials")

    record_login_success(ip_key, account_key)

    return issue_tokens(user)


def issue_tokens(user) -> dict:
    """The token pair plus the fields the frontend stores alongside it.

    Extracted in phase 8 so `update_password` returns **the same shape** as `login`.
    `frontend/src/auth/tokens.js:setTokens` reads `access` and `refresh`, and
    `stores/session.js` reads `user` and `full_name` — a set-password page that landed the
    user with a subtly different payload would log them in and then show an empty header.
    """
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
    """Exchange a refresh token for a new access token, rotating the refresh token.

    This endpoint is hand-rolled rather than SimpleJWT's ``TokenRefreshView`` (the path
    and envelope are fixed by the frontend contract), so ``ROTATE_REFRESH_TOKENS`` and
    ``BLACKLIST_AFTER_ROTATION`` are honoured here explicitly - setting them in
    ``SIMPLE_JWT`` alone would have no effect on this code path.

    Rotation makes a refresh token single-use: one captured in transit stops working as
    soon as the legitimate client next refreshes. Safe for the frontend because
    ``jwtRequest.js`` passes the whole response to ``setTokens``, which persists the new
    refresh token (``frontend/src/auth/tokens.js:22-25``).
    """
    token = refresh or extra.get("refresh_token") or ""
    if not token:
        raise ValidationError("refresh token is required")
    try:
        parsed = RefreshToken(token)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from None

    access = str(parsed.access_token)

    if jwt_settings.ROTATE_REFRESH_TOKENS:
        if jwt_settings.BLACKLIST_AFTER_ROTATION:
            try:
                parsed.blacklist()
            except AttributeError:  # pragma: no cover - blacklist app not installed
                pass
        parsed.set_jti()
        parsed.set_exp()
        parsed.set_iat()

    return {"access": access, "refresh": str(parsed)}


@whitelist("frappe.auth.get_logged_user", methods=("GET", "POST"))
def get_logged_user() -> str:
    """``{"message": "user@example.com"}``. Guests get ``"Guest"``, as in Frappe."""
    return get_current_user() or GUEST_USER
