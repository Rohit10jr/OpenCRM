"""The config account - docs/FINDINGS.md 79.

Upstream's fourth outgoing-account step, ``EmailAccount.find_from_config``
(``email_account.py:493-498``, reached from ``find_default_outgoing`` at ``:538``): with
no saved account to carry a mail, an **unsaved** Email Account built from
``site_config.json`` does. The port reads the same keys from Django's mail settings
(``config/settings/base.py``), so ``EMAIL_HOST`` set is ``mail_server`` set. System mail
- invitations, password resets - runs the same lookup (``crm_app.mail.send``), as
upstream's ``frappe.sendmail`` does with no sender.

The config account's transport is Django's own ``get_connection()``, which the test
settings point at ``locmem`` - so its sends reach ``django.core.mail.outbox`` through the
*real* ``open_backend``, and that path is what this file exercises. A **saved** account's
``open_backend`` would open a socket, so the fixture below patches that case only.
"""

import pytest
from django.core import mail
from django.test import override_settings

from crm_app import communication as communication_service
from frappe_core.session import session_user
from frappe_platform.models import Communication, EmailAccount

pytestmark = pytest.mark.django_db

MAKE = "/api/method/frappe.core.doctype.communication.email.make"

HOST = "smtp.example.test"
FROM = "notifications@example.test"


# --- fixtures ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def local_backend_for_saved_accounts(monkeypatch):
    """A saved account's ``open_backend`` reaches for its relay; send it to ``locmem``.

    The config account keeps the real function on purpose: under the test settings its
    ``get_connection()`` already *is* locmem, and a patch here would hide a regression in
    the one branch this file is about.
    """
    from django.core.mail.backends.locmem import EmailBackend

    real = communication_service.open_backend

    def open_backend(account):
        if getattr(account, "from_site_config", False):
            return real(account)
        return EmailBackend()

    monkeypatch.setattr(communication_service, "open_backend", open_backend)


@pytest.fixture
def config_account():
    """``mail_server`` set, and the rest pinned so a developer's ``.env`` cannot vary the
    From these tests assert on."""
    with override_settings(
        EMAIL_HOST=HOST,
        DEFAULT_FROM_EMAIL=FROM,
        EMAIL_SENDER_NAME="Frappe",
        EMAIL_ALWAYS_USE_ACCOUNT_EMAIL_ID_AS_SENDER=False,
    ):
        yield


@pytest.fixture
def no_config_account():
    """``mail_server`` unset. The test settings already say so; this makes a test that
    depends on it say so too."""
    with override_settings(EMAIL_HOST=""):
        yield


@pytest.fixture
def outgoing_account(administrator):
    """A saved default-outgoing ``Email Account``, as ``test_email_make.py`` builds one."""
    with session_user(administrator.name):
        return EmailAccount.objects.create(
            email_account_name="Support",
            email_id="support@example.com",
            password="hunter2",
            smtp_server="smtp.example.com",
            smtp_port=587,
            use_tls=True,
            enable_outgoing=True,
            default_outgoing=True,
        )


