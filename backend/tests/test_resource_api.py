"""Acceptance criteria 1 and 9 - the generic ``/api/resource/`` endpoint.

PHASE_0_FOUNDATION.md section 6a.

Criterion 1 names ``CRM Lead``. Phase 0 is forbidden from building any CRM model
(spec section 9), so the *shape* of that request - a JSON-encoded ``filters`` list of
3-tuples plus a JSON-encoded ``fields`` list, against a doctype whose name contains a
space - is exercised against the phase-0 test doctype instead. Re-run it against the
real ``CRM Lead`` once phase 1 lands.
"""

import json
from urllib.parse import quote

import pytest

from frappe_core import registry
from frappe_core.session import session_user
from tests_support.models import ChildDoc, FieldDoc, Widget

pytestmark = pytest.mark.django_db

LIST_URL = "/api/resource/" + quote("Phase Zero Widget")


@pytest.fixture
def widgets(alice, bob):
    with session_user(alice.name):
        Widget.objects.create(widget_name="Alpha", status="Open", widget_owner=alice)
        Widget.objects.create(widget_name="Beta", status="Open", widget_owner=bob)
        Widget.objects.create(widget_name="Gamma", status="Closed", widget_owner=alice)
    return Widget.objects.all()


# --- criterion 1 --------------------------------------------------------------


