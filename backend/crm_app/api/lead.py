"""``crm.fcrm.doctype.crm_lead.crm_lead.*`` - the lead endpoint the frontend calls by
its doctype-module path: "Convert to Deal" on a lead and the list's bulk action
(``ConvertToDealModal.vue``, ``ListBulkActions.vue``).

The conversion itself has lived in :mod:`crm_app.conversion` since phase 3; nothing
exposed it at this name, so the button answered 404 (the second of the twenty paths in
``docs/http/14_unserved_paths.http``).
"""

from __future__ import annotations

from frappe_core import permissions, registry
from frappe_core.exceptions import DoesNotExistError
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.query import parse_json_param
from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist


@whitelist("crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal", methods=("POST",))
def convert_to_deal(lead: str, deal=None, existing_contact=None, existing_organization=None, **extra):
    """``crm_lead.py:494-516``. ``deal`` is the modal's deal form (a dict, or its JSON),
    ``existing_contact`` / ``existing_organization`` the names picked instead of
    creating new ones. Write permission on the lead, or "Not allowed to convert Lead to
    Deal"; a lead that does not exist is 404. Returns the new deal's name."""
    from crm_app import conversion

    instance = registry.get_model("CRM Lead")._default_manager.filter(pk=lead).first()
    if instance is None:
        raise DoesNotExistError(f"CRM Lead {lead} not found")
    if not permissions.check_object_permission(instance, "write", get_current_user()):
        raise FrappePermissionError("Not allowed to convert Lead to Deal")
    overrides = parse_json_param(deal, deal) if deal else None
    if not isinstance(overrides, dict):
        overrides = None
    created = conversion.convert_to_deal(
        instance,
        deal=overrides,
        existing_contact=existing_contact or None,
        existing_organization=existing_organization or None,
        ignore_permissions=True,  # checked above, with upstream's sentence
    )
    return created.pk
