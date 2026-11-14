"""Encryption-at-rest primitives for credential model fields."""

from __future__ import annotations

import base64
import hashlib

from django.conf import settings

from core.exceptions import ValidationError


PREFIX = "enc$v1$"


class MissingEncryptionKey(ValidationError):
    pass


def _fernet():
    from cryptography.fernet import Fernet

    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not key:
        raise MissingEncryptionKey(
            "FIELD_ENCRYPTION_KEY is not set. Credentials cannot be stored safely "
            "without it - see frappe_core/secrets.py."
        )
    raw = str(key).encode()
    try:
        Fernet(raw)
    except Exception:
        raw = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(raw)


def ensure_key() -> None:
    _fernet()


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value) -> str:
    if value in (None, ""):
        return ""
    if is_encrypted(value):
        return value
    token = _fernet().encrypt(str(value).encode()).decode()
    return f"{PREFIX}{token}"


def decrypt(value) -> str:
    if value in (None, ""):
        return ""
    if not is_encrypted(value):
        return str(value)

    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(value[len(PREFIX) :].encode()).decode()
    except InvalidToken:
        raise ValidationError(
            "Stored credential could not be decrypted. This usually means "
            "FIELD_ENCRYPTION_KEY has changed; the credential must be re-entered."
        ) from None
