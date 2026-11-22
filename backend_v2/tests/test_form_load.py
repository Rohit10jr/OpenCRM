"""`getdoctype` (specs/CONFIGURATION.md 4.5; temp A-35).

Ported from ``backend/tests/test_form_load.py`` (REBUILD_PLAN S14): `:292`, `:316`, and
the user_settings round trips `:366`, `:378`, `:384`, `:394`. The old cases on CRM Deal
and CRM Contacts are SALES' and CONTACTS'; their in-unit twins here run on FCRM Settings
and CRM Dropdown Item (the Home Actions grid). `frappe.desk.form.load.getdoctype` is
`GET /api/v1/meta/doctype/`; `frappe.model.utils.user_settings.save` is
`POST /api/v1/user-settings/`. Expected answers are unchanged.
"""

import json

import pytest

from configuration import field_meta

pytestmark = pytest.mark.django_db

GETDOCTYPE = "/api/v1/meta/doctype/"
SETTINGS = "/api/v1/user-settings/"


def load(client, doctype: str, **params):
    return client.get(GETDOCTYPE, {"doctype": doctype, **params})


def save_settings(client, doctype: str, settings: dict):
    return client.post(
        SETTINGS, {"doctype": doctype, "user_settings": json.dumps(settings)}, format="json"
    )


def names(doc: dict) -> list[str]:
    return [f["fieldname"] for f in doc["fields"]]


# --- ported ------------------------------------------------------------------------------


def test_unknown_doctype_is_404(auth_api):
    response = load(auth_api, "No Such Doctype")
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"
    assert response.json()["message"] == "DocType No Such Doctype not found"


# --- twins of the old cases on CRM Deal and CRM Contacts (A-36 finding 4) ----------------


def generated() -> dict:
    """The committed file read from disk, not through field_meta, as the old tests do."""
    return json.loads(field_meta._DATA_FILE.read_text(encoding="utf-8"))


def field_of(doc: dict, fieldname: str) -> dict:
    return next(f for f in doc["fields"] if f["fieldname"] == fieldname)


def test_doctype_properties_come_through(auth_api):
    """Twin of `:99` on FCRM Settings: the values, defaults for what the file omits."""
    meta = generated()["FCRM Settings"]
    doc = load(auth_api, "FCRM Settings").json()["docs"][0]
    assert (doc["name"], doc["istable"], doc["issingle"]) == ("FCRM Settings", 0, 1)
    for key in ("autoname", "title_field"):
        assert doc[key] == meta.get(key), key
    assert doc["sort_field"] == meta.get("sort_field", "modified")
    assert doc["sort_order"] == meta.get("sort_order", "DESC")
    assert doc["is_submittable"] == 0
    assert doc["editable_grid"] == meta.get("editable_grid", 0)
    assert doc["translated_doctype"] == meta.get("translated_doctype", 0)


def test_a_hidden_field_is_marked_hidden(api_as, make_user):
    """Twin of `:148` on FCRM Settings' `persona_captured`."""
    assert next(f for f in generated()["FCRM Settings"]["fields"] if f["fieldname"] == "persona_captured").get("hidden") == 1
    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    doc = load(api_as(manager), "FCRM Settings").json()["docs"][0]
    assert field_of(doc, "persona_captured")["hidden"] == 1


def test_a_field_descriptor_carries_what_the_form_controls_read(auth_api):
    """Twin of `:165` on FCRM Settings' `currency`: a Link with its target; `reqd` absent."""
    currency = field_of(load(auth_api, "FCRM Settings").json()["docs"][0], "currency")
    assert (currency["fieldtype"], currency["options"]) == ("Link", "Currency")
    assert currency["label"] == next(
        f for f in generated()["FCRM Settings"]["fields"] if f["fieldname"] == "currency"
    )["label"]
    assert "reqd" not in currency


def test_layout_breaks_are_in_the_field_list(auth_api):
    """Twin of `:181` on FCRM Settings."""
    fieldtypes = {f["fieldtype"] for f in load(auth_api, "FCRM Settings").json()["docs"][0]["fields"]}
    assert fieldtypes & {"Tab Break", "Section Break", "Column Break"}


