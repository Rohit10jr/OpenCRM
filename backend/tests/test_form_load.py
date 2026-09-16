"""``frappe.desk.form.load.getdoctype`` and ``frappe.model.utils.user_settings.*``.

The two endpoints ``frontend/src/stores/meta.js`` is built on: one call fetches a
doctype's meta bundle and the caller's saved UI state for it, and ``save`` writes that
state back.

The expectations about *which* metas come back, and in which order, are computed from
``crm_app/data/doctype_meta.json`` rather than written out by hand - the file is
generated from the CRM DocType JSON and a hard-coded list here would be a second,
silently rotting copy of it. What the tests pin is the **rule** (the doctype first, then
one meta per table field, in field order), not today's answer to it.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from frappe_core import field_meta

pytestmark = pytest.mark.django_db

GETDOCTYPE = "/api/method/frappe.desk.form.load.getdoctype"
SAVE = "/api/method/frappe.model.utils.user_settings.save"
GET_SETTINGS = "/api/method/frappe.model.utils.user_settings.get"

DATA_FILE = (
    pathlib.Path(__file__).resolve().parent.parent / "crm_app" / "data" / "doctype_meta.json"
)


def generated() -> dict:
    """The committed metadata, read from disk rather than through ``field_meta``.

    Reading the file directly is the point: a test that asked ``field_meta`` for the
    expected value and then asked the endpoint for the actual one would pass even if
    both were wrong together.
    """
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def expected_bundle(doctype: str, meta: dict) -> list[str]:
    """The doctype, then one child per table field, in field order - upstream's
    ``get_meta_bundle`` does not deduplicate, so neither does this."""
    names = [doctype]
    for field in meta[doctype]["fields"]:
        if field["fieldtype"] in ("Table", "Table MultiSelect") and field.get("options"):
            names.append(field["options"])
    return names


def load(client, doctype: str, **params):
    return client.post(GETDOCTYPE, {"doctype": doctype, **params}, format="json")


def field_of(doc: dict, fieldname: str) -> dict:
    return next(f for f in doc["fields"] if f["fieldname"] == fieldname)


# ---------------------------------------------------------------------------
# The meta bundle
# ---------------------------------------------------------------------------


def test_bundle_is_the_doctype_then_its_child_tables_in_field_order(auth_api):
    """``load.py:get_meta_bundle`` - ``[meta] + [meta(df.options) for table fields]``."""
    meta = generated()
    expected = expected_bundle("CRM Deal", meta)
    # Guard the guard: CRM Deal must actually embed child tables, or this proves nothing.
    assert len(expected) > 1

    response = load(auth_api, "CRM Deal")

    assert response.status_code == 200
    assert [doc["name"] for doc in response.json()["docs"]] == expected


def test_docs_and_user_settings_sit_beside_a_null_message(auth_api):
    """The response *shape* is load-bearing.

    Upstream writes ``docs`` and ``user_settings`` into ``frappe.response`` rather than
    returning them, and frappe-ui hands the caller the whole body when ``docs`` is
    present (``frappeRequest.ts:92``). A payload nested under ``message`` would leave
    ``stores/meta.js`` reading ``undefined.docs``.
    """
    body = load(auth_api, "CRM Deal").json()

    # Exactly these three: parent_dt appears only when with_parent resolved a parent.
    assert set(body) == {"message", "docs", "user_settings"}
    assert body["message"] is None
    assert body["docs"], "docs must never be empty on success - frappe-ui keys off it"
    assert body["user_settings"] == "{}"
    # A JSON *string*, not an object: stores/meta.js calls JSON.parse on it.
    assert isinstance(body["user_settings"], str)


def test_doctype_properties_come_through(auth_api):
    """The DocType row's own properties, defaults filled in for what the JSON omits."""
    meta = generated()
    deal = load(auth_api, "CRM Deal").json()["docs"][0]

    assert deal["name"] == "CRM Deal"
    assert deal["istable"] == 0
    assert deal["issingle"] == 0
    assert deal["autoname"] == meta["CRM Deal"]["autoname"]
    assert deal["title_field"] == meta["CRM Deal"]["title_field"]
    assert deal["sort_field"] == meta["CRM Deal"]["sort_field"]
    assert deal["sort_order"] == meta["CRM Deal"]["sort_order"]
    assert deal["is_submittable"] == 0
    # Not declared in crm_deal.json, so the generator drops it and the endpoint
    # supplies the DocType default (doctype.json declares no default for the Check).
    assert "editable_grid" not in meta["CRM Deal"]
    assert deal["editable_grid"] == 0
    assert deal["translated_doctype"] == 0


