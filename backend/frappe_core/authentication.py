"""Port only: revoking access tokens that have already been issued (KNOWN_ISSUES §6).

Upstream has no counterpart — it uses server-side sessions, which die the moment they are
deleted. This port uses JWTs (phase 0's sanctioned deviation), and an access token was
checked by signature alone, so `logout_all_sessions` and a password change left every
issued one working until it expired.

The user carries an integer ``token_version``. ``issue_tokens`` writes it into the refresh
token as a claim, SimpleJWT's ``RefreshToken.access_token`` copies it into each access
token, and every place a token authenticates compares it with the user row it has already
loaded. Bumping the version revokes every token issued before the bump.

An integer rather than a ``password_changed_at`` timestamp: ``iat`` has one-second
resolution, so a token issued in the same second as the change would slip through.
"""

from __future__ import annotations

from django.db.models import F
from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

#: The claim's name in both tokens.
TOKEN_VERSION_CLAIM = "token_version"


def token_version_of(token) -> int:
    """The version a token was issued at. A token from before this change has no claim,
    and counts as 0 so that deploying it does not sign everyone out."""
    return int(token.get(TOKEN_VERSION_CLAIM, 0) or 0)


def is_current(token, user) -> bool:
    return token_version_of(token) == user.token_version


def bump_token_version(user) -> None:
    """Revoke every token issued to ``user`` so far.

    ``F()`` so two bumps arriving together both count. Reloads the field afterwards: the
    caller usually issues a fresh pair next, and it must carry the new version.
    """
    type(user)._default_manager.filter(pk=user.pk).update(
        token_version=F("token_version") + 1
    )
    user.refresh_from_db(fields=["token_version"])


class VersionedJWTAuthentication(JWTAuthentication):
    """SimpleJWT's authentication, refusing a token whose version is stale.

    The check sits in ``get_user`` so the WebSocket consumer and the file route, which call
    ``get_user`` directly rather than ``authenticate``, get it too. It reads the user row
    ``get_user`` has just loaded, so it costs no query.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not is_current(validated_token, user):
            # The shape of any other dead token (`get_validated_token`), so the frontend's
            # refresh-then-login path (`frontend/src/auth/jwtRequest.js`) treats it alike.
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
