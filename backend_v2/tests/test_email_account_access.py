"""Ported from ``backend/tests/test_email_account_access.py`` (REBUILD_PLAN S14), all but
`test_the_migration_encrypts_existing_rows` (`:206`, the old backend's legacy-rows
migration; there are no legacy rows here).

Email Account: who may change it, who may see what, and where the secret lives
(specs/CONFIGURATION.md 4.4). `PUT`/`DELETE /api/resource/Email Account/<name>` and
`frappe.client.set_value` are `PATCH`/`DELETE /api/v1/email-accounts/<name>/`; the old
resource answered under `data`, here under `message`. Expected answers are unchanged.
"""

import pytest

from configuration.models import EmailAccount
from core import secrets

pytestmark = pytest.mark.django_db

SECRET = "Sw0rdfish!"
ACCOUNTS = "/api/v1/email-accounts/"


@pytest.fixture
def account(administrator):
    row = EmailAccount(
        email_account_name="Support",
        email_id="support@example.com",
        password=SECRET,
        smtp_server="smtp.example.com",
        enable_outgoing=True,
    )
    row.save(user=administrator)
    return row


@pytest.fixture
def manager(make_user):
    return make_user("manager@example.com", roles=["Sales Manager"])


# --- the row rule --------------------------------------------------------------------------


def test_an_ordinary_user_cannot_repoint_the_mail_server(alice, account, api_as):
    response = api_as(alice).patch(
        f"{ACCOUNTS}{account.name}/", {"smtp_server": "other.example.net"}, format="json"
    )
    assert response.status_code == 403

    account.refresh_from_db()
    assert account.smtp_server == "smtp.example.com"


def test_an_ordinary_user_cannot_delete_an_account(alice, account, api_as):
    assert api_as(alice).delete(f"{ACCOUNTS}{account.name}/").status_code == 403
    assert EmailAccount.objects.filter(pk=account.name).exists()


def test_the_method_endpoint_is_covered_by_the_same_rule(alice, account, api_as):
    """`frappe.client.set_value` and the resource PUT are one route here: PATCH."""
    response = api_as(alice).patch(
        f"{ACCOUNTS}{account.name}/", {"smtp_server": "other.example.net"}, format="json"
    )
    assert response.status_code == 403

    account.refresh_from_db()
    assert account.smtp_server == "smtp.example.com"


def test_a_manager_can_still_edit(manager, account, api_as):
    response = api_as(manager).patch(f"{ACCOUNTS}{account.name}/", {"smtp_port": 2525}, format="json")
    assert response.status_code == 200, response.json()

    account.refresh_from_db()
    assert account.smtp_port == 2525


def test_an_ordinary_user_can_still_list_accounts(alice, account, api_as):
    rows = api_as(alice).get(ACCOUNTS).json()["message"]
    assert [r["email_id"] for r in rows] == ["support@example.com"]


# --- restricted fields ---------------------------------------------------------------------


@pytest.mark.parametrize("field", ["smtp_server", "login_id", "api_key", "domain"])
def test_infrastructure_fields_are_hidden_from_an_ordinary_user(alice, account, api_as, field):
    body = api_as(alice).get(f"{ACCOUNTS}{account.name}/").json()["message"]
    assert field not in body


@pytest.mark.parametrize("field", ["name", "email_id", "enable_outgoing"])
def test_the_picker_still_gets_what_it_reads(alice, account, api_as, field):
    body = api_as(alice).get(f"{ACCOUNTS}{account.name}/").json()["message"]
    assert field in body


def test_a_manager_sees_the_infrastructure(manager, account, api_as):
    body = api_as(manager).get(f"{ACCOUNTS}{account.name}/").json()["message"]
    assert body["smtp_server"] == "smtp.example.com"


def test_the_list_path_hides_them_too(alice, account, api_as):
    rows = api_as(alice).get(ACCOUNTS, {"fields": '["*"]'}).json()["message"]
    assert "smtp_server" not in rows[0]


def test_naming_a_restricted_field_explicitly_is_refused(alice, account, api_as):
    response = api_as(alice).get(ACCOUNTS, {"fields": '["smtp_server"]'})
    assert response.status_code == 417


def test_a_restricted_field_cannot_be_filtered_on_by_an_ordinary_user(alice, account, api_as):
    response = api_as(alice).get(ACCOUNTS, {"filters": '[["smtp_server","like","smtp%"]]'})
    assert response.status_code == 400


def test_a_manager_can_filter_on_it(manager, account, api_as):
    response = api_as(manager).get(ACCOUNTS, {"filters": '[["smtp_server","like","smtp%"]]'})
    assert response.status_code == 200
    assert len(response.json()["message"]) == 1


# --- encryption at rest --------------------------------------------------------------------


def test_the_password_is_not_stored_in_plain_text(account):
    stored = EmailAccount.objects.filter(pk=account.name).values_list("password", flat=True)[0]

    assert stored != SECRET
    assert SECRET not in stored
    assert secrets.is_encrypted(stored)


def test_the_password_round_trips(account):
    assert account.get_password("password") == SECRET


def test_saving_twice_does_not_double_encrypt(account, administrator):
    account.smtp_port = 2525
    account.save(user=administrator)
    account.refresh_from_db()

    assert account.get_password("password") == SECRET


def test_a_plaintext_value_still_reads(account):
    EmailAccount.objects.filter(pk=account.name).update(password="legacy-plaintext")
    account.refresh_from_db()

    assert account.get_password("password") == "legacy-plaintext"


def test_the_mail_layer_gets_the_real_password(account, monkeypatch):
    from core import mail

    seen = {}
    monkeypatch.setattr(mail, "check_smtp", lambda *a, **k: seen.update(k))

    account.refresh_from_db()
    mail.validate_email_account(account)

    assert seen["password"] == SECRET


# --- new: every restricted field through every door (A-34 finding 3) ---------------------

RESTRICTED = (
    "smtp_server",
    "smtp_port",
    "email_server",
    "incoming_port",
    "login_id",
    "domain",
    "api_key",
    "frappe_mail_site",
    "signature",
    "no_smtp_authentication",
    "awaiting_password",
)


@pytest.mark.parametrize("field", RESTRICTED)
def test_a_non_manager_cannot_reach_a_restricted_field_by_any_door(alice, account, api_as, field):
    client = api_as(alice)
    assert field not in client.get(f"{ACCOUNTS}{account.name}/").json()["message"]
    rows = client.get(ACCOUNTS, {"fields": '["*"]'}).json()["message"]
    assert field not in rows[0]
    assert client.get(ACCOUNTS, {"fields": f'["{field}"]'}).status_code == 417
    assert client.get(ACCOUNTS, {"filters": f'[["{field}","is","set"]]'}).status_code == 400
    # backend/frappe_core/query.py:157-158: a ValidationError naming the field.
    ordered = client.get(ACCOUNTS, {"order_by": f"{field} asc"})
    assert ordered.status_code == 417
    assert ordered.json()["message"].startswith(f"Cannot order by '{field}'")
    value = client.get(f"{ACCOUNTS}value/", {"fieldname": field, "filters": '{"name": "Support"}'})
    assert value.status_code == 417


@pytest.mark.parametrize("field", RESTRICTED)
def test_a_manager_reaches_every_restricted_field(manager, account, api_as, field):
    client = api_as(manager)
    assert field in client.get(f"{ACCOUNTS}{account.name}/").json()["message"]
    assert client.get(ACCOUNTS, {"fields": f'["{field}"]'}).status_code == 200