def test_a_child_tables_editable_grid_survives_the_round_trip(auth_api):
    """``Controls/Grid.vue`` reads ``gridSettings.editable_grid`` off the child's meta."""
    meta = generated()
    assert meta["CRM Contacts"]["editable_grid"] == 1

    docs = load(auth_api, "CRM Deal").json()["docs"]
    contacts = next(doc for doc in docs if doc["name"] == "CRM Contacts")

    assert contacts["editable_grid"] == 1
    assert contacts["istable"] == 1


def test_a_translated_doctype_says_so(auth_api):
    """``stores/meta.js:isTranslatable`` reads ``translated_doctype`` off the meta; the
    status doctypes declare it, so their values are shown through ``__()``."""
    meta = generated()
    translated = sorted(dt for dt, m in meta.items() if m.get("translated_doctype") == 1)
    assert translated, "some CRM doctype must declare translated_doctype for this to mean anything"

    doc = load(auth_api, translated[0]).json()["docs"][0]

    assert doc["translated_doctype"] == 1


# ---------------------------------------------------------------------------
# Field descriptors
# ---------------------------------------------------------------------------


def test_a_hidden_field_is_marked_hidden(auth_api):
    """``getFields`` drops ``f.hidden`` fields; the flag has to come through for that."""
    meta = generated()
    hidden = [
        (dt, f["fieldname"])
        for dt, m in meta.items()
        for f in m["fields"]
        if f.get("hidden") == 1 and not m.get("istable")
    ]
    assert hidden, "some CRM field must be hidden for this to mean anything"
    doctype, fieldname = hidden[0]

    doc = load(auth_api, doctype).json()["docs"][0]

    assert field_of(doc, fieldname)["hidden"] == 1


def test_a_field_descriptor_carries_what_the_form_controls_read(auth_api):
    deal = load(auth_api, "CRM Deal").json()["docs"][0]
    organization = field_of(deal, "organization")

    assert organization["fieldtype"] == "Link"
    assert organization["label"] == "Organization"
    # A Link's target - Field.vue turns it into the control's doctype.
    assert organization["options"] == "CRM Organization"

    # `reqd` on a mandatory field. crm_deal.json marks exactly one.
    assert field_of(deal, "status")["reqd"] == 1
    # Absent, not 0, on the rest: the generator drops zeros and `!f.reqd` is the test
    # every consumer makes.
    assert "reqd" not in organization


def test_layout_breaks_are_in_the_field_list(auth_api):
    """Upstream sends every DocField row, breaks included - ``FieldLayout`` needs them."""
    deal = load(auth_api, "CRM Deal").json()["docs"][0]
    fieldtypes = {f["fieldtype"] for f in deal["fields"]}

    assert "Section Break" in fieldtypes or "Column Break" in fieldtypes


def test_in_list_view_marks_the_grid_columns(auth_api):
    """``Grid.vue`` falls back to ``gridFields.filter(f => f.in_list_view)``."""
    meta = generated()
    expected = {f["fieldname"] for f in meta["CRM Contacts"]["fields"] if f.get("in_list_view")}
    assert expected, "CRM Contacts must declare grid columns for this to mean anything"

    docs = load(auth_api, "CRM Deal").json()["docs"]
    contacts = next(doc for doc in docs if doc["name"] == "CRM Contacts")

    assert {f["fieldname"] for f in contacts["fields"] if f.get("in_list_view")} == expected
    # and the ones the JSON does not mark stay unmarked
    assert "phone" not in expected
    assert "in_list_view" not in field_of(contacts, "phone")


def test_every_field_carries_its_1_based_idx(auth_api):
    """A DocField row has an ``idx``; ours is derived at response time."""
    deal = load(auth_api, "CRM Deal").json()["docs"][0]

    assert [f["idx"] for f in deal["fields"]] == list(range(1, len(deal["fields"]) + 1))


def test_idx_does_not_leak_into_the_cached_metadata(auth_api):
    """The response copies each descriptor; the parsed-JSON memo must stay clean.

    ``field_meta._raw`` is an ``lru_cache`` shared by the whole process. Stamping ``idx``
    onto the dicts it holds would put a key in the generated metadata that the committed
    file does not have, and ``test_generated_field_meta_is_current`` would start failing
    depending on test order.
    """
    load(auth_api, "CRM Deal")

    assert all("idx" not in f for f in field_meta.get_fields("CRM Deal"))


