"""Email Account: new tests for what no old test covers (specs/CONFIGURATION.md 4.4).

The resource's closed doors for a non-manager, the sensitive fields, parity on update
(decision 4), rename (parked question, today's behaviour pinned), the link to the user's
`user_emails`, and the saved-account provider core.mail reaches (decision 7). No test
opens a real mail connection.
"""

import pytest

from configuration import mail as provider
from configuration.models import EmailAccount, UserEmail
from core import mail

pytestmark = pytest.mark.django_db

ACCOUNTS = "/api/v1/email-accounts/"


def make(user, **fields):
    values = {
        "email_account_name": "Support",
        "email_id": "support@example.com",
        "smtp_server": "smtp.example.com",
        "enable_outgoing": True,
        **fields,
    }
    row = EmailAccount(**values)
    row.save(user=user)
    return row


@pytest.fixture
def manager(make_user):
    return make_user("manager@example.com", roles=["Sales Manager"])


@pytest.fixture
def account(administrator):
    return make(administrator, password="secret-1")


# --- the doors closed to a non-manager ---------------------------------------------------


def test_a_non_manager_cannot_create_one(auth_api):
    response = auth_api.post(ACCOUNTS, {"email_account_name": "Mine"}, format="json")
    assert response.status_code == 403
    assert not EmailAccount.objects.filter(pk="Mine").exists()


