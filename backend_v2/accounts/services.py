"""Account authentication services shared by API routes and later account actions."""

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
