"""Adding an email account on a server that is not ready for one: docs/FINDINGS.md 65.

Two failures the screen reports as "invalid credentials", because ``EmailAdd.vue`` shows
that one sentence for any error: a server with no ``FIELD_ENCRYPTION_KEY``, which cannot
store the password it has just verified, and a password the mail library cannot encode.
Both must be a clean refusal with the real reason in the response, not a 500, and the
first must be said before any login is attempted.
"""

from unittest import mock

import pytest

from frappe_platform.models import EmailAccount

pytestmark = pytest.mark.django_db

PATH = "/api/method/crm.api.settings.create_email_account"


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
    with mock.patch("frappe_core.mail.check_smtp") as check_smtp:
        response = api_as(administrator).post(PATH, account(), format="json")
    assert response.status_code == 417
    assert "FIELD_ENCRYPTION_KEY is not set" in response.json()["exception"]
    check_smtp.assert_not_called()
    assert not EmailAccount.objects.filter(email_account_name="ZZ Sales").exists()


def test_with_a_key_a_verified_account_is_saved(api_as, administrator):
    with mock.patch("frappe_core.mail.check_smtp") as check_smtp:
        response = api_as(administrator).post(PATH, account(), format="json")
    assert response.status_code == 200, response.content[:300]
    check_smtp.assert_called_once()
    saved = EmailAccount.objects.get(email_account_name="ZZ Sales")
    assert saved.password != "abcd efgh ijkl mnop", "stored encrypted, never as typed"


def test_a_password_the_mail_library_cannot_encode_is_a_refusal_not_a_500(api_as, administrator):
    """A Google app password copied from the page can carry non-breaking spaces;
    ``smtplib`` raises ``UnicodeEncodeError`` on them, which is not an SMTP error."""
    unencodable = UnicodeEncodeError("ascii", "abcd efgh", 4, 5, "ordinal not in range(128)")
    with mock.patch("django.core.mail.backends.smtp.EmailBackend.open", side_effect=unencodable):
        response = api_as(administrator).post(
            PATH, account(password="abcd efgh ijkl mnop"), format="json"
        )
    assert response.status_code == 417
    assert "ascii" in response.json()["exception"]
    assert not EmailAccount.objects.filter(email_account_name="ZZ Sales").exists()
