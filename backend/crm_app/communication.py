"""The model half of ``frappe.core.doctype.communication.email.make``.

`crm_app/api/communication.py` is the endpoint; everything that touches a table lives
here, because an api module may not reach a manager directly
(`tests/test_phase3_endpoints.py::test_no_endpoint_bypasses_the_permission_layer`). The
split is not only a lint rule: the Celery task needs the same code with no request around
it, so "build the row, pick the account, build the message, send it" has to be callable
from both sides.

Ported from, in order:

* ``frappe/core/doctype/communication/email.py`` — ``_make`` (the row), ``validate_email``
  (the addresses), ``add_attachments`` (the file copies)
* ``frappe/core/doctype/communication/mixins.py`` — ``mail_recipients`` / ``mail_cc`` /
  ``mail_bcc`` (who actually receives it), ``mail_sender`` / ``mail_sender_fullname`` /
  ``get_mail_sender_with_displayname`` (the From), ``get_outgoing_email_account``
* ``frappe/email/doctype/email_account/email_account.py`` — ``find_outgoing`` /
  ``find_default_outgoing`` / ``find_from_config``
* ``frappe/email/email_body.py`` — ``get_message_id``, ``replace_sender``,
  ``set_message_id``, ``set_in_reply_to``

### Settled decisions (PHASE_8 follow-up, agreed with the user)

**Transport is per Email Account.** The SMTP connection is built from the account's own
``smtp_server`` / ``smtp_port`` / TLS flags / login / decrypted password, the way
:func:`frappe_core.mail.check_smtp` builds it — *not* a global SMTP from `.env`. Checking
credentials with one stack and sending with another is how a check passes where sending
fails, and the check was already written against Django's backend.

The one account that *does* send through Django's configured backend and settings is the
**config account** (:func:`config_account`, FINDINGS.md 79): upstream's
``find_from_config``, the unsaved Email Account built from ``site_config.json``, whose
port reads Django's own ``EMAIL_*`` settings. It is not a row, it carries system mail and
any lead mail no saved account matches, and it exists only while ``EMAIL_HOST`` is set.

**Sending is queued through Celery**, which is this port's Email Queue (phase 5). The
task retries on ``smtplib.SMTPException`` / ``OSError`` exactly as ``send_invitation_email``
does. Upstream's ``now`` argument is honoured: ``now`` truthy sends inside the request. The
frontend never sends ``now``; the `.http` blocks and hand testing do.

**The sent stamp is ``communication_date``.** Upstream marks delivery on
``Communication.delivery_status`` and on the ``Email Queue`` row, and this port models
neither. See the field's own comment in ``frappe_platform/models.py`` for why nothing
observes the difference. The stamp is a *claim*, taken under a row lock before the
message goes out (see :func:`send_communication`), so two deliveries of the same task
cannot both send.

### Not ported

Read receipts and the tracking pixel, ``print_format`` / ``print_html`` /
``print_letterhead`` / ``print_language``, ``send_after``, unsubscribe lists (so
``emails_not_sent_to`` is always ``""``), inbound mail over IMAP, and ``Email Queue`` as a
table.
"""

from __future__ import annotations

import email.utils
import logging
import mimetypes
from email.utils import formataddr, parseaddr
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone
from django.utils.html import strip_tags

from frappe_core import registry
from frappe_core.models import validate_email_address

logger = logging.getLogger(__name__)

#: ``frappe.STANDARD_USERS`` (``frappe/__init__.py:89``), matched case-insensitively —
#: see :func:`_recipient_lists`.
STANDARD_USERS = ("guest", "administrator")


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------


def _split_emails(raw) -> list[str]:
    """``frappe.utils.split_emails``: a comma- (or newline-) separated address string."""
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        entries = [str(item) for item in raw]
    else:
        entries = str(raw).replace("\n", ",").split(",")
    return [entry.strip() for entry in entries if entry and entry.strip()]


def list_to_str(value) -> str:
    """``frappe.utils.list_to_str``: ``_make`` accepts a list or an already-joined string.

    The CRM frontend joins with ``", "`` itself (``CommunicationArea.vue:216``); other
    callers pass a list.
    """
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value)


def bare_address(value: str) -> str:
    """``frappe.utils.parse_addr(value)[1]`` — ``Jane <jane@x.test>`` -> ``jane@x.test``."""
    return parseaddr(value or "")[1]


