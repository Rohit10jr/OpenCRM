"""``crm.api.doc.get_fields``: docs/FINDINGS.md 52.

The bulk-edit dialog's field dropdown (``EditValueModal.vue``) and the settings page's
form (``SettingsPage.vue``) both build from it. Shapes follow ``crm/api/doc.py:639-651``
and the DocField rows ``frappe.get_meta(doctype).fields`` returns.
"""

import pytest

pytestmark = pytest.mark.django_db

PATH = "/api/method/crm.api.doc.get_fields"


def get_fields(client, **params):
    response = client.post(PATH, {"doctype": "CRM Task", **params}, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def dialog_options(fields):
    """``EditValueModal.vue:76-82``: what survives the dialog's own filter."""
    return [f["fieldname"] for f in fields if f["hidden"] == 0 and f["read_only"] == 0]


def test_the_bulk_edit_dropdown_has_the_tasks_fields(auth_api):
    fields = get_fields(auth_api)
    offered = dialog_options(fields)
    for fieldname in ("title", "status", "priority", "due_date", "assigned_to"):
        assert fieldname in offered, fieldname


def test_every_row_carries_the_flags_the_dialog_reads(auth_api):
    for field in get_fields(auth_api):
        assert field["hidden"] in (0, 1) and field["read_only"] in (0, 1), field
        for key in ("reqd", "options", "description", "default", "label", "fieldtype"):
            assert key in field, (key, field)


def test_labels_order_and_options_are_the_doctypes_not_the_models(auth_api):
    fields = {f["fieldname"]: f for f in get_fields(auth_api)}
    assert fields["title"]["label"] == "Title" and fields["title"]["reqd"] == 1
    assert fields["priority"]["fieldtype"] == "Select"
    assert fields["priority"]["options"] == "Low\nMedium\nHigh"
    assert fields["assigned_to"]["fieldtype"] == "Link"
    assert fields["assigned_to"]["options"] == "User"
    names = [f["fieldname"] for f in get_fields(auth_api)]
    assert names.index("title") < names.index("priority") < names.index("due_date")


def test_layout_breaks_are_left_out_unless_every_type_is_asked_for(auth_api):
    """``no_value_fields``: a Column Break has no value to edit. The settings page asks
    for all of them, because it lays its form out from the breaks."""
    default = {f["fieldtype"] for f in get_fields(auth_api)}
    assert not default & {"Section Break", "Column Break", "Tab Break"}

    everything = {f["fieldtype"] for f in get_fields(auth_api, allow_all_fieldtypes=True)}
    assert "Column Break" in everything


def test_an_unknown_doctype_is_a_404(auth_api):
    response = auth_api.post(PATH, {"doctype": "Nonsense"}, format="json")
    assert response.status_code == 404
