"""Password-reset keys: issue, verify, consume.

Ported from `backend/frappe_core/password_reset.py` (upstream `user.py:383`, `:945`,
`:828`). Three properties hold:

- **Stored hashed.** `sha256(key)` is in the row; the raw key exists only in the emailed
  link. Hashed, not encrypted: an encrypted key is still a working key to whoever holds
  the encryption key.
- **Single use**, cleared by one conditional update of both columns.
- **Two failure messages, and only two**, upstream's: an expired link, and "used before
  or invalid", which merges the two on purpose so a key cannot be probed.

Expiry zero means 60 minutes, not "never" (the old backend's divergence #34, kept).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from accounts.models import User

EXPIRED_MESSAGE = "The reset password link has been expired"
INVALID_MESSAGE = "The reset password link has either been used before or is invalid"
KEY_BYTES = 32
DEFAULT_EXPIRY_MINUTES = 60


def expiry_minutes() -> int:
    configured = getattr(
        settings, "PASSWORD_RESET_LINK_EXPIRY_MINUTES", DEFAULT_EXPIRY_MINUTES
    )
    try:
        minutes = int(configured)
    except (TypeError, ValueError):
        return DEFAULT_EXPIRY_MINUTES
    return minutes if minutes > 0 else DEFAULT_EXPIRY_MINUTES


def hash_key(raw_key: str) -> str:
    """Plain SHA-256: the input is 256 random bits, so a slow KDF protects nothing."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def issue_key(user) -> str:
    """Store the hash of a fresh key and return the raw key, the only time it exists.
    An update, not a save: a guest endpoint calls it. A second key replaces the first."""
    raw_key = secrets.token_urlsafe(KEY_BYTES)
    User._default_manager.filter(pk=user.pk).update(
        reset_password_key=hash_key(raw_key),
        last_reset_password_key_generated_on=timezone.now(),
    )
    return raw_key


@dataclass
class KeyResolution:
    user: object | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.user is not None and self.message is None


def resolve_key(raw_key: str) -> KeyResolution:
    """Expiry is checked after the lookup, as upstream does."""
    if not raw_key:
        return KeyResolution(message=INVALID_MESSAGE)
    user = User._default_manager.filter(reset_password_key=hash_key(raw_key)).first()
    if user is None:
        return KeyResolution(message=INVALID_MESSAGE)
    issued = user.last_reset_password_key_generated_on
    if issued is None:
        return KeyResolution(message=INVALID_MESSAGE)
    if timezone.now() > issued + timedelta(minutes=expiry_minutes()):
        return KeyResolution(message=EXPIRED_MESSAGE)
    return KeyResolution(user=user)


def consume_key(user, raw_key: str | None = None) -> bool:
    """Clear both columns; with `raw_key`, only while the key is still that one, so of
    two racing redemptions exactly one wins. Returns whether this call cleared it."""
    rows = User._default_manager.filter(pk=user.pk)
    if raw_key is not None:
        rows = rows.filter(reset_password_key=hash_key(raw_key))
    return bool(
        rows.update(reset_password_key="", last_reset_password_key_generated_on=None)
    )


def reset_link(raw_key: str) -> str:
    """A frontend route, not an API path."""
    base = (getattr(settings, "FRONTEND_ORIGIN", "") or "").rstrip("/")
    return f"{base}/crm/update-password?key={raw_key}"