def test_in_list_view_marks_the_grid_columns(auth_api):
    """Twin of `:189` on CRM Dropdown Item, the Home Actions grid's rows."""
    meta = generated()["CRM Dropdown Item"]["fields"]
    expected = {f["fieldname"] for f in meta if f.get("in_list_view")}
    assert expected, "CRM Dropdown Item must declare grid columns for this to mean anything"
    docs = load(auth_api, "FCRM Settings").json()["docs"]
    items = next(doc for doc in docs if doc["name"] == "CRM Dropdown Item")
    assert {f["fieldname"] for f in items["fields"] if f.get("in_list_view")} == expected
    unmarked = next(f["fieldname"] for f in meta if f.get("fieldname") and not f.get("in_list_view"))
    assert "in_list_view" not in field_of(items, unmarked)


def test_depends_on_and_the_other_new_field_keys_survive_generation(auth_api):
    """Twin of `:224` on CRM Dropdown Item's `route`."""
    expected = next(f for f in generated()["CRM Dropdown Item"]["fields"] if f["fieldname"] == "route")
    route = field_of(load(auth_api, "CRM Dropdown Item").json()["docs"][0], "route")
    for key in ("depends_on", "mandatory_depends_on"):
        assert route.get(key) == expected.get(key), key
    assert expected.get("depends_on") or expected.get("mandatory_depends_on")


def test_with_parent_on_a_normal_doctype_is_a_no_op(auth_api):
    """Twin of `:271` on FCRM Settings."""
    body = load(auth_api, "FCRM Settings", with_parent=1).json()
    assert "parent_dt" not in body
    assert body["docs"][0]["name"] == "FCRM Settings"


def test_getdoctype_needs_a_session(api):
    assert load(api, "FCRM Settings").status_code == 401


def test_saved_settings_come_back_through_getdoctype(auth_api):
    save_settings(auth_api, "FCRM Settings", {"GridView": {"CRM Dropdown Item": ["label"]}})
    body = load(auth_api, "FCRM Settings").json()
    assert json.loads(body["user_settings"]) == {"GridView": {"CRM Dropdown Item": ["label"]}}


def test_settings_are_per_doctype(auth_api):
    save_settings(auth_api, "FCRM Settings", {"List": {"page_length": 40}})
    assert load(auth_api, "System Settings").json()["user_settings"] == "{}"


def test_with_parent_reads_the_parents_settings(auth_api):
    save_settings(auth_api, "FCRM Settings", {"GridView": {"CRM Dropdown Item": ["label"]}})
    body = load(auth_api, "CRM Dropdown Item", with_parent=1).json()
    assert json.loads(body["user_settings"]) == {"GridView": {"CRM Dropdown Item": ["label"]}}


def test_each_user_sees_only_their_own_settings(auth_api, api_as, bob):
    save_settings(auth_api, "FCRM Settings", {"List": {"page_length": 40}})
    bob_api = api_as(bob)
    save_settings(bob_api, "FCRM Settings", {"List": {"page_length": 5}})
    assert json.loads(load(auth_api, "FCRM Settings").json()["user_settings"]) == {
        "List": {"page_length": 40}
    }
    assert json.loads(load(bob_api, "FCRM Settings").json()["user_settings"]) == {
        "List": {"page_length": 5}
    }


# --- in-unit twins: the Home Actions grid ------------------------------------------------


def test_docs_and_user_settings_sit_beside_a_null_message(auth_api):
    body = load(auth_api, "FCRM Settings").json()
    assert body["message"] is None
    assert body["user_settings"] == "{}"
    assert "parent_dt" not in body


def test_the_bundle_is_the_doctype_then_its_child_tables(auth_api):
    docs = load(auth_api, "FCRM Settings").json()["docs"]
    assert [d["name"] for d in docs] == ["FCRM Settings", "CRM Dropdown Item"]
    assert (docs[0]["issingle"], docs[1]["istable"]) == (1, 1)


def test_with_parent_on_a_child_answers_with_the_parents_bundle(auth_api):
    body = load(auth_api, "CRM Dropdown Item", with_parent=1).json()
    assert body["parent_dt"] == "FCRM Settings"
    assert [d["name"] for d in body["docs"]] == ["FCRM Settings", "CRM Dropdown Item"]


def test_without_with_parent_a_child_answers_for_itself(auth_api):
    body = load(auth_api, "CRM Dropdown Item").json()
    assert [d["name"] for d in body["docs"]] == ["CRM Dropdown Item"]
    assert "parent_dt" not in body