def _deduped(entries: list[str]) -> list[tuple[str, str]]:
    """``[(lowercased bare address, the entry as written)]``, first spelling wins.

    Upstream's ``_get_emails_list`` builds a ``set`` of lowercased bare addresses and
    ``get_email_with_displayname`` maps each back to whichever spelling carried a display
    name. Same result, in the order the caller wrote them — a ``set`` would reorder the
    To header on every send and make it untestable.
    """
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for entry in entries:
        address = bare_address(entry).lower()
        if not address or address in seen:
            continue
        seen.add(address)
        out.append((address, entry))
    return out


def copy_address_for(user: str, sender: str) -> str:
    """``mail_cc(include_sender=True)``, ``mixins.py:88-93``: "send me a copy" goes to the
    *logged-in user's* own email, and to the sender only when that user is a standard
    user (Administrator, Guest) with no mailbox of their own. Resolved at request time
    and carried into the task as an address, because a worker has no session user to
    ask - which is what makes the queued and the inline send agree."""
    if user in ("Administrator", "Guest"):
        return bare_address(sender)
    from frappe_platform.models import User

    row = User._default_manager.filter(pk=user).only("email").first()
    return (row.email if row is not None and row.email else user) or bare_address(sender)


def _recipient_lists(communication, copy_to: str | None = None):
    """``mail_recipients`` / ``mail_cc`` / ``mail_bcc``: who the message actually goes to.

    * an address in ``to`` is dropped from ``cc`` and from ``bcc``. **Not from both to
      ``bcc``**: upstream subtracts only ``mail_recipients`` there, so an address written
      into ``cc`` *and* ``bcc`` is genuinely addressed twice. That is visible to the
      recipient, so it is reproduced rather than tidied up;
    * ``copy_to`` (the resolved "send me a copy" address, see :func:`copy_address_for`)
      joins ``cc`` — upstream adds it at *send* time, not on the stored row, so the
      ``cc`` column stays what the caller typed;
    * ``frappe.STANDARD_USERS`` are dropped.

    One small departure, stated rather than assumed: ``STANDARD_USERS`` is matched
    case-insensitively, which upstream's is not - ``to_list`` lowercases every address
    before ``mail_recipients`` compares it against the literal ``"Administrator"``, so
    upstream's filter can never fire. It is unreachable from this endpoint anyway —
    ``validate_email_address`` rejects ``Administrator`` as an address long before this
    runs — so implementing what upstream meant costs nothing.
    """
    to = _deduped(_split_emails(communication.recipients))

    cc_entries = _split_emails(communication.cc)
    if copy_to:
        cc_entries.append(copy_to)
    cc = _deduped(cc_entries)
    bcc = _deduped(_split_emails(communication.bcc))

    def keep(pairs, *taken):
        blocked = {address for group in taken for address, _ in group}
        return [
            entry
            for address, entry in pairs
            if address not in blocked and address not in STANDARD_USERS
        ]

    return keep(to), keep(cc, to), keep(bcc, to)


# ---------------------------------------------------------------------------
# Message-ID
# ---------------------------------------------------------------------------


def site_domain() -> str:
    """``frappe.local.site`` — the host mail from this deployment claims to come from.

    Upstream's site name *is* the domain. Here it is ``SITE_URL``'s hostname, with the
    port dropped: a port is legal in a URL and not in the right-hand side of a Message-ID.
    """
    return urlsplit(settings.SITE_URL).hostname or "localhost"


def new_message_id() -> str:
    """``get_message_id()`` (``email_body.py:517``), stored the way ``_make`` stores it.

    ``email.utils.make_msgid(domain=...)`` returns ``<unique@domain>``; upstream keeps the
    inside (``get_string_between("<", ..., ">")``) on the row and puts the brackets back
    when it writes the header.
    """
    return email.utils.make_msgid(domain=site_domain()).strip("<>")


# ---------------------------------------------------------------------------
# The row
# ---------------------------------------------------------------------------


