import pytest
from django.db import connection
from django.test import override_settings

from core.exceptions import ValidationError
from core.field_access import encrypted_fields
from core.secrets import (
    PREFIX,
    MissingEncryptionKey,
    decrypt,
    encrypt,
    ensure_key,
    is_encrypted,
)
from tests_support.models import SecuredDocument


KEY = "foundation-field-encryption-key"
SECRET = "Sw0rdfish!"


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_encrypt_decrypt_round_trip_and_idempotence():
    ciphertext = encrypt(SECRET)

    assert ciphertext.startswith(PREFIX)
    assert ciphertext != SECRET
    assert decrypt(ciphertext) == SECRET
    assert encrypt(ciphertext) == ciphertext
    assert is_encrypted(ciphertext)


def test_decrypt_passes_through_an_unprefixed_value():
    assert decrypt(SECRET) == SECRET
    assert decrypt(None) == ""


@override_settings(FIELD_ENCRYPTION_KEY="")
def test_missing_key_uses_the_old_message():
    with pytest.raises(
        MissingEncryptionKey,
        match=(
            r"^FIELD_ENCRYPTION_KEY is not set\. Credentials cannot be stored safely "
            r"without it - see frappe_core/secrets\.py\.$"
        ),
    ):
        ensure_key()


def test_changed_key_uses_the_old_message():
    with override_settings(FIELD_ENCRYPTION_KEY="first-key"):
        ciphertext = encrypt(SECRET)

    with override_settings(FIELD_ENCRYPTION_KEY="second-key"):
        with pytest.raises(
            ValidationError,
            match=(
                r"^Stored credential could not be decrypted\. This usually means "
                r"FIELD_ENCRYPTION_KEY has changed; the credential must be re-entered\.$"
            ),
        ):
            decrypt(ciphertext)


@pytest.mark.django_db
@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_saved_encrypted_field_stays_ciphertext_and_get_password_decrypts(administrator):
    document = SecuredDocument(encrypted_secret=SECRET)
    document.save(user=administrator)

    assert document.encrypted_secret.startswith(PREFIX)
    assert document.encrypted_secret != SECRET
    assert document.get_password("encrypted_secret") == SECRET

    document.refresh_from_db()
    assert document.encrypted_secret.startswith(PREFIX)
    assert document.get_password("encrypted_secret") == SECRET


@pytest.mark.django_db
@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_database_column_holds_ciphertext(administrator):
    document = SecuredDocument(encrypted_secret=SECRET)
    document.save(user=administrator)
    table = connection.ops.quote_name(SecuredDocument._meta.db_table)

    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT encrypted_secret FROM {table} WHERE name = %s",
            [document.name],
        )
        stored = cursor.fetchone()[0]

    assert stored.startswith(PREFIX)
    assert stored != SECRET


def test_get_password_refuses_a_plain_field():
    with pytest.raises(
        ValueError,
        match="'secret' is not an encrypted field on SecuredDocument",
    ):
        SecuredDocument(secret=SECRET).get_password("secret")


def test_encrypted_field_is_also_declared_sensitive():
    assert encrypted_fields(SecuredDocument) <= set(SecuredDocument.SENSITIVE_FIELDS)
