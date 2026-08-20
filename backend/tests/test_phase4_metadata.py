"""Phase 4 — the metadata layer.

Covers `PHASE_4_METADATA.md` §4, plus C7 (allowlists keyed on the Frappe fieldtype) and
the half of C6 this phase owns (kanban manual ordering and the badge counts).

The load-bearing test is :func:`test_generated_field_meta_is_current`: the whole phase
rests on `crm_app/data/doctype_meta.json`, which is *generated* from the DocType JSON,
so it has to be provably in step with its source rather than a snapshot that quietly
rots.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from frappe_core import field_meta, metadata, registry
from frappe_core.api.doc import get_data
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

CRM_DOCTYPE_DIR = pathlib.Path(
    r"D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm\fcrm\doctype"
)


def call(client, path: str, payload: dict | None = None):
    return client.post(f"/api/method/{path}", payload or {}, format="json")


# ---------------------------------------------------------------------------
# The generated metadata must match its source
# ---------------------------------------------------------------------------


def test_generated_field_meta_is_current():
    """Regenerate from the DocType JSON and diff.

    Everything in this phase reads `doctype_meta.json`. If it drifts from the source,
    the allowlists, the layouts and the quick filters all go quietly wrong together.
    """
    if not CRM_DOCTYPE_DIR.exists():
        pytest.skip("CRM source not available")

    import sys

    scripts = pathlib.Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        import generate_field_meta

        regenerated = generate_field_meta.build()
    finally:
        sys.path.remove(str(scripts))

    committed = json.loads(
        (
            pathlib.Path(__file__).resolve().parent.parent
            / "crm_app"
            / "data"
            / "doctype_meta.json"
        ).read_text(encoding="utf-8")
    )
    assert committed == regenerated, (
        "doctype_meta.json is stale - run: python scripts/generate_field_meta.py"
    )


def test_field_meta_keeps_the_layout_breaks():
    """They are excluded from the models by design and are the layout here."""
    fieldtypes = {f["fieldtype"] for f in field_meta.get_fields("CRM Lead")}
    assert "Section Break" in fieldtypes
    assert "Tab Break" in fieldtypes or "Column Break" in fieldtypes


def test_value_fields_exclude_the_layout_breaks():
    fieldtypes = {f["fieldtype"] for f in field_meta.get_value_fields("CRM Lead")}
    assert not (fieldtypes & field_meta.NO_VALUE_FIELDTYPES)


def test_field_meta_falls_back_for_platform_doctypes():
    """The nine platform models ship no JSON; they derive from the Django model."""
    assert not field_meta.has_meta("User")
    fields = field_meta.get_fields("User")
    assert {f["fieldname"] for f in fields} >= {"name", "full_name", "enabled"}


# ---------------------------------------------------------------------------
# C7 - allowlists keyed on the Frappe fieldtype
# ---------------------------------------------------------------------------


def test_filterable_allowlist_matches_the_source_exactly():
    """``crm/api/doc.py:56-73``, transcribed rather than translated."""
    assert metadata.FILTERABLE_FIELDTYPES == {
        "Check", "Data", "Float", "Int", "Currency", "Dynamic Link", "Link",
        "Long Text", "Select", "Small Text", "Text Editor", "Text", "Duration",
        "Rating", "Date", "Datetime",
    }


def test_group_by_allowlist_matches_the_source_exactly():
    """``crm/api/doc.py:114-126`` - narrower, no free text."""
    assert metadata.GROUP_BY_FIELDTYPES == {
        "Check", "Data", "Float", "Int", "Currency", "Dynamic Link", "Link",
        "Select", "Duration", "Date", "Datetime",
    }


def test_duration_is_group_by_able():
    """C7's headline case.

    ``first_response_time`` is a ``Duration``, which upstream **does** allow to group
    by. Phase 0 mapped it to ``IntegerField``, so it was included only by accident -
    and ``Rating`` was filterable by the same accident. Now it is included on purpose.
    """
    assert field_meta.get_fieldtype("CRM Lead", "first_response_time") == "Duration"
    names = {f["fieldname"] for f in metadata.get_group_by_fields("CRM Lead")}
    assert "first_response_time" in names


def test_long_text_is_filterable_but_not_group_by_able():
    """The distinction phase 0 could not make: both were ``TextField``."""
    assert field_meta.get_fieldtype("CRM Lead", "lost_notes") == "Text"
    filterable = {f["fieldname"] for f in metadata.get_filterable_fields("CRM Lead")}
    group_by = {f["fieldname"] for f in metadata.get_group_by_fields("CRM Lead")}
    assert "lost_notes" in filterable
    assert "lost_notes" not in group_by


def test_text_editor_is_filterable_but_not_group_by_able():
    assert field_meta.get_fieldtype("CRM Lead Source", "details") == "Text Editor"
    filterable = {f["fieldname"] for f in metadata.get_filterable_fields("CRM Lead Source")}
    group_by = {f["fieldname"] for f in metadata.get_group_by_fields("CRM Lead Source")}
    assert "details" in filterable
    assert "details" not in group_by


def test_layout_fieldtypes_never_reach_the_allowlists():
    for doctype in ("CRM Lead", "CRM Deal"):
        for builder in (metadata.get_filterable_fields, metadata.get_group_by_fields):
            names = {f["fieldname"] for f in builder(doctype)}
            layout = {
                f["fieldname"]
                for f in field_meta.get_fields(doctype)
                if f["fieldtype"] in field_meta.LAYOUT_FIELDTYPES
            }
            assert not (names & layout)


@pytest.mark.parametrize("doctype", ["CRM Lead", "Phase Zero Widget"])
def test_get_non_filterable_fields_is_honoured(doctype):
    """`PHASE_4_METADATA.md` §3 - a controller may subtract from the filter list.

    Checked on a real CRM doctype *and* on the phase-0 test doctype, which declares
    ``notes``; a skip here would leave the criterion untested.
    """
    entry = registry.get_entry(doctype)
    restricted = set(entry.non_filterable_fields())
    assert restricted, f"{doctype} should declare non-filterable fields"
    names = {f["fieldname"] for f in metadata.get_filterable_fields(doctype)}
    assert not (names & restricted)


def test_non_filterable_fields_are_also_excluded_from_group_by():
    entry = registry.get_entry("CRM Lead")
    restricted = set(entry.non_filterable_fields())
    names = {f["fieldname"] for f in metadata.get_group_by_fields("CRM Lead")}
    assert not (names & restricted)


def test_standard_fields_appear_in_the_filter_list():
    names = {f["fieldname"] for f in metadata.get_filterable_fields("CRM Lead")}
    assert {
        "name", "owner", "modified_by", "creation", "modified",
        "_user_tags", "_liked_by", "_comments", "_assign",
    } <= names


def test_group_by_includes_the_standard_fields():
    names = {f["fieldname"] for f in metadata.get_group_by_fields("CRM Lead")}
    assert {"name", "creation", "modified", "modified_by", "owner", "_assign"} <= names


def test_filterable_fields_carry_the_link_target():
    by_name = {f["fieldname"]: f for f in metadata.get_filterable_fields("CRM Lead")}
    assert by_name["status"]["options"] == "CRM Lead Status"


# ---------------------------------------------------------------------------
# Saved views
# ---------------------------------------------------------------------------


@pytest.fixture
def lead_status(administrator):
    from crm_app.models import CRMLeadStatus

    with session_user(administrator.name):
        return CRMLeadStatus.objects.create(lead_status="New", type="Open")


def make_standard_view(user, columns, rows, view_type="list", doctype="CRM Lead"):
    from crm_app.api.view_settings import create_or_update_standard_view

    with session_user(user):
        return create_or_update_standard_view(
            {"doctype": doctype, "type": view_type, "columns": columns, "rows": rows}
        )


def test_saved_view_persists_per_user_and_type(alice, bob):
    from crm_app.models import CRMViewSettings

    make_standard_view(alice.name, [{"key": "email", "label": "Email"}], ["name", "email"])
    make_standard_view(bob.name, [{"key": "status", "label": "Status"}], ["name", "status"])

    assert CRMViewSettings.objects.filter(dt="CRM Lead", is_standard=True).count() == 2
    assert CRMViewSettings.objects.filter(user=alice).count() == 1


def test_one_users_saved_view_is_invisible_to_another(alice, bob, lead_status):
    """`PHASE_4_METADATA.md` §4's last criterion."""
    make_standard_view(alice.name, [{"key": "email", "label": "Email"}], ["name", "email"])

    with session_user(alice.name):
        alice_columns = [c["key"] for c in get_data(doctype="CRM Lead", filters={}, order_by="modified desc")["columns"]]
    with session_user(bob.name):
        bob_columns = [c["key"] for c in get_data(doctype="CRM Lead", filters={}, order_by="modified desc")["columns"]]

    assert alice_columns == ["email"]
    assert bob_columns != ["email"], "bob must get the controller default, not alice's view"


