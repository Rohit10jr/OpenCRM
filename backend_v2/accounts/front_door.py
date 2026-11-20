"""The guest endpoints behind the auth screens: forgot password, set password, and (with
CRM Invitation) accept an invitation.

Ported from `backend/crm_app/api/auth_pages.py`, messages verbatim. These are the only
routes a stranger can reach that write something.
"""

from __future__ import annotations

import logging

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import password_reset
from accounts.authentication import bump_token_version
from accounts.models import User
from accounts.services import issue_tokens
from core import mail
from core.exceptions import ValidationError
from core.security import check_login_allowed, record_login_failure, record_login_success

logger = logging.getLogger(__name__)

#: One sentence, whatever happened (CWE-204: no enumeration through differing answers).
GENERIC_RESET_RESPONSE = (
    "If this email is registered with us, we have sent password reset instructions to it. "
    "Please check your inbox."
)
MAX_PASSWORD_SIZE = 512


class WrongPassword(ValidationError):
    """401: `update_password` with a bad `old_password`."""

    http_status_code = 401


class LinkNoLongerValid(ValidationError):
    """410: expired, used or invalid; the frontend reads the status as a dead link."""

    http_status_code = 410


def reset_password(address: str) -> dict:
    """Forgot password. Every branch answers the same sentence, returned once."""
    address = (address or "").strip()
    try:
        if address:
            # iexact: `Administrator` is the one name that is not a lowercased email, so a
            # lowercased lookup would miss it and the exclusion below would never run.
            account = User._default_manager.filter(pk__iexact=address).first()
            if account and account.enabled and account.pk != "Administrator":
                raw_key = password_reset.issue_key(account)
                mail.send_password_reset(
                    to=account.email or account.pk,
                    reset_link=password_reset.reset_link(raw_key),
                    expiry_minutes=password_reset.expiry_minutes(),
                )
    except Exception:
        # A mail server that is down must not reveal whether an address exists.
        logger.warning("password reset failed for a requested address", exc_info=True)
    return {"message": GENERIC_RESET_RESPONSE}


def caller_username(inputs: dict, user) -> str:
    """Who the old-password path acts for: `usr`, `user`, or the token's user,
    lowercased and stripped (old `auth_pages.py:177-190`)."""
    # An anonymous caller is "Guest", as the old session user is
    # (backend/frappe_core/session.py:21,52): the bucket is (IP, guest), not the IP alone
    # that key redemptions share (A-24).
    named = inputs.get("usr") or inputs.get("user") or (user.name if user else "Guest")
    return str(named or "").strip().lower()


def throttle_identity(inputs: dict, user) -> str:
    """The reset path buckets on the IP alone (a guesser would mint a bucket per key);
    the signed-in path on the account (old `auth_pages.py:193-217`)."""
    if inputs.get("key"):
        return ""
    return caller_username(inputs, user)


def _authenticate_with_old_password(inputs, user, old_password, client_ip):
    """Through the login lockout: otherwise a second door checking passwords."""
    username = caller_username(inputs, user)
    if not username or username == "guest":
        raise WrongPassword("Invalid password")
    ip_key = client_ip or ""
    check_login_allowed(ip_key, username)
    account = authenticate(username=username, password=old_password)
    if account is None:
        record_login_failure(ip_key, username)
        raise WrongPassword("Invalid password")
    record_login_success(ip_key, username)
    return account


def _validate_new_password(new_password: str, account) -> None:
    """The first validator message only; the frontend shows one line."""
    try:
        validate_password(new_password, user=account)
    except DjangoValidationError as exc:
        raise ValidationError(
            exc.messages[0] if exc.messages else "Password is not strong enough"
        ) from exc


def _blacklist_outstanding_tokens(account) -> None:
    """`logout_all_sessions`: bump the version (reaches access tokens already issued),
    then blacklist every outstanding refresh token."""
    bump_token_version(account)
    for token in OutstandingToken.objects.filter(user=account):
        try:
            RefreshToken(token.token).blacklist()
        except Exception:  # noqa: BLE001 - already blacklisted or unparseable
            continue


def update_password(inputs: dict, user, client_ip: str | None) -> dict:
    """Set a password by reset key or by old password; answers `login`'s token pair."""
    new_password = inputs.get("new_password") or ""
    key = inputs.get("key") or ""
    old_password = inputs.get("old_password") or ""
    logout_all_sessions = inputs.get("logout_all_sessions") or 0

    if not new_password:
        raise ValidationError("New password is required")
    if len(new_password) > MAX_PASSWORD_SIZE:
        raise ValidationError("Password size exceeded the maximum allowed size.")

    if key:
        resolution = password_reset.resolve_key(key)
        if not resolution.ok:
            raise LinkNoLongerValid(resolution.message)
        account = resolution.user
    elif old_password:
        account = _authenticate_with_old_password(inputs, user, old_password, client_ip)
    else:
        raise ValidationError("Provide either a reset key or your current password")

    _validate_new_password(new_password, account)

    # Claim the key before setting the password: of two racing requests one wins.
    if key and not password_reset.consume_key(account, raw_key=key):
        raise LinkNoLongerValid(password_reset.INVALID_MESSAGE)

    account.set_password(new_password)
    account.save(update_fields=["password"])
    if not key:
        # Any outstanding reset link is stale once the password changed.
        password_reset.consume_key(account)

    if int(logout_all_sessions or 0):
        # Before the new pair is issued, so the pair it answers stays valid.
        _blacklist_outstanding_tokens(account)

    # A disabled account gets its password, then issue_tokens refuses it (upstream bug 61).
    return issue_tokens(account)
