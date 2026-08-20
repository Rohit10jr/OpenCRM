"""A3 - Email Account: who may change it, who may see what, and where the secret lives.

Three stages, three separate properties, and none of them subsumes the others:

* **Stage 2** - a row rule. Any authenticated caller could repoint ``smtp_server`` at a
  host they controlled, or delete the account outright. That is not credential theft; it
  is **redirecting the mail**, invitation links included, and it needs no password.
* **Stage 3** - encryption at rest. The password was plaintext in the row.
* **Stage 4** - restricted fields. The record has to stay readable (the Profile screen
  lists accounts), so the infrastructure on it is narrowed instead.

Upstream needs none of this: it withholds the whole record from anyone below System
Manager, and keeps the password out of the document table entirely (`__Auth`). It also,
in consequence, leaves its own Profile "send from" picker empty for ordinary users. We
keep that working, which is what makes stage 4 necessary.
"""

import pytest

from frappe_core import secrets
from frappe_core.session import session_user
from frappe_platform.models import EmailAccount

pytestmark = pytest.mark.django_db

SECRET = "Sw0rdfish!"


@pytest.fixture
def account(administrator):
    with session_user(administrator.name):
        return EmailAccount.objects.create(
            email_account_name="Support",
            email_id="support@example.com",
            password=SECRET,
            smtp_server="smtp.example.com",
            enable_outgoing=True,
        )


@pytest.fixture
def manager(make_user):
    return make_user("manager@example.com", roles=["Sales Manager"])


# --- stage 2: the row rule ---------------------------------------------------------------


def test_an_ordinary_user_cannot_repoint_the_mail_server(alice, account, api_as):
    """**The finding.** Observed at 200 before the rule: every message the system sends,
    invitation links included, would then pass through a host of the caller's choosing."""
    response = api_as(alice).put(
        f"/api/resource/Email Account/{account.name}",
        {"smtp_server": "attacker.example.net"},
        format="json",
    )
    assert response.status_code == 403

    account.refresh_from_db()
    assert account.smtp_server == "smtp.example.com"


def test_an_ordinary_user_cannot_delete_an_account(alice, account, api_as):
    assert api_as(alice).delete(f"/api/resource/Email Account/{account.name}").status_code == 403
    assert EmailAccount.objects.filter(pk=account.name).exists()


def test_the_method_endpoint_is_covered_by_the_same_rule(alice, account, api_as):
    """`EmailEdit.vue` writes through `frappe.client.set_value`, not PUT - so un-routing
    would have fixed nothing. Both resolve through `_get_checked`, which is why one rule
    covers both doors, and why this test exists to prove it rather than assume it."""
    response = api_as(alice).post(
        "/api/method/frappe.client.set_value",
        {
            "doctype": "Email Account",
            "name": account.name,
            "fieldname": {"smtp_server": "attacker.example.net"},
        },
        format="json",
    )
    assert response.status_code == 403

    account.refresh_from_db()
    assert account.smtp_server == "smtp.example.com"


def test_a_manager_can_still_edit(manager, account, api_as):
    response = api_as(manager).put(
        f"/api/resource/Email Account/{account.name}",
        {"smtp_port": 2525},
        format="json",
    )
    assert response.status_code == 200, response.json()

    account.refresh_from_db()
    assert account.smtp_port == 2525


def test_an_ordinary_user_can_still_list_accounts(alice, account, api_as):
    """The Profile screen's "which address do I send from?" picker. Upstream shows this
    user nothing, leaving that picker empty; we keep it working."""
    rows = api_as(alice).get("/api/resource/Email Account").json()["data"]
    assert [r["email_id"] for r in rows] == ["support@example.com"]


# --- stage 4: restricted fields ----------------------------------------------------------


@pytest.mark.parametrize("field", ["smtp_server", "login_id", "api_key", "domain"])
def test_infrastructure_fields_are_hidden_from_an_ordinary_user(alice, account, api_as, field):
    body = api_as(alice).get(f"/api/resource/Email Account/{account.name}").json()["data"]
    assert field not in body


