"""Encryption at rest for credential fields.

Stage 3 of the A3 work. `SENSITIVE_FIELDS` kept credentials out of responses and the
filter guard kept them out of questions, but the value was still sitting in the row in
plain text - readable by anyone with database access, a backup, or a log that captured a
query.

Upstream does not have this problem, and not because it checks anything: Frappe declares
``password`` as a ``Password`` **fieldtype**, and those never reach the document table at
all. ``set_encrypted_password`` (``frappe/utils/password.py:52``) writes ``encrypt(pwd)``
into a separate ``__Auth`` table keyed by ``(doctype, name, fieldname)``. There is no
column on ``tabEmail Account`` to read, filter, or leak.

### Why we encrypt in place rather than copying the `__Auth` split

The security property that matters is *the plaintext is not in the database*, and both
designs deliver it. The separate table additionally means "no column to filter", which we
get from the Stage 1 filter guard instead.

What differs is cost and risk. A second table means a new model, a join on every read, a
write path that has to stay in step with the document's own lifecycle, and a migration
that moves data between tables. Encrypting in place is a field-level change with a
data-only migration. For a port whose remaining risk is concentrated elsewhere, the
cheaper design that reaches the same property is the better trade - and it leaves the
`__Auth` shape available later if a reason for it appears.

### The key

``FIELD_ENCRYPTION_KEY``, deliberately **not** derived from ``SECRET_KEY``. Rotating
``SECRET_KEY`` is a routine, documented Django operation - it invalidates sessions and
signed cookies, both disposable. If credentials hung off it, that routine operation would
silently destroy every stored mail password, and the failure would surface days later as
"invitations stopped arriving".

Losing this key means the stored credentials are unrecoverable and have to be re-entered.
That is the correct failure: it is what "encrypted at rest" means.
"""

from __future__ import annotations

import base64
import hashlib

from django.conf import settings

from frappe_core.exceptions import ValidationError

#: Marks a stored value as ciphertext this module produced. Values written before Stage 3
#: carry no prefix, which is what lets :func:`decrypt` recognise and pass through a
#: not-yet-migrated row instead of raising on it.
PREFIX = "enc$v1$"


class MissingEncryptionKey(ValidationError):
    """Raised on an attempt to encrypt with no key configured."""


def _fernet():
    from cryptography.fernet import Fernet

    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    if not key:
        raise MissingEncryptionKey(
            "FIELD_ENCRYPTION_KEY is not set. Credentials cannot be stored safely "
            "without it - see frappe_core/secrets.py."
        )
    # A Fernet key is 32 url-safe base64 bytes. Accept either that directly or any
    # passphrase, hashed to the right shape, so an operator setting this by hand does not
    # have to know Fernet's encoding rules to get a working deployment.
    raw = str(key).encode()
    try:
        Fernet(raw)
    except Exception:
        raw = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(raw)


def ensure_key() -> None:
    """Raise :class:`MissingEncryptionKey` now if nothing could be encrypted later.

    For a caller about to do something slow or outward-facing on the way to storing a
    credential - ``create_email_account`` logs in to the mail server first - so that a
    server with no key says so before the login rather than after it (FINDINGS.md 65).
    """
    _fernet()


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value) -> str:
    """Encrypt ``value``. Idempotent - an already-encrypted value is returned unchanged.

    Idempotence is load-bearing: ``save()`` runs on every write, including writes that do
    not touch the credential, and double-encrypting would leave a value that decrypts to
    ciphertext.
    """
    if value in (None, ""):
        return ""
    if is_encrypted(value):
        return value
    token = _fernet().encrypt(str(value).encode()).decode()
    return f"{PREFIX}{token}"


def decrypt(value) -> str:
    """Decrypt ``value``. A value with no prefix is returned as-is.

    That pass-through is what makes the migration safe to run on a live database: rows
    written before Stage 3 hold plaintext, and mail has to keep working between the
    deploy and the migration rather than failing in between.
    """
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


class EncryptedFieldsMixin:
    """Encrypt ``ENCRYPTED_FIELDS`` on save; read them back with :meth:`get_password`.

    The attribute holds ciphertext once saved, so **nothing should read it directly** -
    ``account.password`` is a token, ``account.get_password()`` is the credential. That
    asymmetry is deliberate: it makes an accidental read produce something obviously
    unusable rather than something that quietly works in development, where the field may
    still hold pre-migration plaintext.
    """

    ENCRYPTED_FIELDS: tuple[str, ...] = ()

    def save(self, *args, **kwargs):
        for fieldname in self.ENCRYPTED_FIELDS:
            current = getattr(self, fieldname, None)
            if current:
                setattr(self, fieldname, encrypt(current))
        return super().save(*args, **kwargs)

    def get_password(self, fieldname: str = "password") -> str:
        if fieldname not in self.ENCRYPTED_FIELDS:
            raise ValueError(f"{fieldname!r} is not an encrypted field on {type(self).__name__}")
        return decrypt(getattr(self, fieldname, ""))