def test_depends_on_and_the_other_new_field_keys_survive_generation(auth_api):
    """The generator's FIELD_KEYS now keep what ``Field.vue`` reads.

    ``crm_call_log.json`` gives ``receiver`` a ``depends_on``; before this it was dropped
    on the floor and the field rendered unconditionally.
    """
    meta = generated()
    assert meta["CRM Call Log"]["fields"], "CRM Call Log must be in the generated file"

    call_log = load(auth_api, "CRM Call Log").json()["docs"][0]
    receiver = field_of(call_log, "receiver")

    assert receiver["depends_on"] == "eval:doc.type == 'Incoming'"
    # and a fetch_from, the other key the side panel acts on
    assert field_of(load(auth_api, "CRM Deal").json()["docs"][0], "website")["fetch_from"]


# ---------------------------------------------------------------------------
# with_parent
# ---------------------------------------------------------------------------


def test_with_parent_on_a_child_table_answers_with_the_parents_bundle(auth_api):
    """``load.py:getdoctype`` + ``meta.py:get_parent_dt``.

    ``CRM Contacts`` is embedded by ``CRM Deal`` and nothing else, so the parent is not
    a matter of which row the scan happens to reach first.
    """
    meta = generated()
    parents = [
        dt
        for dt, m in meta.items()
        if any(
            f["fieldtype"] in ("Table", "Table MultiSelect") and f.get("options") == "CRM Contacts"
            for f in m["fields"]
        )
    ]
    assert parents == ["CRM Deal"]

    body = load(auth_api, "CRM Contacts", with_parent=1).json()

    assert body["parent_dt"] == "CRM Deal"
    assert [doc["name"] for doc in body["docs"]] == expected_bundle("CRM Deal", meta)
    # the child the caller actually asked about is in there, which is the whole point
    assert "CRM Contacts" in [doc["name"] for doc in body["docs"]]


def test_with_parent_on_a_normal_doctype_is_a_no_op(auth_api):
    """``get_parent_dt`` returns nothing for anything that is not a child table, so the
    doctype's own bundle comes back and no ``parent_dt`` key is set."""
    body = load(auth_api, "CRM Deal", with_parent=1).json()

    assert "parent_dt" not in body
    assert body["docs"][0]["name"] == "CRM Deal"


def test_without_with_parent_a_child_table_answers_for_itself(auth_api):
    body = load(auth_api, "CRM Contacts").json()

    assert "parent_dt" not in body
    assert [doc["name"] for doc in body["docs"]] == ["CRM Contacts"]


# ---------------------------------------------------------------------------
# Errors, platform doctypes, auth
# ---------------------------------------------------------------------------


def test_unknown_doctype_is_404(auth_api):
    response = load(auth_api, "No Such Doctype")

    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"
    assert response.json()["message"] == "DocType No Such Doctype not found"


def test_a_platform_doctype_answers_with_model_derived_fields(auth_api):
    """``Contact`` ships no DocType JSON, so ``field_meta`` falls back to the model."""
    body = load(auth_api, "Contact").json()

    assert [doc["name"] for doc in body["docs"]] == ["Contact"]
    fields = body["docs"][0]["fields"]
    assert fields, "a registered platform doctype must still answer with its fields"
    assert {f["fieldname"] for f in fields} >= {"first_name", "email_id"}
    assert all("fieldtype" in f and "idx" in f for f in fields)
    # No JSON means no declared properties, so the defaults stand.
    assert body["docs"][0]["istable"] == 0
    assert body["docs"][0]["sort_field"] == "modified"


def test_getdoctype_needs_a_session(api):
    response = api.post(GETDOCTYPE, {"doctype": "CRM Deal"}, format="json")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------------


def save_settings(client, doctype: str, settings: dict):
    return client.post(
        SAVE, {"doctype": doctype, "user_settings": json.dumps(settings)}, format="json"
    )


def test_save_returns_what_was_sent(auth_api):
    """``user_settings.py:save`` returns its own parsed argument, not the merged state."""
    response = save_settings(auth_api, "CRM Deal", {"GridView": {"CRM Contacts": ["email"]}})

    assert response.status_code == 200
    assert response.json()["message"] == {"GridView": {"CRM Contacts": ["email"]}}