def test_get_views_only_returns_your_own_and_public_ones(alice, bob):
    from crm_app.api.views import get_views

    make_standard_view(alice.name, [{"key": "email"}], ["name"])
    with session_user(bob.name):
        assert get_views("CRM Lead") == []
    with session_user(alice.name):
        assert len(get_views("CRM Lead")) == 1


# ---------------------------------------------------------------------------
# get_data's four-step column resolution - extended, not rewritten
# ---------------------------------------------------------------------------


def test_step1_explicit_columns_win_over_a_saved_view(alice, lead_status):
    """A custom view must not consult the database at all."""
    make_standard_view(alice.name, [{"key": "email", "label": "Email"}], ["name", "email"])
    with session_user(alice.name):
        result = get_data(
            doctype="CRM Lead",
            filters={},
            order_by="modified desc",
            columns=[{"key": "mobile_no", "label": "Mobile", "type": "Data"}],
            rows=["name", "mobile_no"],
        )
    assert [c["key"] for c in result["columns"]] == ["mobile_no"]
    assert result["is_default"] is False


def test_step2_saved_view_is_used_when_no_columns_are_passed(alice, lead_status):
    make_standard_view(alice.name, [{"key": "email", "label": "Email"}], ["name", "email"])
    with session_user(alice.name):
        result = get_data(doctype="CRM Lead", filters={}, order_by="modified desc")
    assert [c["key"] for c in result["columns"]] == ["email"]
    assert result["is_default"] is False