@pytest.mark.parametrize("field", ["name", "email_id", "enable_outgoing"])
def test_the_picker_still_gets_what_it_reads(alice, account, api_as, field):
    body = api_as(alice).get(f"/api/resource/Email Account/{account.name}").json()["data"]
    assert field in body


def test_a_manager_sees_the_infrastructure(manager, account, api_as):
    body = api_as(manager).get(f"/api/resource/Email Account/{account.name}").json()["data"]
    assert body["smtp_server"] == "smtp.example.com"


def test_the_list_path_hides_them_too(alice, account, api_as):
    """`EmailAccountList.vue` asks for `fields=['*']`. The list does not build a
    serializer, so it needs its own check - without one, everything the detail route
    dropped would come straight back here."""
    rows = api_as(alice).get("/api/resource/Email Account?fields=[\"*\"]").json()["data"]
    assert "smtp_server" not in rows[0]


def test_naming_a_restricted_field_explicitly_is_refused(alice, account, api_as):
    response = api_as(alice).get('/api/resource/Email Account?fields=["smtp_server"]')
    assert response.status_code == 417


def test_a_restricted_field_cannot_be_filtered_on_by_an_ordinary_user(alice, account, api_as):
    """Otherwise the field is readable one question at a time - the same oracle that
    recovered the password, applied to the fields stage 4 hides."""
    response = api_as(alice).get(
        '/api/resource/Email Account?filters=[["smtp_server","like","smtp%"]]'
    )
    assert response.status_code == 400


def test_a_manager_can_filter_on_it(manager, account, api_as):
    response = api_as(manager).get(
        '/api/resource/Email Account?filters=[["smtp_server","like","smtp%"]]'
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


# --- stage 3: encryption at rest ---------------------------------------------------------


def test_the_password_is_not_stored_in_plain_text(account):
    """Read the column, not the model: the point is what a database dump, a backup or a
    logged query would show."""
    stored = EmailAccount.objects.filter(pk=account.name).values_list("password", flat=True)[0]

    assert stored != SECRET
    assert SECRET not in stored
    assert secrets.is_encrypted(stored)


def test_the_password_round_trips(account):
    assert account.get_password("password") == SECRET


def test_saving_twice_does_not_double_encrypt(account):
    """`save()` runs on every write, including writes that do not touch the credential.
    Without idempotence the value would decrypt to ciphertext."""
    account.smtp_port = 2525
    account.save()
    account.refresh_from_db()

    assert account.get_password("password") == SECRET


def test_a_plaintext_value_still_reads(account):
    """The deploy window: code lands before the migration runs, and mail has to keep
    working on rows that are still plaintext."""
    EmailAccount.objects.filter(pk=account.name).update(password="legacy-plaintext")
    account.refresh_from_db()

    assert account.get_password("password") == "legacy-plaintext"


def test_the_mail_layer_gets_the_real_password(account, monkeypatch):
    """The end that matters. If validation read the ciphertext, every stored account
    would be reported as having bad credentials."""
    from frappe_core import mail

    seen = {}
    monkeypatch.setattr(mail, "check_smtp", lambda *a, **k: seen.update(k))

    account.refresh_from_db()
    mail.validate_email_account(account)

    assert seen["password"] == SECRET


def test_the_migration_encrypts_existing_rows(account):
    """Drives the migration's own function over a plaintext row, rather than trusting
    that it does what its name says."""
    import importlib

    from django.apps import apps

    # The module name starts with a digit, so it cannot be imported with `import`.
    migration = importlib.import_module(
        "frappe_platform.migrations.0005_encrypt_email_account_credentials"
    )

    EmailAccount.objects.filter(pk=account.name).update(password="legacy-plaintext")
    migration.encrypt_existing(apps, None)

    stored = EmailAccount.objects.filter(pk=account.name).values_list("password", flat=True)[0]
    assert secrets.is_encrypted(stored)
    assert secrets.decrypt(stored) == "legacy-plaintext"
