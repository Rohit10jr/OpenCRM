"""``frappe.core.doctype.communication.email.make`` - the send button on a lead or deal.

Ported from ``frappe/core/doctype/communication/email.py`` (``make`` / ``_make`` /
``validate_email`` / ``add_attachments``) and ``mixins.py`` (the recipient lists, the From,
the account lookup). ``CommunicationArea.vue:206-229`` is the only caller in the product.

**No test here touches a mail server.** ``crm_app.communication.open_backend`` is the one
seam the send goes through, and patching it to return Django's ``locmem`` backend puts the
real, fully built message in ``django.core.mail.outbox`` - so the From, the To/Cc/Bcc, the
headers, the HTML alternative and the attachment bytes are all assertable without one.

The queued path needs no patching of Celery: ``config/settings/test.py`` sets
``CELERY_TASK_ALWAYS_EAGER``, so ``.delay()`` runs inline and the outbox fills the same way.
"""

import mimetypes

import pytest
from django.core import mail

from crm_app import communication as communication_service
from frappe_core.session import session_user
from frappe_platform.models import Communication, EmailAccount, File

pytestmark = pytest.mark.django_db

MAKE = "/api/method/frappe.core.doctype.communication.email.make"

SUBJECT = "Re: your quote"
BODY = "<p>We can do <b>400k</b>.</p>"


# --- fixtures ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def local_backend(monkeypatch):
    """Every send goes through ``open_backend``; send it to ``locmem`` instead of SMTP.

    Autouse so that a test which forgets it cannot reach a real relay - the failure mode
    would be a hung suite, not a red test.
    """
    from django.core.mail.backends.locmem import EmailBackend

    monkeypatch.setattr(communication_service, "open_backend", lambda account: EmailBackend())


@pytest.fixture
def outgoing_account(administrator):
    """A default-outgoing ``Email Account``. The password is encrypted on save by
    ``EncryptedFieldsMixin``, as it is in production."""
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


def _lead(owner, administrator, first_name="Ada"):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.filter(lead_status="New").first() or (
            CRMLeadStatus.objects.create(lead_status="New", type="Open")
        )
    with session_user(owner.name):
        return CRMLead.objects.create(first_name=first_name, lead_owner=owner, status=status)


@pytest.fixture
def alice_lead(alice, administrator):
    return _lead(alice, administrator)


@pytest.fixture
def bob_lead(bob, administrator):
    return _lead(bob, administrator, first_name="Bruno")


def _payload(lead, **overrides):
    payload = {
        "doctype": "CRM Lead",
        "name": lead.name,
        "subject": SUBJECT,
        "content": BODY,
        "recipients": "buyer@example.test, cfo@example.test",
        "cc": "assistant@example.test",
        "sender": "alice@example.com",
        "sender_full_name": "Alice",
        "send_email": 1,
        "now": 1,
    }
    payload.update(overrides)
    return payload


# --- the happy path ---------------------------------------------------------------------


def test_a_sales_user_emails_a_lead_she_can_read(auth_api, alice_lead, outgoing_account):
    """The whole of ``_make`` in one call: the row, then the message built from it."""
    response = auth_api.post(MAKE, _payload(alice_lead), format="json")
    assert response.status_code == 200

    body = response.json()["message"]
    assert body["emails_not_sent_to"] == ""

    row = Communication.objects.get(pk=body["name"])
    assert row.reference_doctype == "CRM Lead"
    assert row.reference_name == alice_lead.name
    assert row.sender == "alice@example.com"
    assert row.sender_full_name == "Alice"
    assert row.recipients == "buyer@example.test, cfo@example.test"
    assert row.cc == "assistant@example.test"
    assert row.communication_type == "Communication"
    assert row.sent_or_received == "Sent"
    # `get_outgoing_email_account` records which account sent it (mixins.py:181-193).
    assert row.email_account == outgoing_account.name

    # `_make` stores the id without the angle brackets, as `get_string_between` leaves it.
    assert row.message_id
    assert not row.message_id.startswith("<") and not row.message_id.endswith(">")
    assert row.message_id.endswith("@" + communication_service.site_domain())

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject == SUBJECT
    assert message.to == ["buyer@example.test", "cfo@example.test"]
    assert message.cc == ["assistant@example.test"]
    assert message.from_email == "Alice <alice@example.com>"
    assert message.extra_headers["Message-ID"] == f"<{row.message_id}>"
    # HTML as an alternative, with a text fallback in the body.
    assert message.alternatives == [(BODY, "text/html")]
    assert "400k" in message.body and "<b>" not in message.body