def test_step3_controller_default_when_there_is_no_saved_view(alice, lead_status):
    with session_user(alice.name):
        result = get_data(doctype="CRM Lead", filters={}, order_by="modified desc")
    assert [c["key"] for c in result["columns"]] == [
        "lead_name", "organization", "status", "email", "mobile_no", "_assign", "modified",
    ]
    assert result["is_default"] is True


def test_step4_fallback_for_a_doctype_with_no_controller_default(alice):
    """``CRM Industry`` defines no ``default_list_data``."""
    with session_user(alice.name):
        result = get_data(doctype="CRM Industry", filters={}, order_by="modified desc")
    assert [c["key"] for c in result["columns"]] == ["name", "modified"]


def test_a_saved_view_for_a_different_view_type_does_not_apply(alice, lead_status):
    make_standard_view(alice.name, [{"key": "email"}], ["name", "email"], view_type="kanban")
    with session_user(alice.name):
        result = get_data(doctype="CRM Lead", filters={}, order_by="modified desc")
    assert [c["key"] for c in result["columns"]] != ["email"]


def test_get_data_response_keys_are_unchanged_from_phase_0(alice, lead_status):
    """`PHASE_4_METADATA.md` §4 - fill the stubs in, do not add or rename a key."""
    with session_user(alice.name):
        result = get_data(doctype="CRM Lead", filters={}, order_by="modified desc")
    assert set(result) == {
        "data", "columns", "rows", "fields", "column_field", "title_field",
        "kanban_columns", "kanban_fields", "group_by_field", "page_length",
        "page_length_count", "is_default", "views", "total_count", "row_count",
        "form_script", "list_script", "view_type",
    }


def test_get_data_now_returns_real_views(alice, lead_status):
    """Phase 0 stubbed ``views`` to ``[]``; it is wired now."""
    make_standard_view(alice.name, [{"key": "email"}], ["name", "email"])
    with session_user(alice.name):
        result = get_data(doctype="CRM Lead", filters={}, order_by="modified desc")
    assert len(result["views"]) == 1


def test_get_data_now_returns_a_real_form_script(alice, administrator, lead_status):
    from crm_app.models import CRMFormScript

    with session_user(administrator.name):
        script = CRMFormScript(name="lead-form", dt="CRM Lead", view="Form", enabled=True)
        script.script = "class CRMLead {}"
        script.save()

    with session_user(alice.name):
        result = get_data(doctype="CRM Lead", filters={}, order_by="modified desc")
    assert result["form_script"] == "class CRMLead {}"


