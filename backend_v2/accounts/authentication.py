"""JWT authentication with per-user token revocation."""

import secrets

from django.db.models import F
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

TOKEN_VERSION_CLAIM = "token_version"


def new_token_version() -> int:
    """PE-32 (ACCOUNTS §10.5): every account starts at a random version, so a token is
    valid for one account even when a later account takes the same name. At most
    2**62, so a bump never overflows the bigint column."""
    return secrets.randbelow(2**62) + 1


def token_version_of(token) -> int:
    return int(token.get(TOKEN_VERSION_CLAIM, 0) or 0)


def is_current(token, user) -> bool:
    return token_version_of(token) == user.token_version


def bump_token_version(user) -> None:
    type(user)._default_manager.filter(pk=user.pk).update(
        token_version=F("token_version") + 1
    )
    user.refresh_from_db(fields=["token_version"])


def revoke_all_tokens(user) -> None:
    """Blacklist every outstanding refresh token of ``user`` (shared by
    `logout_all_sessions` and the User rename, ACCOUNTS §10.4). It does not bump the
    version; each caller decides that."""
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from rest_framework_simplejwt.tokens import RefreshToken

    for token in OutstandingToken.objects.filter(user=user):
        try:
            RefreshToken(token.token).blacklist()
        except Exception:  # noqa: BLE001 - already blacklisted or unparseable
            continue


class VersionedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not is_current(validated_token, user):
            raise InvalidToken(
                {
                    "detail": _("Given token not valid for any token type"),
                    "messages": [
                        {
                            "token_class": type(validated_token).__name__,
                            "token_type": getattr(validated_token, "token_type", ""),
                            "message": _("Token has been revoked"),
                        }
                    ],
                }
            )
        return user