def test_the_send_stamps_the_row_so_a_redelivery_cannot_double_send(
    auth_api, alice_lead, outgoing_account
):
    """``communication_date`` is the sent stamp - the idempotence a Celery task needs."""
    name = auth_api.post(MAKE, _payload(alice_lead), format="json").json()["message"]["name"]
    assert Communication.objects.get(pk=name).communication_date is not None

    # The task, replayed. Nothing further goes out.
    assert communication_service.send_communication(name) is False
    assert len(mail.outbox) == 1


def test_without_now_the_queued_task_sends_it(auth_api, alice_lead, outgoing_account):
    """The frontend never passes ``now``, so this is the path the product uses.

    ``CELERY_TASK_ALWAYS_EAGER`` runs the task inline here; in production it is a worker.
    """
    response = auth_api.post(MAKE, _payload(alice_lead, now=None), format="json")
    assert response.status_code == 200

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["buyer@example.test", "cfo@example.test"]
    name = response.json()["message"]["name"]
    assert Communication.objects.get(pk=name).communication_date is not None


def test_send_email_false_logs_the_row_and_sends_nothing(auth_api, alice_lead, outgoing_account):
    """The timeline entry is the point of the row; the send is separate."""
    response = auth_api.post(
        MAKE, _payload(alice_lead, send_email=0, now=None), format="json"
    )
    assert response.status_code == 200

    row = Communication.objects.get(pk=response.json()["message"]["name"])
    assert row.subject == SUBJECT
    # Not sent, so not stamped and no account chosen.
    assert row.communication_date is None
    assert row.email_account == ""
    assert mail.outbox == []


# --- addressing ---------------------------------------------------------------------------


def test_send_me_a_copy_puts_the_sender_in_cc(auth_api, alice_lead, outgoing_account):
    """``mail_cc(include_sender=True)`` - added to the *message*, not to the stored row."""
    response = auth_api.post(
        MAKE, _payload(alice_lead, send_me_a_copy=1), format="json"
    )
    assert response.status_code == 200

    assert mail.outbox[0].cc == ["assistant@example.test", "alice@example.com"]
    row = Communication.objects.get(pk=response.json()["message"]["name"])
    assert row.cc == "assistant@example.test"


def test_the_copy_goes_to_the_logged_in_user_not_the_chosen_sender(
    auth_api, alice_lead, outgoing_account
):
    """``mixins.py:88-93``: the copy is for whoever clicked send. Alice sending as the
    shared support address still gets her own copy - Codex finding 1 on this stage."""
    payload = _payload(alice_lead, sender="support@example.com", send_me_a_copy=1)
    response = auth_api.post(MAKE, payload, format="json")
    assert response.status_code == 200, response.content[:300]

    assert "alice@example.com" in mail.outbox[0].cc
    assert "support@example.com" not in mail.outbox[0].cc


def test_a_standard_user_gets_the_copy_at_the_sender_address(
    api_as, administrator, alice_lead, outgoing_account
):
    """Administrator has no mailbox of its own, so upstream falls back to the sender."""
    payload = _payload(alice_lead, sender="support@example.com", send_me_a_copy=1)
    response = api_as(administrator).post(MAKE, payload, format="json")
    assert response.status_code == 200, response.content[:300]

    assert "support@example.com" in mail.outbox[0].cc


def test_a_failed_send_releases_the_claim_so_a_retry_can_send(
    auth_api, alice_lead, outgoing_account, monkeypatch
):
    """The row is claimed before the send and released when the relay refuses - the
    retry then does the work; a duplicate is what the claim exists to prevent
    (Codex finding 2 on this stage)."""
    import smtplib

    from django.core.mail.backends.locmem import EmailBackend

    class RelayDown(EmailBackend):
        def send_messages(self, messages):
            raise smtplib.SMTPException("relay down")

    monkeypatch.setattr(communication_service, "open_backend", lambda account: RelayDown())
    response = auth_api.post(MAKE, _payload(alice_lead), format="json")
    assert response.status_code == 417
    assert response.json()["message"] == "Could not send the email: relay down"
    name = Communication.objects.filter(subject=SUBJECT).latest("creation").pk
    assert Communication.objects.get(pk=name).communication_date is None, "claim released"
    assert mail.outbox == []

    monkeypatch.setattr(communication_service, "open_backend", lambda account: EmailBackend())
    assert communication_service.send_communication(name) is True
    assert len(mail.outbox) == 1
    assert Communication.objects.get(pk=name).communication_date is not None