@pytest.fixture
def alice_lead(alice, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.filter(lead_status="New").first() or (
            CRMLeadStatus.objects.create(lead_status="New", type="Open")
        )
    with session_user(alice.name):
        return CRMLead.objects.create(first_name="Ada", lead_owner=alice, status=status)


def _payload(lead, **overrides):
    payload = {
        "doctype": "CRM Lead",
        "name": lead.name,
        "subject": "Re: your quote",
        "content": "<p>We can do <b>400k</b>.</p>",
        "recipients": "buyer@example.test",
        "sender": "alice@example.com",
        "sender_full_name": "Alice",
        "send_email": 1,
        "now": 1,
    }
    payload.update(overrides)
    return payload


# --- the account itself ---------------------------------------------------------------------


def test_the_config_account_exists_only_while_email_host_is_set(no_config_account):
    """``get_account_details_from_site_config`` returns ``{}`` without ``mail_server``
    (``email_account.py:564-565``), and ``find_from_config`` then returns nothing."""
    assert communication_service.config_account() is None
    assert communication_service.find_outgoing_account() is None


def test_the_config_account_is_the_settings_as_an_unsaved_email_account():
    """The field map of ``email_account.py:567-592``, with Django's names on the left."""
    with override_settings(
        EMAIL_HOST=HOST,
        EMAIL_PORT=2525,
        EMAIL_HOST_USER="relay-login",
        EMAIL_USE_TLS=True,
        EMAIL_USE_SSL=False,
        DEFAULT_FROM_EMAIL=FROM,
        EMAIL_SENDER_NAME="Acme Notifications",
        EMAIL_ALWAYS_USE_ACCOUNT_EMAIL_ID_AS_SENDER=True,
    ):
        account = communication_service.config_account()

    assert isinstance(account, EmailAccount)
    assert not account.pk, "from_record: never saved, so it has no name to stamp"
    assert account.from_site_config is True
    assert account.email_account_name == "Acme Notifications"
    assert account.email_id == FROM
    assert account.enable_outgoing is True
    assert account.smtp_server == HOST
    assert account.smtp_port == 2525
    assert account.use_tls is True
    assert account.use_ssl_for_outgoing is False
    # `mail_login` is the login, and it differs from the address it sends as.
    assert account.login_id == "relay-login"
    assert account.login_id_is_different is True
    assert account.no_smtp_authentication is False
    assert account.always_use_account_email_id_as_sender is True
    assert EmailAccount.objects.count() == 0


def test_no_login_means_no_smtp_authentication():
    with override_settings(EMAIL_HOST=HOST, EMAIL_HOST_USER="", DEFAULT_FROM_EMAIL=FROM):
        account = communication_service.config_account()

    assert account.no_smtp_authentication is True
    assert account.login_id_is_different is False


def test_the_config_account_sends_through_the_configured_backend(config_account):
    """``open_backend`` hands the config account to ``get_connection()`` - locmem here,
    the console backend in development, SMTP with the same settings in production."""
    from django.core.mail.backends.locmem import EmailBackend

    account = communication_service.config_account()
    assert isinstance(communication_service.open_backend(account), EmailBackend)


# --- a lead's mail --------------------------------------------------------------------------


def test_a_lead_mail_falls_through_to_the_config_account(auth_api, alice_lead, config_account):
    """No saved account matches, so step 4 carries it - and the From is still the user's
    own, as ``mail_sender`` / ``mail_sender_fullname`` make it."""
    response = auth_api.post(MAKE, _payload(alice_lead), format="json")
    assert response.status_code == 200, response.content[:300]

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.from_email == "Alice <alice@example.com>"
    assert message.to == ["buyer@example.test"]

    row = Communication.objects.get(pk=response.json()["message"]["name"])
    # Not stamped: the field names a row and the config account has none.
    assert row.email_account == ""
    assert row.communication_date is not None


def test_the_sender_flag_replaces_the_address_on_the_config_account(
    auth_api, alice_lead, config_account
):
    """``replace_sender`` (``email_body.py:300``) applies to the config account as to any
    other: the display name stays the user's, the address becomes ``DEFAULT_FROM_EMAIL``."""
    with override_settings(EMAIL_ALWAYS_USE_ACCOUNT_EMAIL_ID_AS_SENDER=True):
        response = auth_api.post(MAKE, _payload(alice_lead), format="json")

    assert response.status_code == 200
    assert mail.outbox[0].from_email == f"Alice <{FROM}>"


def test_a_saved_default_outgoing_account_wins_over_the_config_account(
    auth_api, alice_lead, config_account, outgoing_account
):
    """Step 3 before step 4 (``find_default_outgoing``, ``email_account.py:537-538``).

    The saved account's sender flag is switched on so the From says which account carried
    the mail: ``support@example.com`` is the saved one's address, not the config one's.
    """
    EmailAccount.objects.filter(pk=outgoing_account.name).update(
        always_use_account_email_id_as_sender=True
    )

    response = auth_api.post(MAKE, _payload(alice_lead), format="json")
    assert response.status_code == 200

    assert mail.outbox[0].from_email == "Alice <support@example.com>"
    row = Communication.objects.get(pk=response.json()["message"]["name"])
    assert row.email_account == outgoing_account.name


def test_the_queued_path_sends_through_the_config_account_too(
    auth_api, alice_lead, config_account
):
    """``now=0``: ``_send`` accepts it (there is an account), the task finds the same
    account again - nothing was stamped - and sends."""
    response = auth_api.post(MAKE, _payload(alice_lead, now=0), format="json")
    assert response.status_code == 200

    assert len(mail.outbox) == 1
    assert mail.outbox[0].from_email == "Alice <alice@example.com>"
    row = Communication.objects.get(pk=response.json()["message"]["name"])
    assert row.email_account == ""
    assert row.communication_date is not None
