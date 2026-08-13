"""Acceptance criterion 8 - the phase-2 and phase-4 hooks are provably wired.

PHASE_0_FOUNDATION.md section 8. "Provably" is the operative word: it is not enough
that the functions exist. These tests register a hook, drive a *real request*, and
assert the hook was consulted and its return value honoured - so phase 2 and phase 4
can plug in without editing phase-0 code.
"""

import json
from urllib.parse import quote

import pytest
from django.db.models import Q

from frappe_core import metadata, permissions, registry
from frappe_core.api.doc import get_data
from frappe_core.session import session_user
from tests_support.models import Widget

pytestmark = pytest.mark.django_db

LIST_URL = "/api/resource/" + quote("Phase Zero Widget")


@pytest.fixture
def widgets(alice, bob):
    with session_user(alice.name):
        Widget.objects.create(widget_name="Alpha", status="Open", widget_owner=alice)
        Widget.objects.create(widget_name="Beta", status="Open", widget_owner=bob)
        Widget.objects.create(widget_name="Gamma", status="Closed", widget_owner=alice)
    return Widget.objects.all()


@pytest.fixture
def clean_hooks():
    """Restore the entry's hooks after each test - the registry is process-global."""
    entry = registry.get_entry("Phase Zero Widget")
    saved = (
        entry.permission_query_conditions,
        entry.has_permission,
        entry.list_columns_provider,
        entry.filterable_fields_provider,
    )
    yield entry
    (
        entry.permission_query_conditions,
        entry.has_permission,
        entry.list_columns_provider,
        entry.filterable_fields_provider,
    ) = saved


# --- default state: no hooks means no restriction -----------------------------


def test_permission_query_conditions_returns_none_by_default():
    assert permissions.get_permission_query_conditions("Phase Zero Widget") is None


def test_has_permission_returns_none_by_default(widgets):
    assert permissions.has_permission(widgets.first(), "read", "alice@example.com") is None


def test_none_means_allowed(widgets):
    assert permissions.check_object_permission(widgets.first(), "read") is True


def test_unregistered_doctype_is_unrestricted():
    assert permissions.get_permission_query_conditions("Not A DocType") is None


# --- phase 2: the list filter hook --------------------------------------------


def test_query_conditions_hook_is_called_on_a_real_list_request(auth_api, widgets, clean_hooks):
    calls = []

    def only_alphas(doctype, user):
        calls.append((doctype, user))
        return Q(widget_name="Alpha")

    registry.register_permission_hooks(
        "Phase Zero Widget", permission_query_conditions=only_alphas
    )

    response = auth_api.get(LIST_URL, {"fields": json.dumps(["widget_name"])})
    assert response.status_code == 200
    assert [r["widget_name"] for r in response.json()["data"]] == ["Alpha"]
    assert calls == [("Phase Zero Widget", "alice@example.com")]


def test_query_conditions_hook_also_narrows_get_data(alice, widgets, clean_hooks):
    """The rule must bind to both list paths, not just /api/resource/."""
    registry.register_permission_hooks(
        "Phase Zero Widget", permission_query_conditions=lambda dt, u: Q(widget_name="Gamma")
    )
    with session_user(alice.name):
        result = get_data(doctype="Phase Zero Widget", filters={}, order_by="modified desc")
    assert [r["widget_name"] for r in result["data"]] == ["Gamma"]


def test_query_conditions_hook_narrows_total_count(alice, widgets, clean_hooks):
    """A hidden row must not be countable either."""
    registry.register_permission_hooks(
        "Phase Zero Widget", permission_query_conditions=lambda dt, u: Q(widget_name="Gamma")
    )
    with session_user(alice.name):
        result = get_data(doctype="Phase Zero Widget", filters={}, order_by="modified desc")
    assert result["total_count"] == 1


def test_query_conditions_hook_cannot_be_bypassed_by_a_filter(auth_api, widgets, clean_hooks):
    registry.register_permission_hooks(
        "Phase Zero Widget", permission_query_conditions=lambda dt, u: Q(widget_name="Alpha")
    )
    response = auth_api.get(
        LIST_URL,
        {"filters": json.dumps({"widget_name": "Beta"}), "fields": json.dumps(["widget_name"])},
    )
    assert response.json()["data"] == []


def test_query_conditions_hook_cannot_be_bypassed_by_or_filters(auth_api, widgets, clean_hooks):
    registry.register_permission_hooks(
        "Phase Zero Widget", permission_query_conditions=lambda dt, u: Q(widget_name="Alpha")
    )
    response = auth_api.get(
        LIST_URL,
        {
            "or_filters": json.dumps({"widget_name": "Beta", "status": "Closed"}),
            "fields": json.dumps(["widget_name"]),
        },
    )
    assert response.json()["data"] == []


def test_query_conditions_hook_applies_to_the_detail_route(auth_api, widgets, clean_hooks):
    """A row filtered out of the list must not be readable directly."""
    hidden = Widget.objects.get(widget_name="Beta")
    registry.register_permission_hooks(
        "Phase Zero Widget",
        permission_query_conditions=lambda dt, u: Q(widget_name="Alpha"),
        has_permission=lambda doc, ptype, user: doc.widget_name == "Alpha",
    )
    response = auth_api.get(f"{LIST_URL}/{quote(hidden.name)}")
    assert response.status_code == 403
    assert response.json()["exc_type"] == "PermissionError"


# --- phase 2: the object hook -------------------------------------------------


def test_has_permission_hook_is_called_on_read(auth_api, widgets, clean_hooks):
    calls = []

    def deny(doc, ptype, user):
        calls.append(ptype)
        return False

    registry.register_permission_hooks("Phase Zero Widget", has_permission=deny)
    response = auth_api.get(f"{LIST_URL}/{quote(widgets.first().name)}")
    assert response.status_code == 403
    assert calls == ["read"]


