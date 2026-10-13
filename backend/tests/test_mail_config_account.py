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

import os
import subprocess
import sys
from pathlib import Path

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

BACKEND = Path(__file__).resolve().parent.parent

#: Builds the SMTP backend from the settings, which is what ``get_connection()`` returns in
#: production, and reports the connection it would open. No ``django.setup()``: the backend
#: reads the settings lazily and touches no model.
SMTP_PROBE = (
    "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test'); "
    "from django.core.mail.backends.smtp import EmailBackend; "
    "b = EmailBackend(); print(f'FLAGS:{int(b.use_tls)},{int(b.use_ssl)},{b.port}')"
)


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


@pytest.mark.parametrize("explicit_tls", [None, "True"], ids=["tls-unset", "tls-true"])
def test_ssl_turns_tls_off_so_the_config_account_can_connect(explicit_tls):
    """``EMAIL_USE_SSL`` with a login and ``EMAIL_USE_TLS`` unset defaulted TLS on too, and
    Django's SMTP backend refuses both flags (``ValueError``) before it opens a socket, so
    the config account could not send at all (Codex, 13 Oct 2026). SSL now drops TLS, the
    rule ``frappe_core.mail.smtp_settings`` applies to a saved account, whether TLS was
    left to its default or set outright.

    The defaults are computed when ``base.py`` is imported, out of ``override_settings``'s
    reach, so a fresh interpreter evaluates them - as ``test_integration_isolation`` does.
    Building the backend is the assertion: the broken pair fails right there. ``base.py``
    also reads the developer's ``.env`` for whatever the environment leaves unset, so the
    unset case is only as strict as that file; the explicit case does not depend on it.
    """
    env = {k: v for k, v in os.environ.items() if k not in ("EMAIL_USE_TLS", "EMAIL_PORT")}
    env.update(EMAIL_HOST=HOST, EMAIL_HOST_USER="relay-login", EMAIL_USE_SSL="True")
    if explicit_tls is not None:
        env["EMAIL_USE_TLS"] = explicit_tls

    result = subprocess.run(
        [sys.executable, "-c", SMTP_PROBE],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr[-2000:]
    line = [l for l in result.stdout.splitlines() if l.startswith("FLAGS:")]
    assert line, f"probe did not report; stdout={result.stdout[-500:]}"
    assert line[0] == "FLAGS:0,1,465", "use_tls, use_ssl, port: implicit TLS on 465, STARTTLS off"


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


# --- system mail: invitations and password resets -------------------------------------------

#: ``find_outgoing(_raise_error=True)``, ``email_account.py:530``, verbatim.
NO_ACCOUNT = "Please setup default outgoing Email Account from Tools > Email Account"

RESET = "/api/method/frappe.core.doctype.user.user.reset_password"


def _invitation(email, administrator):
    from crm_app.models import CRMInvitation

    with session_user(administrator.name):
        return CRMInvitation.objects.create(
            email=email, role="Sales User", status="Pending", key=f"k-{email}"
        )


def test_an_invitation_is_sent_from_the_config_account(administrator, config_account):
    """``frappe.sendmail`` with no sender uses the account's ``default_sender``
    (``QueueBuilder.sender``, ``email_queue.py:719-724``; ``email_account.py:468-469``):
    the account's name and address, so ``Frappe <notifications@...>``."""
    from crm_app.models import CRMInvitation

    mail.outbox.clear()
    invitation = _invitation("invitee@example.test", administrator)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.from_email == f"Frappe <{FROM}>"
    assert message.to == ["invitee@example.test"]
    assert invitation.key in message.body
    assert CRMInvitation.objects.get(pk=invitation.pk).email_sent_at is not None


def test_the_sender_name_setting_names_the_config_account(administrator, config_account):
    """``email_sender_name`` (``email_account.py:585``) is the virtual account's ``name``,
    and ``default_sender`` is built from it."""
    mail.outbox.clear()
    with override_settings(EMAIL_SENDER_NAME="Acme CRM"):
        _invitation("invitee2@example.test", administrator)

    assert mail.outbox[0].from_email == f"Acme CRM <{FROM}>"


def test_an_invitation_with_nothing_to_send_through_fails_its_task_once(
    administrator, no_config_account, monkeypatch
):
    """Upstream throws in front of the inviter (``find_outgoing(_raise_error=True)``,
    ``email_account.py:528-532``, reached from ``after_insert``); here the insert has
    already answered, so the task fails - once, since ``OutgoingEmailError`` is not a
    transport failure and a retry would not make an account appear - and
    ``email_sent_at`` stays null. The phase-5 trade-off of sending from a task."""
    from crm_app.models import CRMInvitation
    from crm_app.tasks import send_invitation_email
    from frappe_core.exceptions import OutgoingEmailError

    # The row without the signal's eager dispatch, which is how a worker meets it.
    monkeypatch.setattr(send_invitation_email, "delay", lambda *args, **kwargs: None)
    invitation = _invitation("nobody-carries@example.test", administrator)
    mail.outbox.clear()

    assert not issubclass(OutgoingEmailError, send_invitation_email.autoretry_for)
    with pytest.raises(OutgoingEmailError) as raised:
        send_invitation_email(invitation.pk)
    assert raised.value.message == NO_ACCOUNT

    assert mail.outbox == []
    assert CRMInvitation.objects.get(pk=invitation.pk).email_sent_at is None


def test_a_password_reset_is_sent_from_the_config_account(api, alice, config_account):
    mail.outbox.clear()
    response = api.post(RESET, {"user": alice.pk}, format="json")

    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert mail.outbox[0].from_email == f"Frappe <{FROM}>"
    assert mail.outbox[0].to == [alice.email or alice.pk]
    assert "/crm/update-password?key=" in mail.outbox[0].body


def test_a_password_reset_with_nothing_to_send_through_stays_silent(
    api, alice, no_config_account
):
    """``user.py:1055-1062`` catches and logs every failure and answers the one sentence;
    a missing account is one more failure the response must not reveal."""
    from crm_app.api import auth_pages

    mail.outbox.clear()
    response = api.post(RESET, {"user": alice.pk}, format="json")

    assert response.status_code == 200
    assert response.json()["message"]["message"] == auth_pages.GENERIC_RESET_RESPONSE
    assert mail.outbox == []
