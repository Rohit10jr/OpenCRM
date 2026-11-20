"""Account authentication services shared by API routes and later account actions."""

import zoneinfo
from functools import lru_cache

from django.contrib.auth import authenticate, get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.authentication import TOKEN_VERSION_CLAIM, token_version_of
from core.exceptions import AuthenticationError, ValidationError
from core.security import (
    check_login_allowed,
    record_login_failure,
    record_login_success,
)


def login(username: str = "", password: str = "", client_ip: str | None = None) -> dict:
    if not username or not password:
        raise ValidationError("Both usr and pwd are required")

    account_key = str(username).strip().lower()
    ip_key = client_ip or ""
    check_login_allowed(ip_key, account_key)

    users = get_user_model()._default_manager
    typed = str(username).strip()
    existing = users.filter(name=typed).first() or (
        users.filter(name__iexact=typed).order_by("name").first()
    )
    user = authenticate(
        username=existing.name if existing is not None else username,
        password=password,
    )
    if user is None:
        record_login_failure(ip_key, account_key)
        if existing is not None and not existing.is_active and existing.check_password(password):
            raise AuthenticationError("User disabled or missing")
        raise AuthenticationError("Invalid login credentials")

    record_login_success(ip_key, account_key)
    return issue_tokens(user)


def issue_tokens(user) -> dict:
    if not user.is_active:
        raise AuthenticationError("User disabled or missing")
    refresh = RefreshToken.for_user(user)
    refresh[TOKEN_VERSION_CLAIM] = user.token_version
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "message": "Logged In",
        "home_page": "/crm",
        "full_name": user.full_name or user.name,
        "user": user.name,
    }


def logout(refresh: str = "") -> dict:
    if refresh:
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            pass
    return {"message": "Logged Out"}


def refresh_token(refresh: str = "") -> dict:
    if not refresh:
        raise ValidationError("refresh token is required")
    try:
        parsed = RefreshToken(refresh)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from None

    user_id = parsed.get(jwt_settings.USER_ID_CLAIM)
    current = (
        get_user_model()
        ._default_manager.filter(**{jwt_settings.USER_ID_FIELD: user_id})
        .values_list("token_version", flat=True)
        .first()
    )
    if current is None or token_version_of(parsed) != current:
        raise AuthenticationError("Token is invalid or expired")

    access = str(parsed.access_token)
    if jwt_settings.ROTATE_REFRESH_TOKENS:
        if jwt_settings.BLACKLIST_AFTER_ROTATION:
            parsed.blacklist()
        parsed.set_jti()
        parsed.set_exp()
        parsed.set_iat()
        parsed.outstand()
    return {"access": access, "refresh": str(parsed)}


def change_password(user, old_password: str = "", new_password: str = "") -> str:
    """`crm.api.user.change_password` (old `crm_app/api/user.py:54-107`), messages
    verbatim. The route is not guest, so the old Guest branch cannot be reached.

    Beside the endpoint's flat limit, an account lockout counts wrong current passwords
    against this account and resets on success.
    """
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError

    from core.security import LoginAttemptTracker

    tracker = LoginAttemptTracker(user.name)
    if not tracker.is_user_allowed():
        raise ValidationError("Too many failed attempts. Please try again after some time.")

    if old_password == new_password:
        raise ValidationError(
            "New password cannot be the same as current password. "
            "Please choose a different password."
        )

    if not user.check_password(old_password):
        tracker.add_failure_attempt()
        raise ValidationError("Incorrect current password. Please try again.")

    tracker.add_success_attempt()

    try:
        validate_password(new_password, user=user)
    except DjangoValidationError as exc:
        suggestions = " ".join(exc.messages)
        raise ValidationError(f"Password is too weak. {suggestions}".strip()) from exc

    user.set_password(new_password)
    user.save(update_fields=["password"])
    return "Password Updated Successfully"


# Fixed-offset and legacy families `pytz.common_timezones` leaves out (old desk.py).
_UNCOMMON_TIMEZONE_PREFIXES = ("Etc/", "SystemV/", "posix/", "right/")


@lru_cache(maxsize=1)
def timezones() -> list[str]:
    """`get_timezones`' list (old `crm_app/api/desk.py:_get_timezones`): upstream's
    `sorted(pytz.common_timezones)`, approximated from `zoneinfo` without adding pytz —
    `Area/Location` names plus UTC and GMT, cached for the process."""
    names = {
        name
        for name in zoneinfo.available_timezones()
        if "/" in name and not name.startswith(_UNCOMMON_TIMEZONE_PREFIXES)
    }
    names.update({"UTC", "GMT"})
    return sorted(names)


def user_signature(user) -> str | None:
    """`crm.api.get_user_signature` (old `crm_app/api/misc.py:42-72`): the user's own
    signature, else the default outgoing Email Account's, wrapped. The fallback comes
    through `core.mail`, so this app does not import configuration."""
    from core.mail import default_signature

    signature = user.email_signature or default_signature()
    if not signature:
        return None
    return f'<br><p class="signature">{signature}</p>'