def test_has_permission_hook_receives_the_write_ptype(auth_api, widgets, clean_hooks):
    calls = []
    registry.register_permission_hooks(
        "Phase Zero Widget",
        has_permission=lambda doc, ptype, user: calls.append(ptype) or True,
    )
    auth_api.put(f"{LIST_URL}/{quote(widgets.first().name)}", {"status": "Won"}, format="json")
    assert calls == ["write"]


def test_has_permission_hook_receives_the_delete_ptype(auth_api, widgets, clean_hooks):
    calls = []
    registry.register_permission_hooks(
        "Phase Zero Widget",
        has_permission=lambda doc, ptype, user: calls.append(ptype) or True,
    )
    auth_api.delete(f"{LIST_URL}/{quote(widgets.first().name)}")
    assert calls == ["delete"]


def test_has_permission_hook_receives_the_acting_user(auth_api, widgets, clean_hooks):
    seen = []
    registry.register_permission_hooks(
        "Phase Zero Widget",
        has_permission=lambda doc, ptype, user: seen.append(user) or True,
    )
    auth_api.get(f"{LIST_URL}/{quote(widgets.first().name)}")
    assert seen == ["alice@example.com"]


# --- phase 4: metadata hooks --------------------------------------------------


def test_get_list_columns_falls_back_to_the_controller_default():
    columns = metadata.get_list_columns("Phase Zero Widget")
    assert [c["key"] for c in columns] == ["widget_name", "status", "modified"]


def test_list_columns_provider_overrides_the_default(clean_hooks):
    registry.register_metadata_hooks(
        "Phase Zero Widget",
        list_columns_provider=lambda dt, user, view_type: {
            "columns": [{"label": "Only", "type": "Data", "key": "status"}],
            "rows": ["name", "status"],
        },
    )
    columns = metadata.get_list_columns("Phase Zero Widget")
    assert columns["columns"][0]["key"] == "status"


def test_get_data_consults_the_saved_view_provider(alice, widgets, clean_hooks):
    """This is the phase-4 seam in ``get_data`` step 3."""
    seen = []

    def provider(doctype, user, view_type):
        seen.append((doctype, user, view_type))
        return {
            "columns": [{"label": "Status", "type": "Data", "key": "status"}],
            "rows": ["name", "status"],
        }

    registry.register_metadata_hooks("Phase Zero Widget", list_columns_provider=provider)
    with session_user(alice.name):
        result = get_data(doctype="Phase Zero Widget", filters={}, order_by="modified desc")

    assert seen == [("Phase Zero Widget", alice.name, "list")]
    assert [c["key"] for c in result["columns"]] == ["status"]
    assert result["is_default"] is False


def test_saved_view_is_not_consulted_for_a_custom_view(alice, widgets, clean_hooks):
    """Upstream only reads View Settings when the client sent no columns/rows."""
    seen = []
    registry.register_metadata_hooks(
        "Phase Zero Widget",
        list_columns_provider=lambda dt, u, vt: seen.append(1) or None,
    )
    with session_user(alice.name):
        get_data(
            doctype="Phase Zero Widget",
            filters={},
            order_by="modified desc",
            columns=[{"label": "W", "type": "Data", "key": "widget_name"}],
            rows=["name"],
        )
    assert seen == []


def test_get_filterable_fields_honours_get_non_filterable_fields():
    """``Widget.get_non_filterable_fields()`` returns ``["notes"]``."""
    names = {f["fieldname"] for f in metadata.get_filterable_fields("Phase Zero Widget")}
    assert "widget_name" in names
    assert "notes" not in names


def test_filterable_fields_include_the_standard_set():
    names = {f["fieldname"] for f in metadata.get_filterable_fields("Phase Zero Widget")}
    assert {"name", "owner", "modified_by", "_assign", "creation", "modified"} <= names


def test_filterable_fields_provider_overrides_the_default(clean_hooks):
    registry.register_metadata_hooks(
        "Phase Zero Widget", filterable_fields_provider=lambda dt: [{"fieldname": "only"}]
    )
    assert metadata.get_filterable_fields("Phase Zero Widget") == [{"fieldname": "only"}]


def test_group_by_fields_exclude_free_text():
    """``crm/api/doc.py:get_group_by_fields`` uses a narrower allowlist than filters."""
    names = {f["fieldname"] for f in metadata.get_group_by_fields("Phase Zero Widget")}
    assert "status" in names
    assert "notes" not in names, "TextField is not group-by-able upstream"


# --- registry surface ---------------------------------------------------------


def test_registry_reports_the_doctype_on_the_model():
    assert Widget.get_doctype() == "Phase Zero Widget"


def test_registry_knows_child_tables():
    assert registry.get_entry("Phase Zero Child").is_child_table is True
    assert registry.get_entry("Phase Zero Widget").is_child_table is False


def test_registry_exposes_default_list_data():
    data = registry.get_entry("Phase Zero Widget").default_list_data()
    assert set(data) == {"columns", "rows"}


def test_registry_default_list_data_falls_back_when_the_model_defines_none():
    """Upstream's own fallback: Name + Last Modified."""
    entry = registry.get_entry("Phase Zero Hash")
    assert entry.has_default_list_data() is False
    assert [c["key"] for c in entry.default_list_data()["columns"]] == ["name", "modified"]


def test_registering_an_unknown_doctype_hook_raises():
    with pytest.raises(registry.DocTypeNotFound):
        registry.register_permission_hooks("Nope", has_permission=lambda *a: True)