def test_a_disabled_form_script_is_not_served(alice, administrator, lead_status):
    from crm_app.models import CRMFormScript

    with session_user(administrator.name):
        script = CRMFormScript(name="off", dt="CRM Lead", view="Form", enabled=False)
        script.script = "nope"
        script.save()
    with session_user(alice.name):
        result = get_data(doctype="CRM Lead", filters={}, order_by="modified desc")
    assert result["form_script"] is None


# ---------------------------------------------------------------------------
# Kanban - C6
# ---------------------------------------------------------------------------


def test_kanban_columns_from_a_link_target(alice, administrator):
    from crm_app.models import CRMDealStatus

    with session_user(administrator.name):
        CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        CRMDealStatus.objects.create(deal_status="Won", type="Won")

    with session_user(alice.name):
        result = get_data(
            doctype="CRM Deal", filters={}, order_by="modified desc",
            view={"view_type": "kanban"}, column_field="status",
        )
    assert {c["name"] for c in result["kanban_columns"]} == {"Qualification", "Won"}


def test_kanban_columns_from_select_options(alice, administrator):
    """``CRM Task.status`` is a Select, so its options are the columns."""
    with session_user(alice.name):
        result = get_data(
            doctype="CRM Task", filters={}, order_by="modified desc",
            view={"view_type": "kanban"}, column_field="status",
        )
    assert [c["name"] for c in result["kanban_columns"]] == [
        "Backlog", "Todo", "In Progress", "Done", "Canceled",
    ]


def test_kanban_cards_carry_the_badge_counts(alice, administrator, lead_status):
    """C6 - ``getCounts`` (``crm/api/doc.py:644-674``)."""
    from crm_app.models import CRMLead, CRMTask, FCRMNote
    from frappe_platform.models import Comment

    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=alice, status=lead_status)
        Comment.objects.create(
            comment_type="Comment", reference_doctype="CRM Lead",
            reference_name=lead.name, content="hi",
        )
        CRMTask.objects.create(
            title="Call", reference_doctype="CRM Lead", reference_docname=lead.name
        )
        FCRMNote.objects.create(
            title="Note", reference_doctype="CRM Lead", reference_docname=lead.name
        )
        result = get_data(
            doctype="CRM Lead", filters={}, order_by="modified desc",
            view={"view_type": "kanban"}, column_field="status",
        )

    card = result["data"][0]["data"][0]
    assert card["_comment_count"] == 1
    assert card["_task_count"] == 1
    assert card["_note_count"] == 1
    assert card["_email_count"] == 0


def test_kanban_manual_order_is_honoured(alice, administrator, lead_status):
    """C6 - ``get_records_based_on_order`` (``crm/api/doc.py:560-586``)."""
    from crm_app.models import CRMLead

    with session_user(alice.name):
        first = CRMLead.objects.create(first_name="A", lead_owner=alice, status=lead_status)
        second = CRMLead.objects.create(first_name="B", lead_owner=alice, status=lead_status)
        third = CRMLead.objects.create(first_name="C", lead_owner=alice, status=lead_status)

        wanted = [third.name, first.name, second.name]
        result = get_data(
            doctype="CRM Lead", filters={}, order_by="modified desc",
            view={"view_type": "kanban"}, column_field="status",
            kanban_columns=[{"name": "New", "order": wanted}],
        )

    assert [r["name"] for r in result["data"][0]["data"]] == wanted


def test_kanban_manual_order_is_permission_filtered(alice, bob, administrator, lead_status):
    """A card dragged into place by someone else must not leak through ``order``."""
    from crm_app.models import CRMLead

    with session_user(administrator.name):
        theirs = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=lead_status)
    with session_user(alice.name):
        mine = CRMLead.objects.create(first_name="Mine", lead_owner=alice, status=lead_status)
        result = get_data(
            doctype="CRM Lead", filters={}, order_by="modified desc",
            view={"view_type": "kanban"}, column_field="status",
            kanban_columns=[{"name": "New", "order": [theirs.name, mine.name]}],
        )

    names = [r["name"] for r in result["data"][0]["data"]]
    assert theirs.name not in names
    assert mine.name in names


# ---------------------------------------------------------------------------
# Form layouts
# ---------------------------------------------------------------------------