def test_a_non_manager_cannot_rename_one(auth_api, account):
    response = auth_api.post(f"{ACCOUNTS}{account.name}/rename/", {"new_name": "Other"}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "You need write permission on Email Account Support to rename"


def test_a_manager_creates_one_through_the_resource_without_validation(api_as, manager, monkeypatch):
    """Parity (decision 4): no validation, service defaults or name check."""
    monkeypatch.setattr(mail, "validate_email_account", lambda *a: pytest.fail("validated"))
    response = api_as(manager).post(
        ACCOUNTS,
        {"email_account_name": "Sales", "email_id": "sales@example.com", "smtp_server": "x"},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    assert EmailAccount.objects.get(pk="Sales").smtp_server == "x"


# --- sensitive fields ----------------------------------------------------------------------


@pytest.mark.parametrize("field", ["password", "api_secret"])
def test_a_secret_is_absent_even_for_administrator(api_as, administrator, account, field):
    body = api_as(administrator).get(f"{ACCOUNTS}{account.name}/").json()["message"]
    assert field not in body
    rows = api_as(administrator).get(ACCOUNTS, {"fields": '["*"]'}).json()["message"]
    assert field not in rows[0]


@pytest.mark.parametrize("field", ["password", "api_secret"])
def test_a_secret_is_refused_by_name_filter_and_value(api_as, administrator, account, field):
    client = api_as(administrator)
    assert client.get(ACCOUNTS, {"fields": f'["{field}"]'}).status_code == 417
    assert client.get(ACCOUNTS, {"filters": f'[["{field}","like","s%"]]'}).status_code == 400
    # `frappe.client.get_value` goes through the list query in backend/ too
    # (crm_app/api/client.py:243), so naming a hidden field is the list's 417.
    value = client.get(f"{ACCOUNTS}value/", {"fieldname": field, "filters": '{"name": "Support"}'})
    assert value.status_code == 417
    assert value.json()["message"] == f"Field {field!r} is not readable"


def test_a_password_sent_on_update_is_ignored(api_as, manager, account):
    """Parity (decision 4; known difference from upstream, DECISIONS 37)."""
    response = api_as(manager).patch(
        f"{ACCOUNTS}{account.name}/", {"password": "new-secret", "smtp_port": 25}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    account.refresh_from_db()
    assert account.get_password("password") == "secret-1"
    assert account.smtp_port == 25


# --- rename (parked question, DECISIONS 38) ------------------------------------------------


def test_a_rename_keeps_the_naming_field_at_the_old_value(api_as, manager, account):
    """Today's behaviour, as backend/: only the key changes. Upstream also updates
    `email_account_name`; this test pins parity until the owner decides."""
    response = api_as(manager).post(f"{ACCOUNTS}Support/rename/", {"new_name": "Help Desk"}, format="json")
    assert response.status_code == 200, response.content[:300]
    renamed = EmailAccount.objects.get(pk="Help Desk")
    assert renamed.email_account_name == "Support"


# --- the link to the user's user_emails ---------------------------------------------------


def test_an_account_links_itself_to_the_user_whose_address_it_is(administrator, make_user):
    owner = make_user("support@example.com", roles=["Sales User"])
    account = make(administrator)
    row = UserEmail.objects.get(parent_user=owner, email_account=account)
    assert (row.idx, row.email_id, row.enable_outgoing) == (1, "support@example.com", True)


def test_the_link_matches_case_insensitively_and_trims(administrator, make_user):
    owner = make_user("support@example.com", roles=["Sales User"])
    make(administrator, email_id="  SUPPORT@Example.com ")
    assert UserEmail.objects.filter(parent_user=owner).count() == 1


def test_a_second_save_updates_the_row_rather_than_adding_one(administrator, make_user):
    owner = make_user("support@example.com", roles=["Sales User"])
    account = make(administrator)
    account.enable_outgoing = False
    account.save(user=administrator)
    rows = UserEmail.objects.filter(parent_user=owner)
    assert rows.count() == 1 and rows.get().enable_outgoing is False


def test_an_empty_address_links_nobody(administrator):
    make(administrator, email_id="")
    assert not UserEmail.objects.exists()


def test_a_queryset_update_does_not_link(administrator, make_user):
    owner = make_user("support@example.com", roles=["Sales User"])
    make(administrator, email_id="")
    EmailAccount.objects.update(email_id="support@example.com")
    assert not UserEmail.objects.filter(parent_user=owner).exists()


def test_deleting_the_account_removes_its_rows(administrator, make_user):
    owner = make_user("support@example.com", roles=["Sales User"])
    account = make(administrator)
    account.delete()
    assert not UserEmail.objects.filter(parent_user=owner).exists()


def test_a_new_row_is_appended_after_the_users_existing_ones(administrator, make_user):
    owner = make_user("support@example.com", roles=["Sales User"])
    make(administrator)
    second = make(administrator, email_account_name="Second")
    assert UserEmail.objects.get(parent_user=owner, email_account=second).idx == 2


# --- the provider core.mail reaches (decision 7) -------------------------------------------


def test_the_provider_is_configured_and_passes_its_check(settings):
    assert settings.MAIL_ACCOUNT_PROVIDER == "configuration.mail"
    assert mail.account_provider() is provider


def test_a_sender_address_picks_its_own_account(administrator):
    make(administrator, email_account_name="Default", email_id="default@example.com", default_outgoing=True)
    own = make(administrator, email_account_name="Own", email_id="own@example.com")
    assert mail.find_outgoing_account(sender="Me <own@example.com>") == own


def test_the_reference_doctype_picks_the_inbox_account(administrator):
    make(administrator, email_account_name="Default", email_id="default@example.com", default_outgoing=True)
    inbox = make(
        administrator,
        email_account_name="Inbox",
        email_id="inbox@example.com",
        enable_incoming=True,
        append_to="CRM Lead",
    )
    assert mail.find_outgoing_account(reference_doctype="CRM Lead") == inbox


def test_system_mail_takes_the_newest_default_account(administrator):
    make(administrator, email_account_name="Old", email_id="old@example.com", default_outgoing=True)
    newest = make(administrator, email_account_name="New", email_id="new@example.com", default_outgoing=True)
    assert mail.find_outgoing_account() == newest


def test_without_a_saved_account_the_config_account_carries_it(settings):
    settings.EMAIL_HOST = "smtp.config.test"
    assert mail.find_outgoing_account().from_site_config


def test_the_signature_fallback_takes_the_newest_default_with_add_signature(administrator):
    make(administrator, email_account_name="A", default_outgoing=True, add_signature=True, signature="Old")
    make(
        administrator,
        email_account_name="B",
        default_outgoing=True,
        add_signature=True,
        signature="New",
        enable_outgoing=False,
    )
    assert mail.default_signature() == "New"


def test_the_signature_fallback_needs_add_signature_and_a_signature(administrator):
    make(administrator, email_account_name="A", default_outgoing=True, signature="Hidden")
    assert mail.default_signature() is None
    make(administrator, email_account_name="B", default_outgoing=True, add_signature=True, signature="")
    assert mail.default_signature() is None