def test_every_field_carries_its_1_based_idx_and_the_file_is_untouched(auth_api):
    doc = load(auth_api, "CRM Dropdown Item").json()["docs"][0]
    assert [f["idx"] for f in doc["fields"]] == list(range(1, len(doc["fields"]) + 1))
    assert all("idx" not in f for f in field_meta.get_fields("CRM Dropdown Item"))


def test_the_nine_doctype_properties_are_always_present(auth_api):
    doc = load(auth_api, "CRM Dropdown Item").json()["docs"][0]
    for key in ("istable", "issingle", "autoname", "title_field", "editable_grid",
                "translated_doctype", "sort_field", "sort_order", "is_submittable"):
        assert key in doc, key


def test_the_defaults_page_loads_the_row_and_its_options(api_as, administrator):
    """``test_system_settings.py:51``'s getdoctype half, which waited for this milestone."""
    response = load(api_as(administrator), "System Settings")
    assert response.status_code == 200, response.content[:300]
    fields = {f["fieldname"]: f for f in response.json()["docs"][0]["fields"]}
    assert fields["date_format"]["fieldtype"] == "Select"
    assert fields["date_format"]["options"].split("\n") == [
        "yyyy-mm-dd", "dd-mm-yyyy", "dd/mm/yyyy", "dd.mm.yyyy", "mm/dd/yyyy", "mm-dd-yyyy",
    ]
    assert fields["time_format"]["options"].split("\n") == ["HH:mm:ss", "HH:mm"]
    assert fields["float_precision"]["options"].split("\n")[:2] == ["", "2"]
    assert fields["currency_precision"]["options"].split("\n")[:2] == ["", "0"]
    assert fields["number_format"]["options"].split("\n")[0] == "#,###.##"
    assert (fields["currency"]["fieldtype"], fields["currency"]["options"]) == ("Link", "Currency")


# --- the exceptions (PE-14, PE-15, PE-16) -------------------------------------------------


def test_pe14_a_withheld_doctype_is_not_found(auth_api):
    response = load(auth_api, "Version")
    assert response.status_code == 404
    assert response.json()["message"] == "DocType Version not found"


def test_a_doctype_in_the_file_with_no_model_is_not_found(auth_api):
    assert field_meta.has_meta("CRM Deal")
    assert load(auth_api, "CRM Deal").status_code == 404


def test_pe16_a_restricted_field_is_left_out_for_a_non_manager(auth_api, api_as, make_user):
    assert "access_key" not in names(load(auth_api, "FCRM Settings").json()["docs"][0])
    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    manager_doc = load(api_as(manager), "FCRM Settings").json()["docs"][0]
    assert "access_key" in names(manager_doc)


def test_pe16_a_sensitive_field_is_left_out_for_everyone(api_as, administrator):
    doc = load(api_as(administrator), "Email Account").json()["docs"][0]
    assert not {"password", "api_secret"} & set(names(doc))


def test_pe16_the_remaining_fields_keep_their_idx(auth_api, api_as, make_user):
    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    full = {f["fieldname"]: f["idx"] for f in load(api_as(manager), "FCRM Settings").json()["docs"][0]["fields"]}
    narrowed = {f["fieldname"]: f["idx"] for f in load(auth_api, "FCRM Settings").json()["docs"][0]["fields"]}
    assert all(full[name] == idx for name, idx in narrowed.items())
    assert set(full) - set(narrowed) == {"access_key"}


def test_a_platform_doctype_answers_with_model_derived_fields(auth_api):
    """Ported from ``backend/tests/test_form_load.py:300-313`` with CONTACTS milestone 3
    (specs/CONTACTS.md §7a): Contact ships no DocType JSON, so its fields come from the
    model, and its two Table rows bring Contact Email and Contact Phone into the bundle."""
    body = load(auth_api, "Contact").json()

    assert [doc["name"] for doc in body["docs"]] == ["Contact", "Contact Email", "Contact Phone"]
    fields = body["docs"][0]["fields"]
    assert fields, "a routed platform doctype must still answer with its fields"
    assert {f["fieldname"] for f in fields} >= {"first_name", "email_id"}
    assert all("fieldtype" in f and "idx" in f for f in fields)
    assert body["docs"][0]["istable"] == 0
    assert body["docs"][0]["sort_field"] == "modified"