def test_the_send_uses_the_accounts_own_smtp_settings(monkeypatch, administrator):
    """``open_backend`` and the save-time check share ``frappe_core.mail.smtp_settings``,
    so an account validated with one set of flags cannot send with another (Codex
    finding 3 on this stage). Builds the real backend and sends nothing."""
    from frappe_core import mail as mail_checks

    monkeypatch.undo()  # drop the locmem seam: this test wants the SMTP backend itself
    with session_user(administrator.name):
        account = EmailAccount.objects.create(
            email_account_name="Relay", email_id="relay@example.com", password="s3cret",
            smtp_server="mail.example.com", smtp_port=None, use_tls=True,
            use_ssl_for_outgoing=True, login_id_is_different=True, login_id="smtp-user",
            enable_outgoing=True,
        )

    backend = communication_service.open_backend(account)

    assert (backend.host, backend.port, backend.username, backend.password) == (
        "mail.example.com", 465, "smtp-user", "s3cret"
    )
    assert backend.use_ssl is True and backend.use_tls is False
    assert mail_checks.smtp_settings(account)["username"] == "smtp-user"
    assert mail_checks.smtp_settings(account)["port"] == 465


def test_in_reply_to_carries_the_earlier_message_id(auth_api, alice_lead, outgoing_account):
    """``set_in_reply_to`` - what makes a mail client thread the two together."""
    first = auth_api.post(MAKE, _payload(alice_lead), format="json").json()["message"]
    earlier = Communication.objects.get(pk=first["name"])

    response = auth_api.post(
        MAKE, _payload(alice_lead, in_reply_to=earlier.name, subject="Re: Re: your quote"),
        format="json",
    )
    assert response.status_code == 200

    reply = Communication.objects.get(pk=response.json()["message"]["name"])
    assert reply.in_reply_to == earlier.name
    assert mail.outbox[-1].extra_headers["In-Reply-To"] == f"<{earlier.message_id}>"


def test_the_recipient_lists_are_deduped_the_way_upstream_dedupes_them(
    auth_api, alice_lead, outgoing_account
):
    """``mail_recipients`` / ``mail_cc`` / ``mail_bcc``, including where they differ.

    ``cc`` loses anything already in ``to``; ``bcc`` loses that too and **keeps** what is
    also in ``cc`` - upstream subtracts only ``mail_recipients`` there, so an address
    written into both is genuinely addressed twice. Reproduced, not tidied.
    """
    response = auth_api.post(
        MAKE,
        _payload(
            alice_lead,
            recipients="buyer@example.test, BUYER@example.test",
            cc="buyer@example.test, assistant@example.test",
            bcc="assistant@example.test, archive@example.test",
        ),
        format="json",
    )
    assert response.status_code == 200

    message = mail.outbox[0]
    assert message.to == ["buyer@example.test"]
    assert message.cc == ["assistant@example.test"]
    assert message.bcc == ["assistant@example.test", "archive@example.test"]


def test_an_invalid_recipient_is_refused(auth_api, alice_lead, outgoing_account):
    """``validate_email`` runs during insert upstream, so nothing is left behind."""
    before = Communication.objects.count()
    response = auth_api.post(
        MAKE, _payload(alice_lead, recipients="buyer@example.test, not-an-address"),
        format="json",
    )

    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "InvalidEmailAddressError"
    assert body["message"] == "not-an-address is not a valid Email Address"
    assert Communication.objects.count() == before
    assert mail.outbox == []


# --- attachments ---------------------------------------------------------------------------


@pytest.fixture
def uploaded_files(settings, tmp_path, administrator):
    """Two real files under a throwaway ``MEDIA_ROOT``, one public and one private."""
    settings.MEDIA_ROOT = tmp_path
    specs = [
        ("quote.pdf", "files/quote.pdf", b"%PDF-1.4 quote", False),
        ("terms.txt", "private/files/terms.txt", b"strictly confidential", True),
    ]
    rows = []
    with session_user(administrator.name):
        for file_name, relative, content, is_private in specs:
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            rows.append(
                File.objects.create(
                    file_name=file_name,
                    file_url="/" + relative,
                    is_private=is_private,
                    file_size=len(content),
                )
            )
    return rows