def test_list_with_filters_and_fields(auth_api, widgets):
    """The exact request shape from acceptance criterion 1."""
    response = auth_api.get(
        LIST_URL,
        {
            "filters": json.dumps([["status", "=", "Open"]]),
            "fields": json.dumps(["name", "widget_name"]),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data"}, "list responses must be enveloped as {'data': ...}"
    assert isinstance(body["data"], list)
    assert sorted(r["widget_name"] for r in body["data"]) == ["Alpha", "Beta"]
    assert set(body["data"][0]) == {"name", "widget_name"}, "fields must be honoured"


def test_list_with_doctype_qualified_filters(auth_api, widgets):
    response = auth_api.get(
        LIST_URL,
        {
            "filters": json.dumps([["Phase Zero Widget", "status", "=", "Closed"]]),
            "fields": json.dumps(["widget_name"]),
        },
    )
    assert response.status_code == 200
    assert [r["widget_name"] for r in response.json()["data"]] == ["Gamma"]


def test_list_with_dict_filters(auth_api, widgets):
    response = auth_api.get(
        LIST_URL,
        {"filters": json.dumps({"status": "Closed"}), "fields": json.dumps(["widget_name"])},
    )
    assert [r["widget_name"] for r in response.json()["data"]] == ["Gamma"]


def test_fields_star_returns_everything(auth_api, widgets):
    response = auth_api.get(LIST_URL, {"fields": json.dumps(["*"])})
    row = response.json()["data"][0]
    for key in ("name", "owner", "modified", "docstatus", "_assign", "widget_name"):
        assert key in row


def test_unknown_field_is_rejected(auth_api, widgets):
    response = auth_api.get(LIST_URL, {"fields": json.dumps(["nonexistent"])})
    assert response.status_code == 417
    assert response.json()["exc_type"] == "ValidationError"


def test_order_by_desc(auth_api, widgets):
    response = auth_api.get(
        LIST_URL, {"fields": json.dumps(["widget_name"]), "order_by": "widget_name desc"}
    )
    assert [r["widget_name"] for r in response.json()["data"]] == ["Gamma", "Beta", "Alpha"]


def test_order_by_asc_is_the_default_direction(auth_api, widgets):
    response = auth_api.get(
        LIST_URL, {"fields": json.dumps(["widget_name"]), "order_by": "widget_name"}
    )
    assert [r["widget_name"] for r in response.json()["data"]] == ["Alpha", "Beta", "Gamma"]


def test_pagination(auth_api, widgets):
    response = auth_api.get(
        LIST_URL,
        {
            "fields": json.dumps(["widget_name"]),
            "order_by": "widget_name asc",
            "limit_start": "1",
            "limit_page_length": "1",
        },
    )
    assert [r["widget_name"] for r in response.json()["data"]] == ["Beta"]


def test_or_filters(auth_api, widgets):
    response = auth_api.get(
        LIST_URL,
        {
            "or_filters": json.dumps({"status": "Closed", "widget_name": "Alpha"}),
            "fields": json.dumps(["widget_name"]),
        },
    )
    assert sorted(r["widget_name"] for r in response.json()["data"]) == ["Alpha", "Gamma"]


# --- read / create / update / delete ------------------------------------------


def test_read_single_document(auth_api, widgets):
    widget = widgets.first()
    response = auth_api.get(f"{LIST_URL}/{quote(widget.name)}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data"}
    assert body["data"]["name"] == widget.name


def test_read_missing_document_is_a_frappe_404(auth_api):
    response = auth_api.get(f"{LIST_URL}/PZW-9999-99999")
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_create_returns_201_and_the_generated_name(auth_api, alice):
    response = auth_api.post(
        LIST_URL, {"widget_name": "Created", "status": "Open"}, format="json"
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["widget_name"] == "Created"
    assert data["name"].startswith("PZW-")


def test_create_stamps_owner_from_the_authenticated_user(auth_api, alice):
    auth_api.post(LIST_URL, {"widget_name": "Owned"}, format="json")
    assert Widget.objects.get(widget_name="Owned").owner_id == alice.name


def test_update(auth_api, widgets):
    widget = widgets.first()
    response = auth_api.put(
        f"{LIST_URL}/{quote(widget.name)}", {"status": "Won"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "Won"
    widget.refresh_from_db()
    assert widget.status == "Won"


def test_update_stamps_modified_by(auth_api, widgets, alice):
    widget = widgets.first()
    auth_api.put(f"{LIST_URL}/{quote(widget.name)}", {"status": "Won"}, format="json")
    widget.refresh_from_db()
    assert widget.modified_by_id == alice.name


def test_delete_returns_a_null_data_envelope(auth_api, widgets):
    widget = widgets.first()
    response = auth_api.delete(f"{LIST_URL}/{quote(widget.name)}")
    assert response.status_code == 200
    assert response.json() == {"data": None}
    assert not Widget.objects.filter(pk=widget.name).exists()


def test_owner_cannot_be_set_by_the_client(auth_api, alice, bob):
    """``owner`` is stamped, never accepted from the wire."""
    auth_api.post(LIST_URL, {"widget_name": "Spoof", "owner": bob.name}, format="json")
    assert Widget.objects.get(widget_name="Spoof").owner_id == alice.name


# --- auth ---------------------------------------------------------------------


def test_prompt_doctype_accepts_a_client_supplied_name(auth_api):
    """``prompt`` autoname - the client names the document (spec section 2).

    ``name`` is ``editable=False`` on the model, so DRF derives it as read-only and
    the name was being dropped. Only ``crm_form_script`` uses this strategy, which is
    why it is easy to miss until phase 3 tries to create one.
    """
    response = auth_api.post(
        "/api/resource/" + quote("Phase Zero Prompt"),
        {"name": "my-form-script", "label": "x"},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["data"]["name"] == "my-form-script"


def test_prompt_doctype_rejects_a_missing_name(auth_api):
    response = auth_api.post(
        "/api/resource/" + quote("Phase Zero Prompt"), {"label": "x"}, format="json"
    )
    assert response.status_code == 417
    assert any("name" in m for m in response.json()["messages"])


def test_creating_a_duplicate_name_does_not_overwrite(auth_api):
    """The dangerous half of the same bug.

    Without ``force_insert``, Django runs UPDATE-then-INSERT for a string PK, so a
    second POST with an existing name silently overwrote the first document instead of
    failing.
    """
    url = "/api/resource/" + quote("Phase Zero Prompt")
    auth_api.post(url, {"name": "dupe", "label": "original"}, format="json")
    response = auth_api.post(url, {"name": "dupe", "label": "impostor"}, format="json")

    assert response.status_code == 409
    assert response.json()["exc_type"] == "DuplicateEntryError"

    from tests_support.models import PromptDoc

    assert PromptDoc.objects.get(pk="dupe").label == "original"


def test_duplicate_field_named_doctype_does_not_overwrite(auth_api):
    """Same guarantee for the 14 ``field:`` doctypes, where the PK is user data."""
    url = "/api/resource/" + quote("Phase Zero Field")
    auth_api.post(url, {"organization_name": "Acme Corp"}, format="json")
    response = auth_api.post(url, {"organization_name": "Acme Corp"}, format="json")
    assert response.status_code == 409
    assert FieldDoc.objects.filter(pk="Acme Corp").count() == 1


def test_unauthenticated_list_is_rejected(api, widgets):
    response = api.get(LIST_URL)
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"


# --- criterion 9: a throwaway model is routable -------------------------------


def test_a_registered_model_is_routable_with_no_view_code(auth_api, alice):
    """``Widget`` is registered in three lines and needs no view, URL or serializer."""
    with session_user(alice.name):
        FieldDoc.objects.create(organization_name="Acme Corp")
    response = auth_api.get("/api/resource/" + quote("Phase Zero Field"))
    assert response.status_code == 200
    assert [r["name"] for r in response.json()["data"]] == ["Acme Corp"]


def test_registry_exposes_the_model_for_a_doctype():
    assert registry.get_model("Phase Zero Widget") is Widget


def test_registry_generates_a_serializer_on_demand():
    serializer = registry.get_entry("Phase Zero Widget").get_serializer_class()
    assert "widget_name" in serializer().get_fields()


def test_registry_caches_the_generated_serializer():
    entry = registry.get_entry("Phase Zero Widget")
    assert entry.get_serializer_class() is entry.get_serializer_class()


def test_unknown_doctype_is_a_frappe_404(auth_api):
    response = auth_api.get("/api/resource/" + quote("No Such DocType"))
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_child_tables_have_no_standalone_route(auth_api, alice):
    """PHASE_1_MODELS.md section 3 - reached through the parent only."""
    with session_user(alice.name):
        ChildDoc.objects.create(parenttype="Phase Zero Widget")
    response = auth_api.get("/api/resource/" + quote("Phase Zero Child"))
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_child_tables_are_excluded_from_routable_doctypes():
    assert "Phase Zero Child" not in registry.routable_doctypes()
    assert "Phase Zero Child" in registry.all_doctypes()


# --- injection surface (PHASE_2_PERMISSIONS.md criterion 7, enforced in phase 0) --


def test_order_by_cannot_traverse_a_relation(auth_api, widgets):
    response = auth_api.get(LIST_URL, {"order_by": "widget_owner__password desc"})
    assert response.status_code == 417
    assert "unknown field" in response.json()["message"].lower()


def test_fields_cannot_traverse_a_relation(auth_api, widgets):
    response = auth_api.get(LIST_URL, {"fields": json.dumps(["widget_owner__password"])})
    assert response.status_code == 417


def test_group_by_cannot_traverse_a_relation(auth_api, widgets):
    response = auth_api.get(LIST_URL, {"group_by": "widget_owner__password"})
    assert response.status_code == 417


def test_order_by_rejects_a_bogus_direction(auth_api, widgets):
    response = auth_api.get(LIST_URL, {"order_by": "widget_name sideways"})
    assert response.status_code == 417


def test_order_by_accepts_a_table_qualified_column(auth_api, widgets):
    response = auth_api.get(
        LIST_URL, {"fields": json.dumps(["widget_name"]), "order_by": "`tabPhase Zero Widget`.widget_name asc"}
    )
    assert response.status_code == 200
    assert [r["widget_name"] for r in response.json()["data"]] == ["Alpha", "Beta", "Gamma"]