def test_default_layout_builds_tabs_from_the_breaks(auth_api):
    """`PHASE_4_METADATA.md` §4 - tabs/sections/columns matching upstream."""
    response = call(
        auth_api,
        "crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout",
        {"doctype": "CRM Lead", "type": "Quick Entry"},
    )
    assert response.status_code == 200
    tabs = response.json()["message"]
    assert tabs and "sections" in tabs[0]
    assert tabs[0]["sections"][0]["columns"]


def test_layout_expands_fieldnames_into_field_objects(auth_api, administrator):
    from crm_app.models import CRMFieldsLayout

    layout = [
        {
            "name": "tab1",
            "sections": [
                {"name": "s1", "columns": [{"name": "c1", "fields": ["first_name", "email"]}]}
            ],
        }
    ]
    with session_user(administrator.name):
        CRMFieldsLayout.objects.create(
            dt="CRM Lead", type="Quick Entry", layout=json.dumps(layout)
        )

    response = call(
        auth_api,
        "crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout",
        {"doctype": "CRM Lead", "type": "Quick Entry"},
    )
    fields = response.json()["message"][0]["sections"][0]["columns"][0]["fields"]
    assert [f["fieldname"] for f in fields] == ["first_name", "email"]
    assert fields[0]["fieldtype"] == "Data"


def test_layout_drops_a_field_the_doctype_no_longer_has(auth_api, administrator):
    from crm_app.models import CRMFieldsLayout

    layout = [
        {
            "name": "tab1",
            "sections": [
                {"name": "s1", "columns": [{"name": "c1", "fields": ["first_name", "gone"]}]}
            ],
        }
    ]
    with session_user(administrator.name):
        CRMFieldsLayout.objects.create(
            dt="CRM Lead", type="Quick Entry", layout=json.dumps(layout)
        )
    response = call(
        auth_api,
        "crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout",
        {"doctype": "CRM Lead", "type": "Quick Entry"},
    )
    fields = response.json()["message"][0]["sections"][0]["columns"][0]["fields"]
    assert [f["fieldname"] for f in fields] == ["first_name"]


def test_sidepanel_returns_empty_when_unconfigured(auth_api):
    response = call(
        auth_api,
        "crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections",
        {"doctype": "CRM Lead"},
    )
    assert response.json()["message"] == []


def test_sidepanel_expands_select_options(auth_api, administrator):
    from crm_app.models import CRMFieldsLayout

    layout = [{"label": "Details", "columns": [{"fields": ["no_of_employees"]}]}]
    with session_user(administrator.name):
        CRMFieldsLayout.objects.create(
            dt="CRM Lead", type="Side Panel", layout=json.dumps(layout)
        )
    response = call(
        auth_api,
        "crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections",
        {"doctype": "CRM Lead"},
    )
    field = response.json()["message"][0]["columns"][0]["fields"][0]
    assert field["options"][0] == {"label": "1-10", "value": "1-10"}
    assert field["placeholder"].startswith("Select ")


def test_save_fields_layout_is_role_gated(auth_api):
    response = call(
        auth_api,
        "crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.save_fields_layout",
        {"doctype": "CRM Lead", "type": "Quick Entry", "layout": "[]"},
    )
    assert response.status_code == 403
    assert response.json()["messages"] == ["Not permitted to modify fields layout"]


# ---------------------------------------------------------------------------
# View settings endpoints
# ---------------------------------------------------------------------------


def test_view_settings_endpoints_are_registered():
    from frappe_core.whitelist import all_methods

    base = "crm.fcrm.doctype.crm_view_settings.crm_view_settings."
    for name in (
        "create", "update", "delete", "public", "pin", "set_as_default",
        "create_or_update_standard_view", "fetch_and_update_kanban_columns",
    ):
        assert base + name in all_methods()


def test_create_merges_the_controller_default_rows(alice):
    from crm_app.api.view_settings import create

    with session_user(alice.name):
        view = create({"doctype": "CRM Lead", "label": "Mine", "type": "list", "rows": ["email"]})
    rows = json.loads(view["rows"])
    assert "email" in rows
    assert "lead_name" in rows, "controller default rows must be merged in"
    assert len(rows) == len(set(rows)), "and deduplicated"


def test_only_the_owner_can_update_a_private_view(alice, bob):
    from crm_app.api.view_settings import create, update
    from frappe_core.exceptions import PermissionError as FrappePermissionError

    with session_user(alice.name):
        view = create({"doctype": "CRM Lead", "label": "Mine", "type": "list"})

    with session_user(bob.name), pytest.raises(FrappePermissionError):
        update({"name": view["name"], "doctype": "CRM Lead", "label": "Stolen"})


