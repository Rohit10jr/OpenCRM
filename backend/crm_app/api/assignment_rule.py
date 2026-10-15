"""``crm.api.assignment_rule.*``. Ported from ``crm/api/assignment_rule.py``."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Exists, OuterRef

from crm_app.api.client import client_insert
from frappe_core import permissions, registry
from frappe_core.exceptions import DoesNotExistError, PermissionError as FrappePermissionError
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist
from frappe_platform.models import AssignmentRule, AssignmentRuleUser


@whitelist("crm.api.assignment_rule.get_assignment_rules_list")
def get_assignment_rules_list():
    """``crm/api/assignment_rule.py:4-24``.

    Deliberately does not apply Assignment Rule's permission hook. Upstream reads with
    ``frappe.get_all``, so every signed-in user gets this small list despite the doctype
    being System Manager-only. ``UPSTREAM_BUGS.md`` 55 records the reproduced exception.
    """
    users = AssignmentRuleUser.objects.filter(parent=OuterRef("pk"))
    return list(
        AssignmentRule.objects.filter(document_type__in=("CRM Lead", "CRM Deal"))
        .annotate(users_exists=Exists(users))
        .values("name", "description", "disabled", "priority", "users_exists")
    )


@whitelist("crm.api.assignment_rule.duplicate_assignment_rule")
def duplicate_assignment_rule(docname: str, new_name: str):
    """``crm/api/assignment_rule.py:27-32``.

    The source document is copied through ``frappe.client.insert``'s implementation, so
    create permission and Assignment Rule's validations are identical at both doors.
    In particular, bug 53 is reproduced: a Sales Manager can see Duplicate but cannot
    create the copy.
    """
    source = AssignmentRule.objects.filter(pk=docname).first()
    if source is None:
        raise DoesNotExistError(f"Assignment Rule {docname} not found")

    serializer = registry.get_entry("Assignment Rule").get_serializer_class()
    payload = dict(serializer(source).data)
    payload["name"] = new_name

    # This explicit copy of insert's check keeps the endpoint allowlist honest. The
    # candidate has the source rule's complete field values; client_insert repeats the
    # same check before it writes, so this cannot become a substitute for that path.
    if not permissions.check_object_permission(source, "create", get_current_user()):
        raise FrappePermissionError(
            "Not permitted to create Assignment Rule", title="Not Permitted"
        )

    with transaction.atomic():
        client_insert(doc=payload)
        # These engine-owned fields are read-only to API callers, but upstream copies
        # them with the rest of the loaded document before insert.
        AssignmentRule.objects.filter(pk=new_name).update(
            last_user_id=source.last_user_id,
            current_index=source.current_index,
        )
        copied = AssignmentRule.objects.get(pk=new_name)
    return serializer(copied).data