def test_save_merges_at_the_top_level(auth_api):
    """``update_user_settings``' ``current.update(user_settings)`` is one level deep."""
    save_settings(auth_api, "CRM Deal", {"GridView": {"CRM Contacts": ["email"]}})
    save_settings(auth_api, "CRM Deal", {"List": {"page_length": 40}})

    stored = json.loads(auth_api.post(GET_SETTINGS, {"doctype": "CRM Deal"}, format="json").json()["message"])

    assert stored == {
        "GridView": {"CRM Contacts": ["email"]},
        "List": {"page_length": 40},
    }


def test_a_second_save_of_the_same_key_replaces_it_wholesale(auth_api):
    """The merge is *not* recursive - that is what ``dict.update`` does, and the frontend
    sends the whole key every time (``stores/meta.js:saveUserSettings`` clones and
    rewrites the key before posting)."""
    save_settings(auth_api, "CRM Deal", {"GridView": {"CRM Contacts": ["email"]}})
    save_settings(auth_api, "CRM Deal", {"GridView": {"CRM Products": ["item"]}})

    stored = json.loads(auth_api.post(GET_SETTINGS, {"doctype": "CRM Deal"}, format="json").json()["message"])

    assert stored == {"GridView": {"CRM Products": ["item"]}}


def test_saved_settings_come_back_through_getdoctype(auth_api):
    """The round trip the frontend actually makes: save, then read it off the next meta
    load for the same doctype."""
    save_settings(auth_api, "CRM Deal", {"GridView": {"CRM Contacts": ["email", "mobile_no"]}})

    body = load(auth_api, "CRM Deal").json()

    assert json.loads(body["user_settings"]) == {
        "GridView": {"CRM Contacts": ["email", "mobile_no"]}
    }


def test_settings_are_per_doctype(auth_api):
    save_settings(auth_api, "CRM Deal", {"List": {"page_length": 40}})

    assert load(auth_api, "CRM Lead").json()["user_settings"] == "{}"


def test_with_parent_reads_the_parents_settings(auth_api):
    """``get_user_settings(parent_dt or doctype)`` - the saved state hangs off the
    parent, which is how ``getGridViewSettings(parentDoctype)`` finds it again."""
    save_settings(auth_api, "CRM Deal", {"GridView": {"CRM Contacts": ["email"]}})

    body = load(auth_api, "CRM Contacts", with_parent=1).json()

    assert json.loads(body["user_settings"]) == {"GridView": {"CRM Contacts": ["email"]}}


def test_each_user_sees_only_their_own_settings(auth_api, api_as, bob):
    """One row per (user, doctype). Nothing here is shared, and there is no route that
    could reach somebody else's row."""
    save_settings(auth_api, "CRM Deal", {"List": {"page_length": 40}})

    bob_api = api_as(bob)
    save_settings(bob_api, "CRM Deal", {"List": {"page_length": 5}})

    alice_body = load(auth_api, "CRM Deal").json()
    bob_body = load(bob_api, "CRM Deal").json()

    assert json.loads(alice_body["user_settings"]) == {"List": {"page_length": 40}}
    assert json.loads(bob_body["user_settings"]) == {"List": {"page_length": 5}}


def test_save_accepts_a_dict_as_well_as_a_json_string(auth_api):
    """``/api/method`` parses JSON-encoded query parameters before dispatch, so the same
    value reaches the handler as a string on POST and as a dict on GET."""
    response = auth_api.post(
        SAVE, {"doctype": "CRM Deal", "user_settings": {"List": {"page_length": 7}}}, format="json"
    )

    assert response.status_code == 200
    assert json.loads(load(auth_api, "CRM Deal").json()["user_settings"]) == {
        "List": {"page_length": 7}
    }


def test_empty_settings_are_stored_as_an_empty_object(auth_api):
    """``json.loads(user_settings or "{}")`` - upstream's first line."""
    response = auth_api.post(SAVE, {"doctype": "CRM Deal", "user_settings": ""}, format="json")

    assert response.status_code == 200
    assert response.json()["message"] == {}
    assert load(auth_api, "CRM Deal").json()["user_settings"] == "{}"


def test_saving_settings_needs_a_session(api):
    response = api.post(SAVE, {"doctype": "CRM Deal", "user_settings": "{}"}, format="json")

    assert response.status_code == 401