def test_a_sales_manager_can_edit_a_public_view(alice, make_user):
    from crm_app.api.view_settings import create, public, update

    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    with session_user(alice.name):
        view = create({"doctype": "CRM Lead", "label": "Shared", "type": "list"})
    with session_user(manager.name):
        public(view["name"], True)
        update({"name": view["name"], "doctype": "CRM Lead", "label": "Renamed"})

    from crm_app.models import CRMViewSettings

    assert CRMViewSettings.objects.get(pk=view["name"]).label == "Renamed"


def test_making_a_view_public_clears_its_owner_and_pin(alice, make_user):
    from crm_app.api.view_settings import create, pin, public
    from crm_app.models import CRMViewSettings

    manager = make_user("mgr2@example.com", roles=["Sales Manager"])
    with session_user(alice.name):
        view = create({"doctype": "CRM Lead", "label": "P", "type": "list"})
        pin(view["name"], True)
    with session_user(manager.name):
        public(view["name"], True)

    row = CRMViewSettings.objects.get(pk=view["name"])
    assert row.public is True
    assert row.pinned is False
    assert row.user_id is None


def test_public_requires_sales_manager(alice):
    from crm_app.api.view_settings import create, public
    from frappe_core.exceptions import PermissionError as FrappePermissionError

    with session_user(alice.name):
        view = create({"doctype": "CRM Lead", "label": "P", "type": "list"})
        with pytest.raises(FrappePermissionError):
            public(view["name"], True)


def test_set_as_default_clears_the_previous_default(alice):
    from crm_app.api.view_settings import create, set_as_default
    from crm_app.models import CRMViewSettings

    with session_user(alice.name):
        first = create({"doctype": "CRM Lead", "label": "A", "type": "list"})
        second = create({"doctype": "CRM Lead", "label": "B", "type": "list"})
        set_as_default(first["name"])
        set_as_default(second["name"])

    assert CRMViewSettings.objects.get(pk=first["name"]).is_default is False
    assert CRMViewSettings.objects.get(pk=second["name"]).is_default is True


def test_set_as_default_does_not_touch_another_users_default(alice, bob):
    from crm_app.api.view_settings import create, set_as_default
    from crm_app.models import CRMViewSettings

    with session_user(bob.name):
        theirs = create({"doctype": "CRM Lead", "label": "Theirs", "type": "list"})
        set_as_default(theirs["name"])
    with session_user(alice.name):
        mine = create({"doctype": "CRM Lead", "label": "Mine", "type": "list"})
        set_as_default(mine["name"])

    assert CRMViewSettings.objects.get(pk=theirs["name"]).is_default is True


def test_fetch_and_update_kanban_columns_marks_new_ones_deleted(alice, administrator):
    """A column added since the view was saved arrives flagged ``delete: True``."""
    from crm_app.api.view_settings import create, fetch_and_update_kanban_columns
    from crm_app.models import CRMDealStatus

    with session_user(administrator.name):
        CRMDealStatus.objects.create(deal_status="Qualification", type="Open")

    with session_user(alice.name):
        view = create(
            {
                "doctype": "CRM Deal", "label": "Board", "type": "kanban",
                "column_field": "status",
            }
        )

    with session_user(administrator.name):
        CRMDealStatus.objects.create(deal_status="Negotiation", type="Ongoing")

    with session_user(alice.name):
        columns = json.loads(fetch_and_update_kanban_columns(view["name"]))

    by_name = {c["name"]: c for c in columns}
    assert by_name["Qualification"].get("delete") is None
    assert by_name["Negotiation"]["delete"] is True


def test_fetch_and_update_kanban_columns_ignores_a_list_view(alice):
    from crm_app.api.view_settings import create, fetch_and_update_kanban_columns

    with session_user(alice.name):
        view = create({"doctype": "CRM Lead", "label": "L", "type": "list"})
        assert fetch_and_update_kanban_columns(view["name"]) is None


def test_delete_requires_permission(alice, bob):
    from crm_app.api.view_settings import create, delete
    from frappe_core.exceptions import PermissionError as FrappePermissionError

    with session_user(alice.name):
        view = create({"doctype": "CRM Lead", "label": "Mine", "type": "list"})
    with session_user(bob.name), pytest.raises(FrappePermissionError):
        delete(view["name"])


