"""Guard every installed model's credential, child, and module declarations."""

import pytest
from django.apps import apps

from core.doctypes import is_child_table
from core.field_access import encrypted_fields, restricted_fields, sensitive_fields


CREDENTIAL_HINTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "access_key",
    "auth",
    "credential",
)
TRUE_SECRET_HINTS = ("password", "secret", "token")

# Fields that only resemble credentials, with the reason that each is harmless.
REVIEWED_NOT_CREDENTIALS = {
    ("configuration.EmailAccount", "awaiting_password"): (
        "A boolean meaning the password will be entered later; it holds no secret and is "
        "restricted to managers with the rest of the mail-server description."
    ),
    ("configuration.EmailAccount", "no_smtp_authentication"): (
        "A boolean meaning the relay takes no login; it holds no secret and is restricted "
        "to managers with the rest of the mail-server description."
    ),
    ("configuration.EmailAccount", "ascii_encode_password"): (
        "A boolean choosing how the password is encoded for the server; it holds no secret "
        "and says nothing about the password's value."
    ),
    ("configuration.UserEmail", "awaiting_password"): (
        "A boolean fetched from the user's Email Account; it holds no secret and only says "
        "whether that account's password is still to be entered."
    ),
    ("configuration.UserEmail", "used_oauth"): (
        "A boolean that stays off, since this backend has no OAuth mail; it holds no token "
        "or other credential material."
    ),
    ("accounts.User", "last_reset_password_key_generated_on"): (
        "This is the timestamp at which the current reset key was issued, not the key "
        "itself. It remains sensitive because exposing it reveals reset activity."
    ),
    ("accounts.User", "token_version"): (
        "This integer is a revocation counter copied into signed tokens, not credential "
        "material. It remains sensitive so a client cannot restore an older version."
    ),
    ("tests_support.SecuredDocument", "secret"): (
        "This deliberately plain test value proves that SENSITIVE_FIELDS alone hides a "
        "field; it is fixture data and is never used as authenticating material."
    ),
    ("token_blacklist.BlacklistedToken", "token"): (
        "This one-to-one relation identifies an OutstandingToken row; it does not store "
        "a second token value or any independently usable credential material."
    ),
}

# Real credentials that are intentionally protected by access rather than encryption.
REVIEWED_RESTRICTED_ONLY = {
    ("configuration.EmailAccount", "api_key"): (
        "The Frappe Mail API key, stored as plain restricted text as in backend/; its "
        "secret half, api_secret, is encrypted and sensitive. Managers read the key back on "
        "the Email Account screen; everyone else gets it absent and value/ refused."
    ),
    ("configuration.FCRMSettings", "access_key"): (
        "The exchange-rate provider key, stored as plain restricted text as in backend/. "
        "Managers read it back on the Dashboard settings screen (DashboardSettings.vue:157), "
        "so it cannot be write-only; everyone else gets it absent and value/ refused."
    ),
    ("token_blacklist.OutstandingToken", "token"): (
        "SimpleJWT owns this server-only model and requires the encoded token for its "
        "blacklist checks. The model has no CRM resource route, so clients cannot read, "
        "filter, or write the field through the API."
    ),
}

# One-way hashes are stronger at rest where the original value need not be recovered.
REVIEWED_HASHED_AT_REST = {
    ("accounts.User", "password"): (
        "Django's AbstractBaseUser stores a one-way password hash and password checks do "
        "not recover the original value. The global field rule also hides it."
    ),
    ("accounts.User", "reset_password_key"): (
        "The reset flow stores sha256(key); only the emailed raw key can be redeemed, "
        "and the server compares its digest instead of recovering the original."
    ),
}


def _matches(fieldname, hints):
    lowered = fieldname.lower()
    return any(hint in lowered for hint in hints)


def _credential_fields():
    for model in apps.get_models():
        for field in model._meta.get_fields():
            if getattr(field, "concrete", False) and _matches(
                field.name, CREDENTIAL_HINTS
            ):
                yield model._meta.label, field.name, model


def _reviewed_fields():
    return (
        set(REVIEWED_NOT_CREDENTIALS)
        | set(REVIEWED_RESTRICTED_ONLY)
        | set(REVIEWED_HASHED_AT_REST)
    )


