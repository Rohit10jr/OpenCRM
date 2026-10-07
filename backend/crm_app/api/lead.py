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


def _deal_overrides(deal: dict) -> dict | None:
    """The modal's deal form, as ``new_deal.update(deal)`` takes it (``crm_lead.py:375-376``).

    ``ConvertToDealModal.vue`` sends ``deal.doc`` whole, and a new document starts life as
    ``{__newDocument: true, doctype}`` (``data/document.js``), so those two keys arrive on
    every conversion from a lead's page, before any field the user filled in. Upstream's
    ``update`` sets every key on the document and ``insert`` saves the ones that are
    fields. Passed straight to the model here they raised ``TypeError`` and the button
    answered 500 (FINDINGS.md 73).

    The keys that are deal fields go through the deal's serializer, as they do in the
    "Create Deal" door (``crm_app/api/deal.py``): the same read-only rules as
    ``frappe.client.insert``, the same validation, and a Link arrives as the name the
    frontend sent. What comes back is keyed the way ``conversion.create_deal`` builds its
    own payload, a Link under ``<field>_id``.
    """
    entry = registry.get_entry("CRM Deal")
    concrete = {f.name: f for f in entry.model._meta.get_fields() if getattr(f, "concrete", False)}
    data = {key: value for key, value in deal.items() if key in concrete}
    if not data:
        return None
    serializer = entry.get_serializer_class()(data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    overrides: dict = {}
    for name, value in serializer.validated_data.items():
        field = concrete.get(name)
        if field is None:
            continue
        if field.is_relation:
            overrides[f"{name}_id"] = getattr(value, "pk", value)
        else:
            overrides[name] = value
    return overrides or None


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
    overrides = _deal_overrides(overrides) if isinstance(overrides, dict) else None
    created = conversion.convert_to_deal(
        instance,
        deal=overrides,
        existing_contact=existing_contact or None,
        existing_organization=existing_organization or None,
        ignore_permissions=True,  # checked above, with upstream's sentence
    )
    return created.pk