def test_route_name_derivation():
    from crm_app.api.view_settings import get_route_name

    assert get_route_name("CRM Lead") == "Leads"
    assert get_route_name("CRM Deal") == "Deals"
    assert get_route_name("Contact") == "Contacts"


# ---------------------------------------------------------------------------
# The allowlists must only advertise fields that can actually be queried
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doctype",
    ["CRM Lead", "CRM Deal", "CRM Task", "CRM Organization", "CRM Call Log", "FCRM Note"],
)
def test_every_filterable_field_is_actually_filterable(doctype, alice):
    """C7 moved the allowlists off the Django model and onto the DocType JSON.

    That is right, but it introduces a way to be wrong that did not exist before: a
    field present in the JSON but never materialised as a column would now be offered
    in the filter dropdown and then 417 when used. Every advertised field is exercised
    against the real query layer.
    """
    from frappe_core.exceptions import ValidationError
    from frappe_core.query import fetch_rows

    failures = []
    for field in metadata.get_filterable_fields(doctype):
        fieldname = field["fieldname"]
        with session_user(alice.name):
            try:
                fetch_rows(
                    doctype,
                    fields=["name"],
                    filters={fieldname: ["is", "set"]},
                    limit_page_length=1,
                )
            except ValidationError as exc:
                failures.append(f"{fieldname}: {exc.message}")
    assert not failures, f"{doctype} advertises unfilterable fields: {failures}"


@pytest.mark.parametrize("doctype", ["CRM Lead", "CRM Deal", "CRM Task"])
def test_every_group_by_field_is_actually_orderable(doctype, alice):
    """Same risk on the group-by list, which the UI turns into an ``order_by``."""
    from frappe_core.exceptions import ValidationError
    from frappe_core.query import fetch_rows

    failures = []
    for field in metadata.get_group_by_fields(doctype):
        fieldname = field["fieldname"]
        with session_user(alice.name):
            try:
                fetch_rows(
                    doctype, fields=["name"], order_by=f"{fieldname} asc", limit_page_length=1
                )
            except ValidationError as exc:
                failures.append(f"{fieldname}: {exc.message}")
    assert not failures, f"{doctype} advertises ungroupable fields: {failures}"


# ---------------------------------------------------------------------------
# Review findings — the generic /api/resource/ route, which the endpoints bypass
# ---------------------------------------------------------------------------

from urllib.parse import quote  # noqa: E402


def _client_for(user):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def test_a_private_saved_view_is_invisible_through_the_generic_route(alice, bob):
    """Codex phase-4 High finding.

    ``get_views`` scoped correctly, but ``/api/resource/CRM View Settings`` did not go
    through it — and a doctype with no permission hook is world-readable. The criterion
    is "invisible to another user", not "invisible through one endpoint".
    """
    make_standard_view(alice.name, [{"key": "email"}], ["name", "email"])

    response = _client_for(bob).get("/api/resource/" + quote("CRM View Settings"))
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_a_private_saved_view_cannot_be_read_by_name(alice, bob):
    from crm_app.models import CRMViewSettings

    make_standard_view(alice.name, [{"key": "email"}], ["name", "email"])
    view = CRMViewSettings.objects.get(user=alice)

    response = _client_for(bob).get(
        "/api/resource/" + quote("CRM View Settings") + f"/{view.pk}"
    )
    assert response.status_code == 403


def test_a_public_saved_view_is_visible_to_everyone(alice, bob, make_user):
    from crm_app.api.view_settings import create, public
    from crm_app.models import CRMViewSettings

    manager = make_user("mgr3@example.com", roles=["Sales Manager"])
    with session_user(alice.name):
        view = create({"doctype": "CRM Lead", "label": "Shared", "type": "list"})
    with session_user(manager.name):
        public(view["name"], True)

    response = _client_for(bob).get("/api/resource/" + quote("CRM View Settings"))
    assert [r["name"] for r in response.json()["data"]] == [view["name"]]


def test_another_users_saved_view_cannot_be_edited_through_the_generic_route(alice, bob):
    from crm_app.models import CRMViewSettings

    make_standard_view(alice.name, [{"key": "email"}], ["name", "email"])
    view = CRMViewSettings.objects.get(user=alice)

    response = _client_for(bob).put(
        "/api/resource/" + quote("CRM View Settings") + f"/{view.pk}",
        {"label": "Hijacked"},
        format="json",
    )
    assert response.status_code == 403
    assert CRMViewSettings.objects.get(pk=view.pk).label != "Hijacked"