def test_attachments_are_copied_onto_the_communication_and_sent(
    auth_api, alice_lead, outgoing_account, uploaded_files
):
    """``add_attachments`` copies the File rows; ``mail_attachments`` sends their bytes.

    The copy is what makes them show on the timeline - ``activities.py`` reads File rows
    attached to the Communication, not to the lead.
    """
    response = auth_api.post(
        MAKE,
        _payload(alice_lead, attachments=[row.name for row in uploaded_files]),
        format="json",
    )
    assert response.status_code == 200

    row = Communication.objects.get(pk=response.json()["message"]["name"])
    assert row.has_attachment is True

    copies = File.objects.filter(
        attached_to_doctype="Communication", attached_to_name=row.name
    ).order_by("creation", "pk")
    assert [c.file_url for c in copies] == ["/files/quote.pdf", "/private/files/terms.txt"]
    assert [c.is_private for c in copies] == [False, True]
    # The originals stay where they were - a copy, not a move.
    assert File.objects.filter(pk=uploaded_files[0].name).exists()

    # Django decodes a `text/*` attachment to `str` on the way in and leaves everything
    # else as bytes; both are the file's own content, read from `MEDIA_ROOT`.
    sent = {name: content for name, content, _type in mail.outbox[0].attachments}
    assert sent == {"quote.pdf": b"%PDF-1.4 quote", "terms.txt": "strictly confidential"}
    types = {name: mimetype for name, _content, mimetype in mail.outbox[0].attachments}
    assert types == {"quote.pdf": "application/pdf", "terms.txt": "text/plain"}
    assert mimetypes.guess_type("quote.pdf")[0] == "application/pdf"


def test_a_stale_attachment_name_is_skipped_not_fatal(
    auth_api, alice_lead, outgoing_account, uploaded_files
):
    """**Deliberate divergence.** Upstream reads ``attach.file_url`` off the ``None`` that
    ``frappe.db.get_value`` returned and 500s, losing the email with it."""
    response = auth_api.post(
        MAKE,
        _payload(alice_lead, attachments=[uploaded_files[0].name, "no-such-file"]),
        format="json",
    )
    assert response.status_code == 200

    row = Communication.objects.get(pk=response.json()["message"]["name"])
    assert (
        File.objects.filter(attached_to_doctype="Communication", attached_to_name=row.name).count()
        == 1
    )
    assert [a[0] for a in mail.outbox[0].attachments] == ["quote.pdf"]


def test_a_file_whose_bytes_are_gone_does_not_lose_the_email(
    auth_api, alice_lead, outgoing_account, uploaded_files, settings, tmp_path
):
    """The row is there, the bytes are not. The email still goes, minus that file."""
    (tmp_path / "files/quote.pdf").unlink()

    response = auth_api.post(
        MAKE,
        _payload(alice_lead, attachments=[row.name for row in uploaded_files]),
        format="json",
    )
    assert response.status_code == 200
    assert [a[0] for a in mail.outbox[0].attachments] == ["terms.txt"]


# --- the account ------------------------------------------------------------------------------


def test_no_outgoing_account_refuses_but_keeps_the_row(auth_api, alice_lead):
    """``_make`` inserts **before** it checks for an account, so what the user typed
    survives the refusal. Reproduced deliberately: losing the draft would be worse."""
    response = auth_api.post(MAKE, _payload(alice_lead), format="json")

    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "OutgoingEmailError"
    assert body["message"] == (
        "Unable to send mail because of a missing email account. "
        "Please setup default Email Account from Settings > Email Account"
    )

    row = Communication.objects.filter(
        reference_doctype="CRM Lead", reference_name=alice_lead.name
    ).first()
    assert row is not None and row.subject == SUBJECT
    assert row.communication_date is None
    assert mail.outbox == []