def test_every_credential_shaped_field_is_sensitive_or_excused():
    undeclared = [
        (label, fieldname)
        for label, fieldname, model in _credential_fields()
        if fieldname not in sensitive_fields(model)
        and (label, fieldname) not in _reviewed_fields()
    ]

    assert not undeclared, (
        f"Credential-shaped fields with no declaration: {undeclared}. "
        "Add the field to SENSITIVE_FIELDS or record a reviewed exception with a reason."
    )


def test_true_secrets_are_both_sensitive_and_encrypted():
    encrypted_not_sensitive = []
    sensitive_not_encrypted = []

    for model in apps.get_models():
        label = model._meta.label
        concrete = {
            field.name
            for field in model._meta.get_fields()
            if getattr(field, "concrete", False)
        }
        sensitive = sensitive_fields(model)
        encrypted = encrypted_fields(model)
        for reviewed_label, fieldname in REVIEWED_RESTRICTED_ONLY:
            if reviewed_label == label:
                assert not getattr(model, "DOCTYPE", None) or fieldname in (
                    restricted_fields(model)
                ), f"{label}.{fieldname} is no longer restricted-only"
        encrypted_not_sensitive.extend(
            (label, fieldname) for fieldname in sorted(encrypted - sensitive)
        )
        sensitive_not_encrypted.extend(
            (label, fieldname)
            for fieldname in sorted((sensitive & concrete) - encrypted)
            if _matches(fieldname, TRUE_SECRET_HINTS)
            and (label, fieldname) not in REVIEWED_NOT_CREDENTIALS
            and (label, fieldname) not in REVIEWED_RESTRICTED_ONLY
            and (label, fieldname) not in REVIEWED_HASHED_AT_REST
        )

    assert not encrypted_not_sensitive, (
        "Encrypted fields served or filterable as ciphertext: "
        f"{encrypted_not_sensitive}. Add them to SENSITIVE_FIELDS."
    )
    assert not sensitive_not_encrypted, (
        "Sensitive secrets stored without encryption: "
        f"{sensitive_not_encrypted}. Use an encrypted field or record why the value is "
        "hashed at rest or deliberately restricted-only."
    )


def test_every_child_model_declares_child_fields():
    missing = sorted(
        model._meta.label
        for model in apps.get_models()
        if is_child_table(model) and "CHILD_FIELDS" not in model.__dict__
    )

    assert not missing, f"Child models without an explicit CHILD_FIELDS tuple: {missing}"


def test_installed_models_are_defined_in_their_apps_models_module():
    misplaced = []
    for model in apps.get_models():
        models_module = f"{model._meta.app_config.name}.models"
        if model.__module__ != models_module and not model.__module__.startswith(
            f"{models_module}."
        ):
            misplaced.append((model._meta.label, model.__module__))

    assert not misplaced, (
        "Installed models defined outside their app's models module: "
        f"{sorted(misplaced)}. Put test-only models under isolate_apps."
    )


def test_reviewed_exception_fields_still_exist():
    known = {(label, fieldname) for label, fieldname, _model in _credential_fields()}
    dangling = sorted(_reviewed_fields() - known)

    assert not dangling, f"Reviewed credential fields no longer exist: {dangling}"


@pytest.mark.parametrize("key", sorted(_reviewed_fields()))
def test_each_exception_carries_a_real_reason(key):
    reason = (
        REVIEWED_NOT_CREDENTIALS.get(key)
        or REVIEWED_RESTRICTED_ONLY.get(key)
        or REVIEWED_HASHED_AT_REST[key]
    )

    assert len(reason) > 40, f"{key}: record a real reason, not {reason!r}"


def test_known_credentials_remain_covered():
    fields = {
        (label, fieldname): model
        for label, fieldname, model in _credential_fields()
    }
    expected = {
        ("accounts.User", "password"),
        ("accounts.User", "reset_password_key"),
        ("accounts.User", "token_version"),
        ("configuration.EmailAccount", "api_key"),
        ("configuration.EmailAccount", "api_secret"),
        ("configuration.EmailAccount", "password"),
        ("configuration.FCRMSettings", "access_key"),
        ("tests_support.SecuredDocument", "secret"),
        ("tests_support.SecuredDocument", "encrypted_secret"),
    }

    assert not expected - fields.keys(), (
        f"Known credential-shaped fields disappeared: {sorted(expected - fields.keys())}"
    )
    for key in expected:
        model = fields[key]
        assert key in _reviewed_fields() or key[1] in sensitive_fields(model), (
            f"{key[0]}.{key[1]} lost its credential declaration"
        )
