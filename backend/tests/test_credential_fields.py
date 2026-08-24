"""A field whose name looks like a credential must say so.

`tests/test_route_surface.py` forces a decision about **who can reach** a doctype. Nothing
forced one about **what is inside it** - and the two failures are different. A3 was a mail
password stored in plain text and recoverable through filters; A4 was an FX-provider key
sitting on a record every user reads. Both were found by hand, months after the field was
written.

Phase 7 is the credential-heavy phase - ERPNext API keys, Meta long-lived page tokens,
webhook signing secrets - so this exists before it starts rather than after.

**It matches on the field's name, which is a heuristic and deliberately so.** A name is
what a reviewer scans for, and a name is what the author chose while thinking about the
credential. It cannot know that `subdomain` is harmless or that `account_sid` is half a
credential pair, and it does not try: an exception list carries that judgement, in writing.

The test does not decide. It refuses to let the decision be skipped.
"""

import pytest

from frappe_core import registry
from frappe_core.field_security import restricted_fields, sensitive_fields

#: Substrings that make a field name look like a secret. Kept narrow on purpose - a
#: pattern that matches half the schema teaches people to add exceptions without reading.
CREDENTIAL_HINTS = ("password", "secret", "token", "api_key", "auth", "credential")

#: Names that match a hint and are **not** credentials, each with the reason. Adding a
#: line here is the point of the test: it is cheap, and it leaves the judgement on record
#: where the next person can disagree with it.
REVIEWED_NOT_CREDENTIALS = {
    # `frappe_platform.User`
    ("User", "password"): (
        "Django's own hashed password column, managed by AbstractBaseUser. Already in "
        "GLOBAL_SENSITIVE_FIELDS, so it never reaches the wire; listed here because the "
        "global set is applied by name rather than declared per model."
    ),
    ("Email Account", "awaiting_password"): (
        "A **boolean flag**, not a password: upstream's 'save the account now, the user "
        "will supply credentials later' switch (`email_account.py:157`). Ported in A4 as "
        "one of three escape hatches around credential validation."
    ),
    ("User", "last_reset_password_key_generated_on"): (
        "A **timestamp**, not a secret: when the current reset key was issued. Matched on "
        "the name alone, which is the heuristic doing its job. It is in SENSITIVE_FIELDS "
        "anyway, for a different reason — `User` reads are open to every authenticated "
        "caller (SECURITY_MODEL divergence #5), so a visible issue time would tell any "
        "colleague which accounts have a live reset link and when."
    ),
    ("Email Account", "ascii_encode_password"): (
        "A **boolean flag**, not a password: upstream's switch for ASCII-encoding the "
        "password before handing it to the SMTP library. Caught by the name on this "
        "test's first run, which is the heuristic working rather than failing."
    ),
}


def _credential_shaped(fieldname: str) -> bool:
    lowered = fieldname.lower()
    return any(hint in lowered for hint in CREDENTIAL_HINTS)


def _declared(model, fieldname: str) -> bool:
    """Declared in any of the three that keep a value away from an ordinary caller."""
    encrypted = set(getattr(model, "ENCRYPTED_FIELDS", ()) or ())
    return (
        fieldname in sensitive_fields(model)
        or fieldname in restricted_fields(model)
        or fieldname in encrypted
    )


def _credential_fields():
    """(doctype, fieldname, model) for every credential-shaped field in the registry."""
    for doctype in sorted(registry.all_doctypes()):
        model = registry.get_entry(doctype).model
        for field in model._meta.get_fields():
            if not getattr(field, "concrete", False) or field.is_relation:
                continue
            if _credential_shaped(field.name):
                yield doctype, field.name, model


def test_every_credential_shaped_field_is_declared_or_excused():
    """Registering a credential without declaring it fails here.

    The message is written for whoever hits it - somebody who added a model and has no
    idea why the build broke - so it names the field, the three declarations and the
    escape hatch, rather than asserting a bare False.
    """
    undeclared = [
        (doctype, fieldname)
        for doctype, fieldname, model in _credential_fields()
        if not _declared(model, fieldname)
        and (doctype, fieldname) not in REVIEWED_NOT_CREDENTIALS
    ]

    assert not undeclared, (
        f"Credential-shaped fields with no declaration: {undeclared}.\n"
        "Registering a doctype publishes it: every field is readable, filterable and "
        "writable through /api/resource/ unless something says otherwise.\n"
        "  - SENSITIVE_FIELDS  keeps it off the wire, out of `fields=`, out of filters\n"
        "  - ENCRYPTED_FIELDS  keeps it out of the database in plain text\n"
        "  - RESTRICTED_FIELDS makes it manager-only\n"
        "If it only looks like a credential, add it to REVIEWED_NOT_CREDENTIALS with the "
        "reason. See specs/SECURITY_MODEL.md and specs/AS_BUILT.md."
    )


#: Names that are a secret outright, rather than merely identifying material. These need
#: **both** declarations: off the wire *and* out of the database in plain text.
TRUE_SECRET_HINTS = ("password", "secret", "token")

#: Genuine secrets that are deliberately **restricted rather than hidden**, with the
#: reason. Distinct from `REVIEWED_NOT_CREDENTIALS`, which is for fields that only look
#: like credentials - conflating the two would let a real secret hide behind "not a
#: credential".
REVIEWED_RESTRICTED_ONLY = {
    ("CRM Exotel Settings", "webhook_verify_token"): (
        "A real secret - it is what proves an inbound webhook came from Exotel - and "
        "deliberately readable by a manager, because it has to be entered at the provider "
        "end too and there is no way to recover it otherwise. Upstream leaves it plain "
        "`Data` readable by the same roles; RESTRICTED_FIELDS is already stricter. "
        "Encrypting it would serve a manager ciphertext, since the serializer has no "
        "decrypt-for-privileged-callers path and building one for a single field is not "
        "worth the machinery."
    ),
}

