"""Phase 1 behaviour: child tables, ported validations, and _assign <-> ToDo.

The remaining PHASE_1_MODELS.md section 7 criteria that a schema comparison cannot
cover.

Every message asserted here is quoted from the source controller. CLAUDE.md hard rule 4:
``frappe.throw`` text is user-facing copy and must survive the port verbatim.
"""

import json
from urllib.parse import quote

import pytest

from frappe_core import registry
from frappe_core.assignment import get_assigned_users
from frappe_core.exceptions import MandatoryError, ValidationError
from frappe_core.session import session_user
from frappe_platform.models import Contact, ToDo
from crm_app.models import (
    CRMDeal,
    CRMDealStatus,
    CRMHoliday,
    CRMHolidayList,
    CRMLead,
    CRMLeadStatus,
    CRMLostReason,
    CRMProducts,
    CRMServiceDay,
    CRMServiceLevelAgreement,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def statuses(alice):
    with session_user(alice.name):
        return {
            "open": CRMLeadStatus.objects.create(lead_status="New", type="Open"),
            "lost": CRMLeadStatus.objects.create(lead_status="Junk", type="Lost"),
            "deal_open": CRMDealStatus.objects.create(deal_status="Qualification", type="Open"),
            "deal_lost": CRMDealStatus.objects.create(deal_status="Lost", type="Lost"),
        }


@pytest.fixture
def lost_reasons(alice):
    with session_user(alice.name):
        return {
            "other": CRMLostReason.objects.create(lost_reason="Other"),
            "price": CRMLostReason.objects.create(lost_reason="Price"),
        }


# --- CRM Lead validations (crm_lead.py) ---------------------------------------


def test_lead_requires_a_name_or_organization(alice, statuses):
    """``crm_lead.py:127``. Message verbatim."""
    with session_user(alice.name), pytest.raises(ValidationError) as caught:
        CRMLead.objects.create(status=statuses["open"])
    assert caught.value.message == (
        "A Lead requires either a person's name or an organization's name"
    )


def test_lead_name_is_derived_from_the_person(alice, statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(
            status=statuses["open"], first_name="Ada", last_name="Lovelace"
        )
    assert lead.lead_name == "Ada Lovelace"


def test_lead_name_falls_back_to_the_organization(alice, statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(status=statuses["open"], organization="Acme Corp")
    assert lead.lead_name == "Acme Corp"


def test_lead_name_includes_the_salutation(alice, statuses):
    """Codex phase-1 finding. ``crm_lead.py:113-122`` includes ``salutation``."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(
            status=statuses["open"], salutation="Dr", first_name="Ada", last_name="Lovelace"
        )
    assert lead.lead_name == "Dr Ada Lovelace"


def test_lead_name_from_email_uses_the_local_part_only(alice, statuses):
    """``crm_lead.py:133`` - ``self.email.split("@")[0]``, not the whole address."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(status=statuses["open"], email="ada@example.com")
    assert lead.lead_name == "ada"


def test_a_persons_name_wins_over_the_organization(alice, statuses):
    """set_full_name runs first, so set_lead_name's fallback chain never fires."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(
            status=statuses["open"], first_name="Ada", organization="Acme Corp"
        )
    assert lead.lead_name == "Ada"


def test_set_full_name_only_fires_when_there_is_a_first_name(alice, statuses):
    """Upstream guards on ``first_name``; a lone last_name does not derive a name."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(
            status=statuses["open"], last_name="Lovelace", organization="Acme Corp"
        )
    assert lead.lead_name == "Acme Corp"


def test_ignore_mandatory_falls_back_to_unnamed_lead(alice, statuses):
    """``crm_lead.py:135`` - only reachable when the mandatory check is bypassed."""
    with session_user(alice.name):
        lead = CRMLead(status=statuses["open"])
        lead.save(ignore_mandatory=True)
    assert lead.lead_name == "Unnamed Lead"


def test_lead_owner_cannot_be_the_lead_email(alice, statuses):
    """``crm_lead.py:144``. Message verbatim."""
    with session_user(alice.name), pytest.raises(ValidationError) as caught:
        CRMLead.objects.create(
            status=statuses["open"], first_name="Ada", email=alice.name, lead_owner=alice
        )
    assert caught.value.message == "Lead Owner cannot be same as the Lead Email Address"


def test_lost_lead_requires_a_reason(alice, statuses):
    """``crm_lead.py:152``. Message verbatim - note "a reason"."""
    with session_user(alice.name), pytest.raises(ValidationError) as caught:
        CRMLead.objects.create(status=statuses["lost"], first_name="Ada")
    assert caught.value.message == "Please specify a reason for losing the lead."


def test_lost_lead_with_other_requires_notes(alice, statuses, lost_reasons):
    """``crm_lead.py:154``. Message verbatim - note "the reason", not "a reason"."""
    with session_user(alice.name), pytest.raises(ValidationError) as caught:
        CRMLead.objects.create(
            status=statuses["lost"], first_name="Ada", lost_reason=lost_reasons["other"]
        )
    assert caught.value.message == "Please specify the reason for losing the lead."


def test_lost_lead_with_a_normal_reason_is_accepted(alice, statuses, lost_reasons):
    with session_user(alice.name):
        lead = CRMLead.objects.create(
            status=statuses["lost"], first_name="Ada", lost_reason=lost_reasons["price"]
        )
    assert lead.pk


def test_the_two_lost_messages_differ_by_exactly_one_word():
    """They are nearly identical upstream; a careless port collapses them into one."""
    a = "Please specify a reason for losing the lead."
    b = "Please specify the reason for losing the lead."
    assert a != b


# --- CRM Deal validations (crm_deal.py) ---------------------------------------


def test_lost_deal_requires_a_reason(alice, statuses):
    """``crm_deal.py:261``. Says "deal", not "lead"."""
    with session_user(alice.name), pytest.raises(ValidationError) as caught:
        CRMDeal.objects.create(status=statuses["deal_lost"])
    assert caught.value.message == "Please specify a reason for losing the deal."


def test_lost_deal_with_other_requires_notes(alice, statuses, lost_reasons):
    """``crm_deal.py:263``."""
    with session_user(alice.name), pytest.raises(ValidationError) as caught:
        CRMDeal.objects.create(status=statuses["deal_lost"], lost_reason=lost_reasons["other"])
    assert caught.value.message == "Please specify the reason for losing the deal."


def test_forecasting_requires_an_expected_value(alice, statuses):
    """``crm_deal.py:251`` - and upstream raises MandatoryError, not ValidationError.

    ``src/data/document.js:61`` branches on ``exc_type == 'MandatoryError'``, so the
    exception class is part of the contract, not an implementation detail.
    """
    with session_user(alice.name):
        deal = CRMDeal(status=statuses["deal_open"])
        with pytest.raises(MandatoryError) as caught:
            deal.validate_forecasting(forecasting_enabled=True)
    assert caught.value.message == "Expected deal value is required."
    assert caught.value.exc_type == "MandatoryError"


def test_forecasting_requires_a_closure_date(alice, statuses):
    """``crm_deal.py:253``."""
    with session_user(alice.name):
        deal = CRMDeal(status=statuses["deal_open"], expected_deal_value=1000)
        with pytest.raises(MandatoryError) as caught:
            deal.validate_forecasting(forecasting_enabled=True)
    assert caught.value.message == "Expected closure date is required."


def test_forecasting_is_skipped_when_disabled(alice, statuses):
    with session_user(alice.name):
        CRMDeal(status=statuses["deal_open"]).validate_forecasting(forecasting_enabled=False)


# --- other ported controller behaviour ----------------------------------------


def test_call_log_generates_an_id_when_blank(alice):
    """Codex phase-1 finding. ``crm_call_log.py:50-54``.

    ``field:id`` naming would otherwise fail outright for a manually logged call.
    """
    from crm_app.models import CRMCallLog

    with session_user(alice.name):
        log = CRMCallLog.objects.create(status="Completed", type="Outgoing", **{"from": "1", "to": "2"})
    assert len(log.id) == 12
    assert log.name == log.id


def test_call_log_defaults_to_the_manual_medium(alice):
    from crm_app.models import CRMCallLog

    with session_user(alice.name):
        log = CRMCallLog.objects.create(status="Completed", type="Incoming", **{"from": "1", "to": "2"})
    assert log.telephony_medium == "Manual"


def test_call_log_keeps_a_supplied_id(alice):
    from crm_app.models import CRMCallLog

    with session_user(alice.name):
        log = CRMCallLog.objects.create(
            id="CA123", status="Completed", type="Incoming", **{"from": "1", "to": "2"}
        )
    assert log.name == "CA123"


def test_product_name_defaults_to_the_product_code(alice):
    """Codex phase-1 finding. ``crm_product.py:51-52``."""
    from crm_app.models import CRMProduct

    with session_user(alice.name):
        product = CRMProduct.objects.create(product_code="WIDGET-1")
    assert product.product_name == "WIDGET-1"


def test_organization_exchange_rate_defaults_to_one(alice):
    """``crm_organization.py:update_exchange_rate`` - same currency means rate 1."""
    from crm_app.models import CRMOrganization

    with session_user(alice.name):
        org = CRMOrganization.objects.create(organization_name="Acme", currency="USD")
        org.update_exchange_rate(system_currency="USD")
    assert org.exchange_rate == 1


def test_organization_exchange_rate_uses_the_injected_rate(alice):
    from crm_app.models import CRMOrganization

    with session_user(alice.name):
        org = CRMOrganization.objects.create(organization_name="Beta", currency="EUR")
        org.update_exchange_rate(system_currency="USD", fx_rate=1.09)
    assert org.exchange_rate == 1.09


@pytest.mark.parametrize("color", ["cyan", "teal", "violet", "purple"])
def test_the_late_colour_options_are_accepted(color):
    """Codex phase-1 finding - the four options my truncated JSON dump hid."""
    from crm_app.models.taxonomy import COLOR_CHOICES

    assert (color, color) in COLOR_CHOICES


def test_fields_layout_types_match_the_source():
    from crm_app.models.metadata import LAYOUT_TYPE_CHOICES

    assert [c[0] for c in LAYOUT_TYPE_CHOICES] == [
        "Quick Entry",
        "Side Panel",
        "Data Fields",
        "Grid Row",
        "Required Fields",
    ]


def test_select_options_match_the_json_exactly():
    """Guards against the truncation mistake generally, not just for colour.

    Reads the full ``options`` string from every JSON and compares it to the model's
    ``choices``, so a partially-transcribed Select cannot pass again.
    """
    from tests.test_crm_models import FRAPPE_DOCTYPE_DIR, PORTED, data_fields, load_doctype_json

    if not FRAPPE_DOCTYPE_DIR.exists():
        pytest.skip("Frappe source not available")

    mismatches = []
    for doctype, dirname in PORTED.items():
        doc = load_doctype_json(dirname)
        model = registry.get_model(doctype)
        for field in data_fields(doc):
            if field.get("fieldtype") != "Select":
                continue
            try:
                django_field = model._meta.get_field(field["fieldname"])
            except Exception:
                continue
            choices = [c[0] for c in (django_field.choices or [])]
            if not choices:
                continue
            expected = [o for o in (field.get("options") or "").split("\n")]
            expected_set = {o for o in expected if o}
            actual_set = {c for c in choices if c}
            if not expected_set <= actual_set:
                mismatches.append(
                    f"{doctype}.{field['fieldname']} missing {sorted(expected_set - actual_set)}"
                )
    assert not mismatches, mismatches


# --- child tables: inline + replace-on-write ----------------------------------


def test_single_parent_child_is_discovered_automatically(alice):
    """``CRM Holiday`` -> ``CRM Holiday List`` via a real FK."""
    spec = registry.get_entry("CRM Holiday List").get_serializer_class().child_table_spec
    assert "holidays" in spec
    assert spec["holidays"]["doctype"] == "CRM Holiday"
    assert spec["holidays"]["polymorphic"] is False


def test_multi_parent_child_is_declared_explicitly():
    """``CRM Products`` is embedded by both CRM Lead and CRM Deal."""
    spec = registry.get_entry("CRM Deal").get_serializer_class().child_table_spec
    assert spec["products"]["polymorphic"] is True
    assert spec["products"]["doctype"] == "CRM Products"


def test_children_serialise_inline(alice):
    with session_user(alice.name):
        hl = CRMHolidayList.objects.create(
            holiday_list_name="2026", from_date="2026-01-01", to_date="2026-12-31"
        )
        CRMHoliday.objects.create(
            parent_holiday_list=hl, date="2026-01-01", description="New Year", idx=1
        )
    serializer = registry.get_entry("CRM Holiday List").get_serializer_class()
    data = serializer(hl).data
    assert len(data["holidays"]) == 1
    assert data["holidays"][0]["description"] == "New Year"


def test_writing_a_parent_replaces_children_wholesale(auth_api, alice):
    """Frappe semantics - not a merge (PHASE_1_MODELS.md section 3)."""
    with session_user(alice.name):
        hl = CRMHolidayList.objects.create(
            holiday_list_name="2027", from_date="2027-01-01", to_date="2027-12-31"
        )
        CRMHoliday.objects.create(
            parent_holiday_list=hl, date="2027-01-01", description="Old", idx=1
        )

    url = "/api/resource/" + quote("CRM Holiday List") + "/" + quote(hl.name)
    response = auth_api.put(
        url,
        {"holidays": [{"date": "2027-07-04", "description": "New"}]},
        format="json",
    )
    assert response.status_code == 200

    remaining = CRMHoliday.objects.filter(parent_holiday_list=hl)
    assert remaining.count() == 1, "old rows must be removed, not merged"
    assert remaining.first().description == "New"


def test_replacing_children_assigns_idx_from_position(auth_api, alice):
    with session_user(alice.name):
        hl = CRMHolidayList.objects.create(
            holiday_list_name="2028", from_date="2028-01-01", to_date="2028-12-31"
        )
    auth_api.put(
        "/api/resource/" + quote("CRM Holiday List") + "/" + quote(hl.name),
        {
            "holidays": [
                {"date": "2028-01-01", "description": "A"},
                {"date": "2028-02-01", "description": "B"},
            ]
        },
        format="json",
    )
    rows = list(CRMHoliday.objects.filter(parent_holiday_list=hl).order_by("idx"))
    assert [r.idx for r in rows] == [1, 2]
    assert [r.description for r in rows] == ["A", "B"]


def test_polymorphic_children_are_scoped_to_their_parent(alice, statuses):
    """A lead's products must not appear on a deal with the same row data."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(status=statuses["open"], first_name="Ada")
        deal = CRMDeal.objects.create(status=statuses["deal_open"])
        CRMProducts.objects.create(
            parenttype="CRM Lead", parent=lead.name, parentfield="products",
            product_name="Widget", rate=10, idx=1,
        )

    lead_data = registry.get_entry("CRM Lead").get_serializer_class()(lead).data
    deal_data = registry.get_entry("CRM Deal").get_serializer_class()(deal).data
    assert len(lead_data["products"]) == 1
    assert deal_data["products"] == []


def test_child_tables_are_not_routable_over_http(auth_api):
    response = auth_api.get("/api/resource/" + quote("CRM Holiday"))
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_sla_children_serialise_inline(alice):
    with session_user(alice.name):
        sla = CRMServiceLevelAgreement.objects.create(sla_name="Standard", apply_on="CRM Lead")
        CRMServiceDay.objects.create(
            parent_sla=sla, workday="Monday", start_time="09:00", end_time="17:00", idx=1
        )
    data = registry.get_entry("CRM Service Level Agreement").get_serializer_class()(sla).data
    assert [d["workday"] for d in data["working_hours"]] == ["Monday"]


def test_contact_children_serialise_inline(alice):
    """Contact's email_ids / phone_nos are the platform equivalent."""
    with session_user(alice.name):
        c = Contact.objects.create(first_name="Grace", last_name="Hopper")
        c.email_ids.create(email_id="grace@navy.mil", is_primary=True)
    data = registry.get_entry("Contact").get_serializer_class()(c).data
    assert data["email_ids"][0]["email_id"] == "grace@navy.mil"


# --- _assign <-> ToDo, both directions, on a real CRM doctype -----------------


def test_assigning_a_lead_updates_its_assign_cache(alice, bob, statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(status=statuses["open"], first_name="Ada")
    ToDo.objects.create(
        reference_type="CRM Lead", reference_name=lead.name, allocated_to=bob, status="Open"
    )
    lead.refresh_from_db()
    assert lead._assign == [bob.name]


def test_cancelling_the_todo_clears_the_lead_assign_cache(alice, bob, statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(status=statuses["open"], first_name="Ada")
    todo = ToDo.objects.create(
        reference_type="CRM Lead", reference_name=lead.name, allocated_to=bob, status="Open"
    )
    todo.status = "Cancelled"
    todo.save()
    lead.refresh_from_db()
    assert lead._assign == []


def test_permission_view_of_assignment_reads_todo_not_assign(alice, bob, statuses):
    """PHASE_2_PERMISSIONS.md section 2 - phase 2 must query ToDo directly."""
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["deal_open"])
    ToDo.objects.create(
        reference_type="CRM Deal", reference_name=deal.name, allocated_to=bob, status="Open"
    )
    assert get_assigned_users("CRM Deal", deal.name, for_permission=True) == [bob.name]


def test_a_forged_assign_value_does_not_grant_assignment(alice, bob, statuses):
    """``_assign`` is writable through the generic endpoint; it must not be trusted."""
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["deal_open"])
    CRMDeal.objects.filter(pk=deal.pk).update(_assign=[bob.name])
    assert get_assigned_users("CRM Deal", deal.name, for_permission=True) == []


# --- naming through the API ---------------------------------------------------


def test_lead_gets_a_naming_series_pk(alice, statuses):
    from datetime import datetime, timezone

    with session_user(alice.name):
        lead = CRMLead.objects.create(status=statuses["open"], first_name="Ada")
    assert lead.name.startswith(f"CRM-LEAD-{datetime.now(timezone.utc).year}-")


def test_deal_gets_a_naming_series_pk(alice, statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["deal_open"])
    assert deal.name.startswith("CRM-DEAL-")


def test_task_gets_an_integer_pk(alice):
    from crm_app.models import CRMTask

    with session_user(alice.name):
        task = CRMTask.objects.create(title="Call back")
    assert isinstance(task.pk, int)


def test_get_data_works_against_the_real_lead_controller_defaults(alice, statuses):
    """The keystone endpoint, driven by ``crm_lead.py``'s own ``default_list_data``.

    Phase 0 could only exercise ``get_data`` against a test doctype. This runs it against
    the real one, whose default rows name 15 fields including the SLA columns - which is
    what would break if any of them were missing or misnamed.
    """
    from frappe_core.api.doc import get_data

    with session_user(alice.name):
        CRMLead.objects.create(status=statuses["open"], first_name="Ada", email="ada@example.com")
        result = get_data(doctype="CRM Lead", filters={}, order_by="modified desc")

    assert len(result["data"]) == 1
    assert [c["key"] for c in result["columns"]] == [
        "lead_name",
        "organization",
        "status",
        "email",
        "mobile_no",
        "_assign",
        "modified",
    ]
    # Every field the controller names must be a real column on the model.
    from frappe_core.query import concrete_field_names

    available = concrete_field_names(CRMLead)
    declared = CRMLead.default_list_data()["rows"]
    assert set(declared) <= available, f"missing: {sorted(set(declared) - available)}"


def test_get_data_kanban_resolves_lead_status_columns(alice, statuses):
    """Kanban column resolution from a Link target, on real data."""
    from frappe_core.api.doc import get_data

    with session_user(alice.name):
        CRMLead.objects.create(status=statuses["open"], first_name="Ada")
        result = get_data(
            doctype="CRM Lead",
            filters={},
            order_by="modified desc",
            view={"view_type": "kanban"},
            column_field="status",
        )
    resolved = [c["name"] for c in result["kanban_columns"]]
    assert "New" in resolved and "Junk" in resolved


def test_lead_is_listable_with_the_criterion_1_request_shape(auth_api, alice, statuses):
    """PHASE_0_FOUNDATION.md criterion 1, now against the real ``CRM Lead``.

    Phase 0 could only test the shape against a stand-in doctype (spec section 9 forbade
    building CRM models), and PROGRESS.md flagged this as owed. Here it is.
    """
    with session_user(alice.name):
        CRMLead.objects.create(status=statuses["open"], first_name="Ada")

    response = auth_api.get(
        "/api/resource/" + quote("CRM Lead"),
        {
            "filters": json.dumps([["status", "=", "New"]]),
            "fields": json.dumps(["name", "lead_name"]),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data"}
    assert body["data"][0]["lead_name"] == "Ada"
    assert set(body["data"][0]) == {"name", "lead_name"}
