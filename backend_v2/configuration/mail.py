"""The saved Email Account lookups `core.mail` reaches through `MAIL_ACCOUNT_PROVIDER`
(specs/CONFIGURATION.md section 4.4, decision 7).

Product logic: which saved account a message goes through, and the default signature.
`core.mail` wraps both, so `core` and `accounts` never import this app.
"""

from __future__ import annotations

from email.utils import parseaddr

from configuration.models import EmailAccount


def _bare_address(value: str) -> str:
    """`frappe.utils.parse_addr(value)[1]`: `Jane <jane@x.test>` -> `jane@x.test`."""
    return parseaddr(value or "")[1]


def saved_outgoing_account(sender=None, reference_doctype=None):
    """Steps 1-3 of `EmailAccount.find_outgoing` (old `crm_app/communication.py:400-440`),
    each newest first: an outgoing account whose `email_id` is the sender's address; an
    incoming-and-outgoing account appending to the reference doctype; the default
    outgoing account. `None` when none matches (the config account is `core.mail`'s)."""
    accounts = EmailAccount._default_manager.order_by("-modified")
    address = _bare_address(sender or "")
    if address:
        account = accounts.filter(enable_outgoing=True, email_id__iexact=address).first()
        if account is not None:
            return account
    if reference_doctype:
        account = accounts.filter(
            enable_outgoing=True, enable_incoming=True, append_to=reference_doctype
        ).first()
        if account is not None:
            return account
    return accounts.filter(enable_outgoing=True, default_outgoing=True).first()


def default_signature():
    """The signature fallback (old `crm_app/api/misc.py:62-67`): the newest account with
    `default_outgoing` and `add_signature`, whether or not outgoing is enabled; `None`
    when there is none or its signature is empty. Several default accounts can coexist,
    as in `backend/`; the newest wins."""
    signature = (
        EmailAccount._default_manager.filter(default_outgoing=True, add_signature=True)
        .order_by("-modified")
        .values_list("signature", flat=True)
        .first()
    )
    return signature or None
