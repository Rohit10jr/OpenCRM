"""Ported from ``backend/tests/test_email_account_setup.py`` and the two endpoint cases of
``backend/tests/test_mail_validation.py:192-236`` (REBUILD_PLAN S14).

`crm.api.settings.create_email_account` is `POST /api/v1/email-accounts/setup/`
(specs/CONFIGURATION.md 4.4); the service is `configuration.email_accounts`, which takes
the caller as `user` (S16). Expected answers are unchanged. No test opens a real mail
connection: the checks are patched.
"""

from unittest import mock

import pytest

from configuration import email_accounts
from configuration.models import EmailAccount
from core.exceptions import ValidationError

pytestmark = pytest.mark.django_db

PATH = "/api/v1/email-accounts/setup/"


def account(**overrides) -> dict:
    data = {
        "service": "GMail",
        "email_account_name": "ZZ Sales",
        "email_id": "zz.sales@example.com",
        "password": "abcd efgh ijkl mnop",
        "enable_incoming": False,
        "enable_outgoing": True,
        "default_incoming": False,
        "default_outgoing": True,
    }
    data.update(overrides)
    return {"data": data}


def test_a_server_with_no_key_says_so_before_it_logs_in(api_as, administrator, settings):
    settings.FIELD_ENCRYPTION_KEY = ""
    with mock.patch("core.mail.check_smtp") as check_smtp:
        response = api_as(administrator).post(PATH, account(), format="json")
    assert response.status_code == 417
    assert "FIELD_ENCRYPTION_KEY is not set" in response.json()["exception"]
    check_smtp.assert_not_called()
    assert not EmailAccount.objects.filter(email_account_name="ZZ Sales").exists()


def test_with_a_key_a_verified_account_is_saved(api_as, administrator):
    with mock.patch("core.mail.check_smtp") as check_smtp:
        response = api_as(administrator).post(PATH, account(), format="json")
    assert response.status_code == 200, response.content[:300]
    check_smtp.assert_called_once()
    saved = EmailAccount.objects.get(email_account_name="ZZ Sales")
    assert saved.password != "abcd efgh ijkl mnop", "stored encrypted, never as typed"


def test_a_password_the_mail_library_cannot_encode_is_a_refusal_not_a_500(api_as, administrator):
    unencodable = UnicodeEncodeError("ascii", "abcd efgh", 4, 5, "ordinal not in range(128)")
    with mock.patch("django.core.mail.backends.smtp.EmailBackend.open", side_effect=unencodable):
        response = api_as(administrator).post(
            PATH, account(password="abcd efgh ijkl mnop"), format="json"
        )
    assert response.status_code == 417
    assert "ascii" in response.json()["exception"]
    assert not EmailAccount.objects.filter(email_account_name="ZZ Sales").exists()


def test_a_rejected_account_is_not_saved(monkeypatch, administrator):
    def boom(_account):
        raise ValidationError("Failed to create email account: invalid credentials")

    monkeypatch.setattr(email_accounts, "validate_email_account", boom)

    before = EmailAccount.objects.count()
    with pytest.raises(ValidationError):
        email_accounts.create_email_account(
            {
                "service": "GMail",
                "email_id": "x@example.com",
                "email_account_name": "Broken",
                "password": "wrong",
                "enable_outgoing": True,
            },
            user=administrator,
        )

    assert EmailAccount.objects.count() == before


def test_a_valid_account_saves(monkeypatch, administrator):
    monkeypatch.setattr(email_accounts, "validate_email_account", lambda _a: None)

    name = email_accounts.create_email_account(
        {
            "service": "GMail",
            "email_id": "ok@example.com",
            "email_account_name": "Working",
            "password": "right",
            "enable_outgoing": True,
        },
        user=administrator,
    )

    assert EmailAccount.objects.filter(pk=name).exists()


# --- new: no old test covers these (specs/CONFIGURATION.md section 4.4) -------------------


@pytest.fixture
def no_server(monkeypatch):
    monkeypatch.setattr(email_accounts, "validate_email_account", lambda _a: None)


def test_a_sales_user_is_refused_before_anything_else(auth_api, no_server):
    response = auth_api.post(PATH, {"data": "not an object"}, format="json")
    assert response.status_code == 403
    assert response.json()["message"] == "Not permitted"


def test_a_sales_manager_may_set_one_up(api_as, make_user, no_server):
    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    response = api_as(manager).post(PATH, account(), format="json")
    assert response.json() == {"message": "ZZ Sales"}


def test_data_that_is_not_an_object_is_invalid(api_as, administrator, no_server):
    response = api_as(administrator).post(PATH, {"data": "[1, 2]"}, format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "Invalid data"


def test_an_unknown_service_answers_the_string(api_as, administrator, no_server):
    response = api_as(administrator).post(PATH, account(service="Pigeon"), format="json")
    assert response.status_code == 200
    assert response.json() == {"message": "Service not supported"}
    assert not EmailAccount.objects.exists()


def test_the_name_is_required(api_as, administrator, no_server):
    response = api_as(administrator).post(PATH, account(email_account_name=""), format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "Email account name is required"


def test_a_duplicate_name_is_409_after_validation(api_as, administrator, monkeypatch):
    checked = []
    monkeypatch.setattr(email_accounts, "validate_email_account", lambda a: checked.append(a))
    client = api_as(administrator)
    assert client.post(PATH, account(), format="json").status_code == 200
    response = client.post(PATH, account(), format="json")
    assert response.status_code == 409
    assert response.json()["exc_type"] == "DuplicateEntryError"
    assert len(checked) == 2, "the second one was validated before the insert failed"


def test_the_service_fixes_the_hosts_and_appends_to_crm_lead(api_as, administrator, no_server):
    api_as(administrator).post(
        PATH, account(smtp_server="evil.example.net", awaiting_password=True), format="json"
    )
    saved = EmailAccount.objects.get(pk="ZZ Sales")
    assert (saved.smtp_server, saved.email_server) == ("smtp.gmail.com", "imap.gmail.com")
    assert saved.append_to == "CRM Lead"
    assert saved.awaiting_password is False


def test_a_frappe_mail_account_takes_the_api_credentials(api_as, administrator, no_server):
    api_as(administrator).post(
        PATH,
        account(
            service="Frappe Mail",
            api_key="k",
            api_secret="s",
            frappe_mail_site="https://mail.example.com",
            password="ignored",
        ),
        format="json",
    )
    saved = EmailAccount.objects.get(pk="ZZ Sales")
    assert (saved.api_key, saved.get_password("api_secret")) == ("k", "s")
    assert saved.get_password("password") == ""


def test_a_frappe_mail_account_with_a_direction_on_is_always_refused(api_as, administrator):
    """Its service config has no password and no server, so validation refuses it: the
    old behaviour, intended (spec section 4.4)."""
    response = api_as(administrator).post(
        PATH, account(service="Frappe Mail", api_key="k", api_secret="s"), format="json"
    )
    assert response.status_code == 417
    assert response.json()["message"] == "Password is required or select Awaiting Password"


def test_a_string_zero_is_true_as_in_backend(api_as, administrator, no_server):
    api_as(administrator).post(PATH, account(default_incoming="0"), format="json")
    assert EmailAccount.objects.get(pk="ZZ Sales").default_incoming is True


def test_get_is_not_served(api_as, administrator):
    assert api_as(administrator).get(PATH).status_code == 405
