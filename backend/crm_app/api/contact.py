"""``crm.api.contact.*`` - Group C. Ported from ``crm/api/contact.py``."""

from __future__ import annotations

from frappe_core import permissions
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.exceptions import throw
from frappe_core.query import fetch_rows
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist

#: ``crm/api/contact.py:47-57`` - the exact field list returned per linked deal.
LINKED_DEAL_FIELDS = [
    "name",
    "organization",
    "currency",
    "deal_value",
    "status",
    "email",
    "mobile_no",
    "deal_owner",
    "modified",
]


def _require_contact(contact: str, ptype: str):
    """Upstream guards each of these with ``frappe.has_permission("Contact", ...)``.

    Message is ``"Not permitted"`` verbatim (``crm/api/contact.py:33``).
    """
    from frappe_platform.models import Contact

    # Upstream asks has_permission("Contact", ptype, name), which is False for a name
    # that does not exist, so a missing contact is the same PermissionError as a denied
    # one - the frontend branches on that class (FINDINGS.md 12).
    instance = Contact._default_manager.filter(pk=contact).first()
    if instance is None or not permissions.check_object_permission(
        instance, ptype, get_current_user()
    ):
        raise FrappePermissionError("Not permitted")
    return instance


@whitelist("crm.api.contact.get_linked_deals")
def get_linked_deals(contact: str):
    """``crm/api/contact.py:29-60``.

    The deals are read through ``fetch_rows``, so a contact linked to a deal the caller
    cannot see yields nothing for that row. Upstream uses ``frappe.get_cached_doc``,
    which does **not** permission-filter - reproducing that would leak deal values
    across the sales hierarchy through a contact the user can legitimately read.
    Recorded as a deliberate divergence in docs/internal/PROGRESS_PHASE_3.md.
    """
    from crm_app.models import CRMContacts

    _require_contact(contact, "read")

    deal_names = list(
        CRMContacts._default_manager.filter(contact=contact, parenttype="CRM Deal")
        .exclude(parent_deal__isnull=True)
        .values_list("parent_deal", flat=True)
        .distinct()
    )
    if not deal_names:
        return []

    return fetch_rows(
        "CRM Deal",
        fields=LINKED_DEAL_FIELDS,
        filters={"name": ["in", deal_names]},
        limit_page_length=0,
    )


@whitelist("crm.api.contact.create_new")
def create_new(contact: str, field: str, value: str):
    """``crm/api/contact.py:63-80``.

    The first email/phone added becomes primary; later ones do not
    (``len(...) == 0`` upstream). Message ``"Invalid field"`` verbatim.
    """
    from frappe_platform.models import ContactEmail, ContactPhone

    instance = _require_contact(contact, "write")

    if field == "email":
        ContactEmail._default_manager.create(
            parent_contact=instance,
            email_id=value,
            is_primary=not instance.email_ids.exists(),
        )
    elif field in ("mobile_no", "phone"):
        ContactPhone._default_manager.create(
            parent_contact=instance,
            phone=value,
            is_primary_mobile_no=not instance.phone_nos.exists(),
        )
    else:
        throw("Invalid field")

    return True


@whitelist("crm.api.contact.set_as_primary")
def set_as_primary(contact: str, field: str, value: str):
    """``crm/api/contact.py:87-111``. Exactly one row ends up flagged.

    Upstream flags the rows in memory and saves the contact once, so its "only one can
    be primary" check sees the finished table. Saving the rows one at a time does not:
    each row's save re-derives the contact (the rows' own signal), and at the moment the
    new primary is written the old one is still flagged. That threw "Only one Mobile No
    can be set as primary." and left both rows flagged, after which nothing on the
    contact would save (FINDINGS.md 67).

    So the flags are written as two set-based updates, which fire no per-row signal, the
    old ones cleared first, inside one transaction; the contact is derived once at the
    end, and a refusal there undoes the flags.
    """
    from django.db import transaction

    instance = _require_contact(contact, "write")

    if field == "email":
        rows, column, flag = instance.email_ids, "email_id", "is_primary"
    elif field in ("mobile_no", "phone"):
        rows, column = instance.phone_nos, "phone"
        flag = "is_primary_mobile_no" if field == "mobile_no" else "is_primary_phone"
    else:
        throw("Invalid field")

    with transaction.atomic():
        rows.exclude(**{column: value}).update(**{flag: False})
        rows.filter(**{column: value}).update(**{flag: True})
        instance.sync_primary_values()
        type(instance)._default_manager.filter(pk=instance.pk).update(
            email_id=instance.email_id, mobile_no=instance.mobile_no, phone=instance.phone
        )
    return True


@whitelist("crm.api.contact.search_emails")
def search_emails(txt: str):
    """``crm/api/contact.py:109-145``.

    Returns **lists, not dicts** - upstream passes ``as_list=True``, and the frontend's
    email autocomplete indexes positionally. The order is
    ``[full_name, email_id, name]``, matching ``search_fields``.
    """
    search_fields = ["full_name", "email_id", "name"]
    filters = {"email_id": ["is", "set"]}
    or_filters = None
    if txt:
        or_filters = {f: ["like", f"%{txt}%"] for f in search_fields}

    rows = fetch_rows(
        "Contact",
        fields=search_fields,
        filters=filters,
        or_filters=or_filters,
        order_by="email_id asc, full_name asc, name asc",
        limit_start=0,
        limit_page_length=20,
    )
    return [[row[f] for f in search_fields] for row in rows]
