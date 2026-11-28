"""The contact calls: `crm.api.contact.create_new`, `set_as_primary`, `search_emails`
(specs/CONTACTS.md §4 "The contact calls", "Primary email and phone" (h)-(i), PE-12f,
§11.2; old `backend/crm_app/api/contact.py:26-170`). Messages verbatim.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max

from contacts.models import Contact, ContactEmail, ContactPhone
from core.exceptions import PermissionError, ValidationError, throw
from core.query import fetch_rows

SEARCH_FIELDS = ["full_name", "email_id", "name"]


def _require_contact(rules, user, name, ptype: str) -> Contact:
    """`contact.py:26-41`: a missing or refused contact is the same 403 "Not permitted",
    before the field is checked (FINDINGS 12). The base 404 lookup is not used."""
    contact = Contact._default_manager.filter(pk=name).first() if name else None
    if contact is None or rules.has_object_rule(user, contact, ptype) is False:
        raise PermissionError("Not permitted", title="Not Permitted")
    return contact


def _required(value, message: str):
    """PE-12f: a missing argument is 417 with a fixed sentence, not a crash."""
    if value is None:
        raise ValidationError(message)
    return value


def _next_idx(rows) -> int:
    """Upstream's `append` numbers a new row `len(table) + 1`; the highest `idx` plus one
    is the same while the table has no gaps, and stays unique after a delete (PE-36)."""
    return (rows.aggregate(top=Max("idx"))["top"] or 0) + 1


def create_new(rules, user, contact: str, field, value) -> bool:
    """`contact.py:63-80`: the first email or number is primary, later ones are not; the
    row gets the next `idx` (PE-36). The row's save fires the row signal, which
    re-derives the mirror columns and `user` (§11.2, PE-35) with `update()`; both run in
    one transaction."""
    instance = _require_contact(rules, user, contact, "write")
    field = _required(field, "Field is required")
    value = _required(value, "Value is required")
    if field == "email":
        model, rows, values = ContactEmail, instance.email_ids, {"email_id": value}
        values["is_primary"] = not rows.exists()
    elif field in ("mobile_no", "phone"):
        model, rows, values = ContactPhone, instance.phone_nos, {"phone": value}
        values["is_primary_mobile_no"] = not rows.exists()
    else:
        throw("Invalid field")
    with transaction.atomic():
        # Two calls on one contact would read the same highest idx: lock the contact.
        Contact._default_manager.select_for_update().filter(pk=instance.pk).first()
        model(parent_contact=instance, idx=_next_idx(rows), **values).save(user=user)
    return True


def set_as_primary(rules, user, contact: str, field, value) -> bool:
    """`contact.py:87-111` (FINDINGS 67): the flags as two set-based updates in one
    transaction, the old ones cleared first, then one derive written with `update()`
    (`user` with it, §11.2); a refusal there rolls the flags back."""
    instance = _require_contact(rules, user, contact, "write")
    field = _required(field, "Field is required")
    value = _required(value, "Value is required")
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
        Contact._default_manager.filter(pk=instance.pk).update(
            email_id=instance.email_id,
            mobile_no=instance.mobile_no,
            phone=instance.phone,
            user_id=instance.user_id,
        )
    return True


def search_emails(queryset, user, txt) -> list[list]:
    """`contact.py:141-164`: contacts with an email, `like` on full name, email or name,
    ordered `email_id, full_name, name`, 20 rows, each a **list**
    `[full_name, email_id, name]` (the frontend indexes positionally). `queryset` is the
    resource's, so the Contact list rule applies (PE-29)."""
    txt = _required(txt, "Search text is required")
    or_filters = None
    if txt:
        or_filters = {field: ["like", f"%{txt}%"] for field in SEARCH_FIELDS}
    rows = fetch_rows(
        queryset,
        user=user,
        fields=SEARCH_FIELDS,
        filters={"email_id": ["is", "set"]},
        or_filters=or_filters,
        order_by="email_id asc, full_name asc, name asc",
        limit_start=0,
        limit_page_length=20,
    )
    return [[row[field] for field in SEARCH_FIELDS] for row in rows]