def test_the_account_matching_the_sender_wins_over_the_default(
    auth_api, alice_lead, outgoing_account, administrator
):
    """``find_outgoing(match_by_email=...)`` is tried before ``find_default_outgoing``."""
    with session_user(administrator.name):
        mine = EmailAccount.objects.create(
            email_account_name="Alice",
            email_id="Alice@Example.com",  # matched case-insensitively, as `parse_addr` is
            password="hunter2",
            smtp_server="smtp.example.com",
            smtp_port=587,
            enable_outgoing=True,
        )

    response = auth_api.post(MAKE, _payload(alice_lead), format="json")
    assert response.status_code == 200
    assert Communication.objects.get(
        pk=response.json()["message"]["name"]
    ).email_account == mine.name


def test_always_use_account_email_id_as_sender_replaces_the_address(
    auth_api, alice_lead, outgoing_account
):
    """``replace_sender`` (``email_body.py:300``): the display name stays, the address
    becomes the account's - which is what a relay that only accepts its own sender needs."""
    EmailAccount.objects.filter(pk=outgoing_account.name).update(
        always_use_account_email_id_as_sender=True
    )

    response = auth_api.post(MAKE, _payload(alice_lead), format="json")
    assert response.status_code == 200
    assert mail.outbox[0].from_email == "Alice <support@example.com>"


def test_a_transport_failure_on_the_inline_path_is_a_417(
    auth_api, alice_lead, outgoing_account, monkeypatch
):
    """``now`` has no retry behind it, so the caller is told what the relay said."""
    import smtplib

    class _Refusing:
        def send_messages(self, messages):
            raise smtplib.SMTPRecipientsRefused({"buyer@example.test": (550, b"nope")})

        def open(self):
            return True

        def close(self):
            return None

    monkeypatch.setattr(communication_service, "open_backend", lambda account: _Refusing())

    response = auth_api.post(MAKE, _payload(alice_lead), format="json")
    assert response.status_code == 417
    assert response.json()["exc_type"] == "ValidationError"
    assert Communication.objects.filter(
        reference_name=alice_lead.name
    ).first().communication_date is None


# --- permission ------------------------------------------------------------------------------


def test_a_lead_the_caller_cannot_read_is_refused(auth_api, bob_lead, outgoing_account):
    """Upstream checks ``ptype="email"``; the port has no such type, so this is ``read``
    on the reference document - the same roles, per ``crm_lead.json``'s permission rows."""
    before = Communication.objects.count()
    response = auth_api.post(MAKE, _payload(bob_lead), format="json")

    assert response.status_code == 403
    assert response.json()["exc_type"] == "PermissionError"
    assert Communication.objects.count() == before
    assert mail.outbox == []


def test_a_missing_lead_is_a_404(auth_api, outgoing_account):
    response = auth_api.post(
        MAKE,
        {
            "doctype": "CRM Lead",
            "name": "CRM-LEAD-0000-99999",
            "subject": SUBJECT,
            "content": BODY,
            "recipients": "buyer@example.test",
            "send_email": 1,
            "now": 1,
        },
        format="json",
    )
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_a_communication_referencing_nothing_is_allowed(auth_api, outgoing_account):
    """``if doctype and name`` upstream - a Communication need not hang off anything."""
    response = auth_api.post(
        MAKE,
        {
            "subject": SUBJECT,
            "content": BODY,
            "recipients": "buyer@example.test",
            "send_email": 1,
            "now": 1,
        },
        format="json",
    )
    assert response.status_code == 200
    row = Communication.objects.get(pk=response.json()["message"]["name"])
    assert row.reference_doctype == ""
    # No `sender` given, so it defaults to the session user's formatted email
    # (`get_formatted_email(frappe.session.user)`).
    assert row.sender == "Alice <alice@example.com>"
    # ...and no `sender_full_name`, so the display name on the *message* is the account's
    # own name, which is `mail_sender_fullname`'s fallback (mixins.py:157-162). The address
    # is still the sender's.
    assert mail.outbox[0].from_email == "Support <alice@example.com>"


def test_get_is_refused(auth_api, alice_lead):
    """POST only - upstream's ``make`` writes, and a GET that writes is a CSRF gift."""
    response = auth_api.get(MAKE, {"doctype": "CRM Lead", "name": alice_lead.name})
    assert response.status_code == 403
    assert mail.outbox == []


def test_it_needs_authentication(api, alice_lead):
    assert api.post(MAKE, _payload(alice_lead), format="json").status_code == 401
