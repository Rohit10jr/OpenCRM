"""Edit or delete one Contact Email or Contact Phone row through its contact
(specs/CONTACTS.md §4 "The child-row routes", DECISIONS 60; old
`backend/crm_app/api/client.py:393-459`, upstream `frappe/client.py:213-223,551-572`).

`PATCH /api/v1/contacts/<name>/email-ids/<row>/` and `.../phone-nos/<row>/` answer the
contact's document; `DELETE` answers null. The row is looked up first, as the old route
does. Only the row's non-relation columns are written, never the four caches
(`API_CONTRACT.md:239`; PE-24's second sentence).
"""

from __future__ import annotations

from django.db import transaction

from contacts.models import Contact, ContactEmail, ContactPhone
from core.exceptions import DoesNotExistError, PermissionError, throw
from core.query import parse_json_param

#: `frappe.model.default_fields` and `child_table_fields` (old `client.py:376-389`).
STANDARD_FIELDS = frozenset(
    {
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "parent",
        "parentfield",
        "parenttype",
        "doctype",
    }
)
#: Never written through a row route (v2's invariant).
CACHE_FIELDS = frozenset({"_assign", "_liked_by", "_comments", "_user_tags"})

TABLES = {"email_ids": ContactEmail, "phone_nos": ContactPhone}


def _row_and_contact(contact_name: str, table: str, row_name: str):
    """A row that does not exist, belongs to another contact or to the other table, or a
    contact that does not exist: 404 "<DocType> <row> not found"."""
    model = TABLES[table]
    doctype = model.DOCTYPE
    row = model._default_manager.filter(pk=row_name, parent_contact_id=contact_name).first()
    contact = Contact._default_manager.filter(pk=contact_name).first() if row else None
    if row is None or contact is None:
        raise DoesNotExistError(f"{doctype} {row_name} not found")
    return model, row, contact


def edit_row(rules, user, contact_name: str, table: str, row_name: str, body) -> Contact:
    """`client.py:213-223`: update the row, save the contact, answer the contact."""
    model, row, contact = _row_and_contact(contact_name, table, row_name)
    if rules.has_object_rule(user, contact, "write") is False:
        raise PermissionError("Not permitted to write Contact", title="Not Permitted")

    values = parse_json_param(body, body)
    values = values if isinstance(values, dict) else {}
    editable = {key: val for key, val in values.items() if key not in STANDARD_FIELDS}
    if values and not editable:
        throw("Cannot edit standard fields")

    columns = {
        field.name
        for field in model._meta.concrete_fields
        if not field.is_relation and field.name not in STANDARD_FIELDS | CACHE_FIELDS
    }
    with transaction.atomic():
        for key, val in editable.items():
            if key in columns:
                setattr(row, key, val)
        row.save(user=user)
        # The row's signal re-derived the contact; the save re-validates the whole table,
        # as upstream's `doc.save()` does.
        contact.refresh_from_db()
        contact.save(user=user)
    return contact


def delete_row(rules, user, contact_name: str, table: str, row_name: str) -> None:
    """`client.py:551-572`: a caller who may not write the contact is told the doctype
    does not exist, never 403."""
    model, row, contact = _row_and_contact(contact_name, table, row_name)
    if rules.has_object_rule(user, contact, "write") is False:
        raise DoesNotExistError(f"DocType {model.DOCTYPE} not found")
    with transaction.atomic():
        row.delete()
        contact.refresh_from_db()
        contact.save(user=user)