def validate_addresses(communication_type: str, communication_medium: str, *values) -> None:
    """``email.py:validate_email`` — every recipient, cc and bcc address is checked.

    Upstream's guard is kept: only a ``Communication`` sent over ``Email`` is validated, so
    a Comment-shaped row or a phone call is not held to address syntax. The port's
    :func:`frappe_core.models.validate_email_address` is
    ``frappe.utils.validate_email_address(throw=True)`` and raises
    ``InvalidEmailAddressError`` with upstream's sentence, "<addr> is not a valid Email
    Address" (417).
    """
    if communication_type != "Communication" or communication_medium != "Email":
        return
    for value in values:
        for address in _split_emails(value):
            validate_email_address(address)


def formatted_email(user) -> str:
    """``frappe.utils.get_formatted_email(frappe.session.user)`` — ``Full Name <email>``.

    Falls back to the bare address when the User row carries no name, and to the user id
    when it carries no email (``Administrator``'s row may not).
    """
    from frappe_platform.models import User

    row = User._default_manager.filter(pk=user).values("full_name", "email").first()
    if row is None:
        return str(user)
    address = row["email"] or str(user)
    full_name = row["full_name"] or ""
    return formataddr((full_name, address)) if full_name else address


def create_communication(
    *,
    doctype=None,
    name=None,
    content=None,
    subject=None,
    sent_or_received="Sent",
    sender=None,
    sender_full_name=None,
    recipients=None,
    communication_medium="Email",
    attachments=None,
    cc=None,
    bcc=None,
    communication_type=None,
    in_reply_to=None,
):
    """``email.py:_make``'s first half: build the row and insert it.

    Saved through the registry serializer, so the same validation, defaults and
    ``owner``/``modified`` stamping apply as on ``/api/resource/`` — a bare ``create()``
    here would quietly acquire a second set of semantics for the same table.

    Upstream inserts with ``ignore_permissions=True``; the *caller* has already been
    checked against the reference document, which is where the decision belongs.
    """
    communication_type = communication_type or "Communication"
    recipients = list_to_str(recipients)
    cc = list_to_str(cc)
    bcc = list_to_str(bcc)

    validate_addresses(communication_type, communication_medium, recipients, cc, bcc)

    entry = registry.get_entry("Communication")
    serializer = entry.get_serializer_class()(
        data={
            "subject": subject or "",
            "content": content or "",
            "sender": sender or "",
            "sender_full_name": sender_full_name or "",
            "recipients": recipients,
            "cc": cc,
            "bcc": bcc,
            "communication_medium": communication_medium or "",
            "sent_or_received": sent_or_received or "",
            "reference_doctype": doctype or "",
            "reference_name": str(name) if name else "",
            "communication_type": communication_type,
            "message_id": new_message_id(),
            "in_reply_to": in_reply_to or "",
            "has_attachment": bool(attachments),
        }
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save()


def add_attachments(communication_name: str, attachments) -> int:
    """``email.py:add_attachments`` — each named File is copied onto the Communication.

    Returns how many copies were made.

    Only the *File name* form is accepted. Upstream also takes a ``{"fname", "fcontent"}``
    dict from ``frappe.attach_print``; the CRM frontend never sends one
    (``CommunicationArea.vue:217`` maps uploads to ``x.name``), and the rendered print it
    would carry has no producer here — so it takes upstream's own ``else: continue``
    branch. (Storing bytes is ``File._content`` + ``save()`` since FINDINGS.md 49.)

    **A File name that no longer exists is skipped**, where upstream crashes:
    ``frappe.db.get_value`` returns ``None`` and the next line reads ``attach.file_url``
    off it. A stale name in the uploader's list is a 500 and a lost email upstream; here it
    is one missing attachment. The divergence is deliberate — reproducing a crash helps
    nobody.
    """
    from frappe_platform.models import File

    copied = 0
    for attachment in attachments or []:
        if not isinstance(attachment, str):
            continue
        source = File._default_manager.filter(pk=attachment).first()
        if source is None:
            logger.warning(
                "Communication %s: attachment %r no longer exists, skipped",
                communication_name,
                attachment,
            )
            continue
        File._default_manager.create(
            file_url=source.file_url,
            file_name=source.file_name,
            is_private=source.is_private,
            file_size=source.file_size,
            attached_to_doctype="Communication",
            attached_to_name=str(communication_name),
            folder="Home/Attachments",
        )
        copied += 1
    return copied


# ---------------------------------------------------------------------------
# The account
# ---------------------------------------------------------------------------


def config_account():
    """``EmailAccount.find_from_config`` (``email_account.py:493-498``) — the account
    ``site_config.json`` describes, read here from Django's mail settings.

    ``None`` unless ``EMAIL_HOST`` is set, as upstream's
    ``get_account_details_from_site_config`` returns ``{}`` while ``mail_server`` is unset
    (``email_account.py:563-565``). Otherwise an **unsaved** ``Email Account``
    (``from_record``, ``email_account.py:478-481``) carrying the settings as the fields the
    rest of this module reads — the From rules in :func:`sender_with_displayname`, the name
    and address that make upstream's ``default_sender`` for system mail — and
    ``from_site_config``, upstream's ``_from_site_config``, which :func:`open_backend` reads
    to send it through Django's configured backend rather than an SMTP session of its own.
    The settings are read at call time so ``override_settings`` works in tests.

    The password is deliberately not set: it is an encrypted column, and nothing reads it
    for this account — ``django.core.mail.get_connection`` takes the credentials from the
    settings itself. On Frappe Cloud this is the account a site with no Email Account
    sends from (``notifications@<site>``); it is not a document, so Settings shows nothing.
    FINDINGS.md 79.
    """
    from frappe_platform.models import EmailAccount

    host = settings.EMAIL_HOST
    if not host:
        return None

    login = settings.EMAIL_HOST_USER or ""
    address = settings.DEFAULT_FROM_EMAIL
    account = EmailAccount(
        email_account_name=settings.EMAIL_SENDER_NAME,
        email_id=address,
        enable_outgoing=True,
        smtp_server=host,
        smtp_port=settings.EMAIL_PORT,
        use_tls=bool(settings.EMAIL_USE_TLS),
        use_ssl_for_outgoing=bool(settings.EMAIL_USE_SSL),
        login_id=login,
        login_id_is_different=bool(login) and login != address,
        no_smtp_authentication=not login,
        always_use_account_email_id_as_sender=bool(
            settings.EMAIL_ALWAYS_USE_ACCOUNT_EMAIL_ID_AS_SENDER
        ),
    )
    account.from_site_config = True
    return account


def find_outgoing_account(sender=None, reference_doctype=None):
    """``EmailAccount.find_outgoing`` + ``find_default_outgoing`` (``email_account.py:506-540``).

    Four steps, upstream's order:

    1. an outgoing-enabled account whose ``email_id`` *is* the sender's address;
    2. an account that is both incoming- and outgoing-enabled and appends to the reference
       doctype — the CRM configures exactly this (``crm/api/settings.py:36`` sets
       ``append_to = "CRM Lead"``), so leaving it out would pick a different account than
       upstream for any deployment with an inbox;
    3. the default outgoing account;
    4. the config account (``find_from_config``, ``email_account.py:538``), with Django's
       mail settings standing in for ``site_config.json`` — see :func:`config_account`.
       ``None`` while ``EMAIL_HOST`` is unset.

    Called with no arguments this is what ``frappe.sendmail`` reaches with no sender
    (``QueueBuilder.sender``, ``email_queue.py:719-724``): steps 3 and 4, which is how
    system mail finds its carrier (``crm_app.mail``).

    Upstream's last fallback, ``create_dummy``, is not ported: it exists only for
    ``mute_emails``, a test flag.
    """
    from frappe_platform.models import EmailAccount

    address = bare_address(sender or "")
    if address:
        account = EmailAccount._default_manager.filter(
            enable_outgoing=True, email_id__iexact=address
        ).first()
        if account is not None:
            return account

    if reference_doctype:
        account = EmailAccount._default_manager.filter(
            enable_outgoing=True, enable_incoming=True, append_to=reference_doctype
        ).first()
        if account is not None:
            return account

    account = EmailAccount._default_manager.filter(
        enable_outgoing=True, default_outgoing=True
    ).first()
    if account is not None:
        return account

    return config_account()


def outgoing_account_for(communication):
    """``mixins.py:get_outgoing_email_account`` — find it, and record it on the row.

    ``db_set("email_account", ...)`` upstream; an ``update()`` here for the same reason
    ``toggle_like`` uses one: stamping which account sent a message is not an edit of the
    message and must not bump ``modified``, which is the default list sort.

    **The config account is not stamped.** ``email_account`` names a row, and the config
    account has none: upstream writes its virtual ``name`` ("Frappe") into that Link field,
    where it points at nothing. Here the stamp is read back by the lookup above it, so a
    stamp of "Frappe" would make the next call find no account and the queued send give
    up; a stamp that names nothing is not worth keeping.
    """
    from frappe_platform.models import Communication, EmailAccount

    if communication.email_account:
        return EmailAccount._default_manager.filter(pk=communication.email_account).first()

    account = find_outgoing_account(communication.sender, communication.reference_doctype)
    if account is not None and account.pk and communication.sent_or_received == "Sent":
        Communication._default_manager.filter(pk=communication.pk).update(
            email_account=account.pk
        )
        communication.email_account = account.pk
    return account


# ---------------------------------------------------------------------------
# The message
# ---------------------------------------------------------------------------


def attachment_path(file_url: str):
    """``/files/x.pdf`` -> ``media/files/x.pdf``, ``/private/files/x.pdf`` -> ``media/private/files/x.pdf``.

    ``File.file_url`` is a URL string rather than a Django ``FileField``
    (PHASE_1_MODELS.md §2), so the mapping is done here. Returns ``None`` when the bytes
    are not on disk *or* when the path escapes ``MEDIA_ROOT`` — a ``file_url`` is a
    database value and a row saying ``../../etc/passwd`` must not be readable as an
    attachment.
    """
    if not file_url:
        return None
    relative = str(file_url).split("?")[0].split("#")[0].lstrip("/")
    if not relative:
        return None
    root = Path(settings.MEDIA_ROOT).resolve()
    try:
        candidate = (root / relative).resolve()
    except OSError:
        return None
    if candidate != root and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def sender_with_displayname(communication, account) -> str:
    """``get_mail_sender_with_displayname`` + ``replace_sender`` (``email_body.py:300``).

    The display name is the sender's full name, falling back to the account's own name and
    then to ``Notification`` (``mail_sender_fullname``, ``mixins.py:157-162``). The address
    is the sender's, falling back to the account's (``mail_sender``) — and *replaced* by
    the account's when ``always_use_account_email_id_as_sender`` is set, which is what that
    flag means: the relay will only accept its own envelope sender.

    ``always_use_account_name_as_sender_name`` is not ported; the port's ``Email Account``
    has no such column.
    """
    display = communication.sender_full_name or account.email_account_name or "Notification"
    address = bare_address(communication.sender) or account.email_id
    if account.always_use_account_email_id_as_sender:
        address = account.email_id
    return formataddr((display, address))


def build_message(communication, account, copy_to: str | None = None):
    """``sendmail_input_dict`` + ``EmailBody``, as a Django message. ``None`` if nobody.

    Upstream returns an empty dict from ``sendmail_input_dict`` when recipients, cc and bcc
    are all empty and ``send_email`` then does nothing; ``None`` here says the same.

    The body is sent as HTML with a plain-text alternative, because the content the editor
    produces is HTML (``<p>...</p>``) and a text-only part is what a client without HTML,
    and most spam filters, read.
    """
    from frappe_platform.models import Communication, File

    to, cc, bcc = _recipient_lists(communication, copy_to=copy_to)
    if not (to or cc or bcc):
        return None

    headers = {}
    if communication.message_id:
        headers["Message-ID"] = f"<{communication.message_id}>"
    if communication.in_reply_to:
        parent = (
            Communication._default_manager.filter(pk=communication.in_reply_to)
            .values_list("message_id", flat=True)
            .first()
        )
        if parent:
            headers["In-Reply-To"] = f"<{parent}>"

    html = communication.content or ""
    message = EmailMultiAlternatives(
        subject=communication.subject or "",
        body=strip_tags(html),
        from_email=sender_with_displayname(communication, account),
        to=to,
        cc=cc,
        bcc=bcc,
        headers=headers,
    )
    message.attach_alternative(html, "text/html")

    for attachment in File._default_manager.filter(
        attached_to_doctype="Communication", attached_to_name=str(communication.pk)
    ).order_by("creation", "pk"):
        path = attachment_path(attachment.file_url)
        if path is None:
            # Upstream lets the read raise and the whole send fails. One unreadable
            # attachment losing the email is a worse outcome than an email arriving
            # without it, and the warning says which file to go and look for.
            logger.warning(
                "Communication %s: attachment %s (%s) is not on disk, not attached",
                communication.pk,
                attachment.pk,
                attachment.file_url,
            )
            continue
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        message.attach(attachment.file_name or path.name, path.read_bytes(), content_type)

    return message


def open_backend(account):
    """The connection for one ``Email Account``.

    The config account (:func:`config_account`) is the one account whose transport is
    Django's configured backend and settings: ``get_connection()`` reads ``EMAIL_HOST``,
    ``EMAIL_PORT``, the login and the TLS flags itself, through whatever ``EMAIL_BACKEND``
    names — so the console backend carries it in development. Every saved account still
    sends through its own SMTP details, built the way :func:`frappe_core.mail.check_smtp`
    builds the connection it validates the account with, so what was checked at save time
    is what sends:

    * ``use_ssl_for_outgoing`` -> implicit TLS (``use_ssl``). Django refuses both flags at
      once, so ``use_tls`` is dropped when it is set; the default port follows.
    * ``no_smtp_authentication`` -> no username and no password, matching
      ``check_smtp(authenticate=False)``.
    * ``login_id`` when ``login_id_is_different``, else ``email_id`` — upstream's
      ``EmailAccount.get_smtp_server`` rule.

    **This is the one function the tests patch.** Returning a
    ``locmem.EmailBackend`` from it puts the built message in ``django.core.mail.outbox``,
    which is what makes everything above assertable without a mail server. (The config
    account needs no patch: under the test settings ``get_connection()`` *is* locmem.)
    """
    from django.core.mail import get_connection
    from django.core.mail.backends.smtp import EmailBackend

    from frappe_core import mail as mail_checks

    if getattr(account, "from_site_config", False):
        # The same explicit timeout as below. The base backend takes it as a keyword too,
        # so the console and locmem backends accept it.
        return get_connection(fail_silently=False, timeout=mail_checks._timeout())

    # One source for the flags, shared with the save-time check (`validate_email_account`),
    # so what was checked is what sends.
    smtp = mail_checks.smtp_settings(account, account.get_password("password"))
    return EmailBackend(
        **smtp,
        # The same explicit timeout `check_smtp` passes, and for the same reason: without
        # one an unreachable relay blocks until the OS gives up.
        timeout=mail_checks._timeout(),
        fail_silently=False,
    )


def send_communication(name: str, copy_to: str | None = None) -> bool:
    """Send an already-inserted Communication. ``True`` if a message went out.

    Called inline when ``make(now=1)`` and from ``crm.send_communication_email`` otherwise.

    **Idempotent**, which a Celery task has to be (`PHASE_5_ASYNC.md` §5), and safe
    against two deliveries at once: the row is *claimed* first - ``communication_date``
    is stamped under a row lock and committed - and only then does the message go out.
    A second delivery, concurrent or later, finds the stamp and returns. A send that
    raises clears the stamp again, so the retry does the work. A process killed between
    the claim and the send leaves the row stamped and the mail unsent, which is what an
    ``Email Queue`` row stuck in "Sending" is upstream: both err toward no duplicate.

    Transport failures are raised, not swallowed: the task retries on them and the
    inline caller turns them into a 417.
    """
    from django.db import transaction

    from frappe_platform.models import Communication

    with transaction.atomic():
        communication = (
            Communication._default_manager.select_for_update().filter(pk=name).first()
        )
        if communication is None:
            logger.warning("Communication %s no longer exists, not sending", name)
            return False
        if communication.communication_date:
            return False

        account = outgoing_account_for(communication)
        if account is None:
            # `make` refuses with OutgoingEmailError before enqueueing, so this is the
            # account having been deleted or disabled between the request and the worker.
            logger.warning("Communication %s: no outgoing Email Account, not sending", name)
            return False

        message = build_message(communication, account, copy_to=copy_to)
        if message is None:
            return False

        # update(), not save(): the claim is not an edit of the message and must not bump
        # `modified`, which is the default list sort.
        Communication._default_manager.filter(pk=name).update(communication_date=timezone.now())

    try:
        message.connection = open_backend(account)
        message.send(fail_silently=False)
    except Exception:
        Communication._default_manager.filter(pk=name).update(communication_date=None)
        raise
    return True