def test_a_sales_user_cannot_write_a_form_script(alice):
    """Codex phase-4 High finding — this one is an XSS boundary.

    ``get_data`` serves ``form_script`` to every client, which executes it. A Sales User
    who could author one would be running code in every colleague's browser.
    """
    response = _client_for(alice).post(
        "/api/resource/" + quote("CRM Form Script"),
        {"name": "evil", "dt": "CRM Lead", "view": "Form", "script": "steal()", "enabled": True},
        format="json",
    )
    assert response.status_code == 403

    from crm_app.models import CRMFormScript

    assert not CRMFormScript.objects.filter(pk="evil").exists()


def test_a_sales_user_cannot_edit_an_existing_form_script(alice, administrator):
    from crm_app.models import CRMFormScript

    with session_user(administrator.name):
        script = CRMFormScript(name="ok", dt="CRM Lead", view="Form", enabled=True)
        script.script = "safe()"
        script.save()

    response = _client_for(alice).put(
        "/api/resource/" + quote("CRM Form Script") + "/ok",
        {"script": "steal()"},
        format="json",
    )
    assert response.status_code == 403
    assert CRMFormScript.objects.get(pk="ok").script == "safe()"


def test_a_sales_user_can_still_read_a_form_script(alice, administrator):
    """Reading is not the boundary — the frontend has to receive it."""
    from crm_app.models import CRMFormScript

    with session_user(administrator.name):
        script = CRMFormScript(name="readable", dt="CRM Lead", view="Form", enabled=True)
        script.script = "safe()"
        script.save()

    response = _client_for(alice).get("/api/resource/" + quote("CRM Form Script") + "/readable")
    assert response.status_code == 200


def test_a_sales_manager_can_write_a_form_script(make_user):
    manager = make_user("scripter@example.com", roles=["Sales Manager"])
    response = _client_for(manager).post(
        "/api/resource/" + quote("CRM Form Script"),
        {"name": "fine", "dt": "CRM Lead", "view": "Form", "script": "ok()"},
        format="json",
    )
    assert response.status_code == 201


def test_a_sales_user_cannot_write_a_fields_layout(alice):
    """``save_fields_layout`` was gated; the generic route was the way around it."""
    response = _client_for(alice).post(
        "/api/resource/" + quote("CRM Fields Layout"),
        {"dt": "CRM Lead", "type": "Quick Entry", "layout": "[]"},
        format="json",
    )
    assert response.status_code == 403


def test_load_default_columns_is_read_off_the_named_view(alice, lead_status):
    """Codex phase-4 Medium finding — the last phase-0 stub, now filled.

    ``crm/api/doc.py:485-486``: a named view flagged ``load_default_columns`` reports
    itself as default, which is how the frontend chooses between "reset to default" and
    "save changes".
    """
    from crm_app.api.view_settings import create
    from crm_app.models import CRMViewSettings

    with session_user(alice.name):
        view = create(
            {
                "doctype": "CRM Lead", "label": "Flagged", "type": "list",
                "load_default_columns": True,
                "columns": [{"key": "email", "label": "Email"}],
                "rows": ["name", "email"],
            }
        )
        result = get_data(
            doctype="CRM Lead", filters={}, order_by="modified desc",
            columns=[{"key": "email", "label": "Email"}], rows=["name", "email"],
            view={"custom_view_name": view["name"]},
        )
    assert CRMViewSettings.objects.get(pk=view["name"]).load_default_columns is True
    assert result["is_default"] is True


def test_a_named_view_without_the_flag_is_not_default(alice, lead_status):
    from crm_app.api.view_settings import create

    with session_user(alice.name):
        view = create(
            {
                "doctype": "CRM Lead", "label": "Plain", "type": "list",
                "columns": [{"key": "email", "label": "Email"}], "rows": ["name", "email"],
            }
        )
        result = get_data(
            doctype="CRM Lead", filters={}, order_by="modified desc",
            columns=[{"key": "email", "label": "Email"}], rows=["name", "email"],
            view={"custom_view_name": view["name"]},
        )
    assert result["is_default"] is False