#: Secrets **hashed** at rest rather than encrypted — a third answer the first two lists
#: could not express, added in phase 8.
#:
#: Encryption is reversible by design: an encrypted reset key is still a working key to
#: whoever reaches the encryption key. A one-way hash is not, so hashing is **stronger**
#: here, not a weaker substitute. It is only available for a value the server never needs to
#: read back — it compares, it does not recover — which is exactly a reset key and is not
#: true of an SMTP password or an API secret.
#:
#: Kept separate from the two lists above on purpose. `REVIEWED_NOT_CREDENTIALS` would be a
#: lie (it is a credential) and `REVIEWED_RESTRICTED_ONLY` would be worse (it says a manager
#: may read it, and nobody may). An entry here still has to be in `SENSITIVE_FIELDS`; the
#: test below enforces that, so this excuses one requirement rather than both.
REVIEWED_HASHED_AT_REST = {
    ("User", "reset_password_key"): (
        "Stored as sha256(key); the raw value exists only in the emailed link "
        "(frappe_core/password_reset.py, porting user.py:385-387). Encrypting a hash would "
        "add nothing - the plaintext is already unrecoverable, which is more than "
        "encryption gives - and the server never needs the original back, only a "
        "comparison. A database dump yields nothing redeemable either way."
    ),
}


def test_a_true_secret_is_both_hidden_and_encrypted():
    """The two are independent, and needing only one of them is how A3 happened.

    The mail password was in SENSITIVE_FIELDS from phase 1 and sat in the row in plain
    text until phase 4's review - hidden from callers, readable in any database dump,
    backup or logged query.

    The converse fails too, and this test missed it on its first draft: a field that is
    encrypted but *not* sensitive is served over the API as ciphertext and remains
    filterable. Better than plaintext, and not the same as protected. Caught by
    deliberately removing a SENSITIVE_FIELDS entry and finding the suite still green.

    Only true secrets are held to this. An identifier that is merely restricted - Twilio's
    `api_key`, which upstream marks permlevel 1 - is not something to encrypt.
    """
    missing_hidden, missing_encrypted = [], []

    for doctype, fieldname, model in _credential_fields():
        if (doctype, fieldname) in REVIEWED_NOT_CREDENTIALS:
            continue
        if (doctype, fieldname) in REVIEWED_RESTRICTED_ONLY:
            assert fieldname in restricted_fields(model), (
                f"{doctype}.{fieldname} is excused as restricted-only but is not in "
                "RESTRICTED_FIELDS - the excuse and the code disagree"
            )
            continue
        if not any(hint in fieldname.lower() for hint in TRUE_SECRET_HINTS):
            continue
        if fieldname not in sensitive_fields(model):
            missing_hidden.append((doctype, fieldname))
        # A hashed secret is excused from ENCRYPTED_FIELDS and **not** from
        # SENSITIVE_FIELDS: the check above still applies to it, so this excuses one
        # requirement rather than both.
        if (doctype, fieldname) in REVIEWED_HASHED_AT_REST:
            continue
        if fieldname not in set(getattr(model, "ENCRYPTED_FIELDS", ()) or ()):
            missing_encrypted.append((doctype, fieldname))

    assert not missing_hidden, (
        f"A secret not in SENSITIVE_FIELDS: {missing_hidden}. Encrypting it is not enough - "
        "without this it is served as ciphertext and stays filterable."
    )
    assert not missing_encrypted, (
        f"Hidden from the wire but stored in plain text: {missing_encrypted}. "
        "Add them to ENCRYPTED_FIELDS (frappe_core.secrets) and write a data migration "
        "for existing rows - see frappe_platform/migrations/0005."
    )


def test_the_exception_list_does_not_go_stale():
    """An excused field that has since been renamed or removed leaves a dangling entry,
    and a dangling entry makes the list look considered when it is not."""
    known = {(dt, name) for dt, name, _ in _credential_fields()}
    listed = (
        set(REVIEWED_NOT_CREDENTIALS)
        | set(REVIEWED_RESTRICTED_ONLY)
        | set(REVIEWED_HASHED_AT_REST)
    )
    dangling = sorted(listed - known)

    assert not dangling, f"Listed as reviewed but no longer exist: {dangling}"


@pytest.mark.parametrize(
    "key", sorted(set(REVIEWED_NOT_CREDENTIALS) | set(REVIEWED_RESTRICTED_ONLY))
)
def test_each_exception_carries_a_real_reason(key):
    """Guards the quality of the excuses. A one-word placeholder would let the list look
    complete while meaning nothing - the failure mode the whole file exists to prevent."""
    reason = REVIEWED_NOT_CREDENTIALS.get(key) or REVIEWED_RESTRICTED_ONLY[key]
    assert len(reason) > 40, f"{key}: say why it is not a credential, not {reason!r}"


def test_the_known_credentials_are_still_covered():
    """The four this was built from, pinned so a refactor cannot quietly drop one."""
    expected = {
        ("Email Account", "password"),
        ("Email Account", "api_secret"),
        ("CRM Twilio Settings", "api_secret"),
        ("CRM Exotel Settings", "api_token"),
    }
    for doctype, fieldname in expected:
        model = registry.get_entry(doctype).model
        assert _declared(model, fieldname), f"{doctype}.{fieldname} lost its declaration"
