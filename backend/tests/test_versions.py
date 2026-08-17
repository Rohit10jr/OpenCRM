"""A2 - field-change history in the timeline.

The gap phase 3 recorded: a deal's value could change with nothing recording who did it.
Upstream builds these entries from the framework's ``Version`` doctype and records
**every** field, description edits included; this port records a declared list per model
(:attr:`CRMLead.TRACKED_FIELDS`).

That narrowing is a product decision, and these tests pin both halves of it - the fields
that *are* tracked, and the deliberate exclusions - so neither is later mistaken for a
bug and "fixed".
"""

import pytest

from crm_app.models import CRMDeal, CRMDealStatus, CRMLead, CRMLeadStatus
from frappe_core.session import session_user
from frappe_core.versions import Version, versions_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def statuses(administrator):
    with session_user(administrator.name):
        return {
            "lead_new": CRMLeadStatus.objects.create(lead_status="New", type="Open"),
            "lead_next": CRMLeadStatus.objects.create(lead_status="Contacted", type="Open"),
            "deal": CRMDealStatus.objects.create(deal_status="Qualification", type="Open"),
        }


@pytest.fixture
def deal(alice, statuses):
    with session_user(alice.name):
        return CRMDeal.objects.create(
            deal_owner=alice, status=statuses["deal"], deal_value=50000
        )


def _changes(doc):
    return [c for v in versions_for(doc.get_doctype(), doc.pk) for c in v.changes()]


# --- what gets recorded ---------------------------------------------------------------


def test_creating_a_record_writes_no_version(alice, statuses):
    """The timeline already carries a "created" entry, and upstream's diff against a
    non-existent prior document is empty too."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=alice, status=statuses["lead_new"])

    assert versions_for("CRM Lead", lead.pk) == []


def test_changing_the_deal_value_is_recorded(alice, deal):
    """The question this whole feature exists to answer: who raised it to 80k?"""
    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.deal_value = 80000
        reloaded.save()

    changes = _changes(reloaded)
    assert len(changes) == 1
    field, old, new = changes[0]
    assert field == "deal_value"
    assert str(old).startswith("50000")
    assert str(new).startswith("80000")


def test_the_version_records_who_made_the_change(alice, bob, deal):
    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(bob.name):
        reloaded.deal_value = 90000
        reloaded.save()

    assert versions_for("CRM Deal", deal.pk)[0].owner_id == bob.name


def test_changing_the_owner_is_recorded(alice, bob, deal):
    """"Who took this deal off Sarah?" - the second question managers ask."""
    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.deal_owner = bob
        reloaded.save()

    assert ["deal_owner", alice.name, bob.name] in _changes(reloaded)


def test_several_fields_in_one_save_share_a_version(alice, deal):
    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.deal_value = 70000
        reloaded.probability = 75
        reloaded.save()

    versions = versions_for("CRM Deal", deal.pk)
    assert len(versions) == 1, "one save should write one row"
    assert {c[0] for c in versions[0].changes()} == {"deal_value", "probability"}


def test_successive_saves_each_write_a_row(alice, deal):
    for value in (60000, 70000):
        reloaded = CRMDeal.objects.get(pk=deal.pk)
        with session_user(alice.name):
            reloaded.deal_value = value
            reloaded.save()

    assert len(versions_for("CRM Deal", deal.pk)) == 2


def test_two_saves_in_one_request_diff_against_the_last_write(alice, deal):
    """The in-memory snapshot has to refresh after each save, or the second save
    re-reports the first change."""
    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.deal_value = 60000
        reloaded.save()
        reloaded.deal_value = 70000
        reloaded.save()

    changes = _changes(reloaded)
    assert [str(c[1])[:5] for c in changes] == ["50000", "60000"]


# --- what is deliberately not recorded ------------------------------------------------


def test_saving_without_changing_anything_tracked_writes_nothing(alice, deal):
    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.first_name = "Renamed"
        reloaded.save()

    assert versions_for("CRM Deal", deal.pk) == []


def test_status_is_not_double_recorded(alice, statuses):
    """Status reaches the timeline through ``CRM Status Change Log``, which also carries
    the duration spent in each status. Tracking it here too would show every transition
    twice."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(
            first_name="Ada", lead_owner=alice, status=statuses["lead_new"]
        )

    reloaded = CRMLead.objects.get(pk=lead.pk)
    with session_user(alice.name):
        reloaded.status = statuses["lead_next"]
        reloaded.save()

    assert not [c for c in _changes(reloaded) if c[0] == "status"]


def test_an_untracked_field_is_not_recorded(alice, deal):
    """**Upstream records this and we deliberately do not.**

    ``track_changes=1`` on CRM Deal means Frappe logs every field, so upstream's timeline
    shows description edits. Tracking them here would put an entry in the timeline every
    time somebody fixes a typo. Widening ``TRACKED_FIELDS`` is the one-line change if
    that is ever wanted.
    """
    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.mobile_no = "555-9999"
        reloaded.save()

    assert versions_for("CRM Deal", deal.pk) == []


def test_a_model_with_no_tracked_fields_writes_nothing(alice, administrator):
    """Most doctypes opt out entirely - the default is no history."""
    from crm_app.models import CRMOrganization

    with session_user(administrator.name):
        org = CRMOrganization.objects.create(organization_name="Acme Corp")
    reloaded = CRMOrganization.objects.get(pk=org.pk)
    with session_user(alice.name):
        reloaded.website = "changed.example"
        reloaded.save()

    assert Version.objects.filter(ref_doctype="CRM Organization").count() == 0


# --- the timeline ---------------------------------------------------------------------


def test_the_change_reaches_the_activity_timeline(alice, deal):
    from crm_app.api.activities import _field_change_activities

    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.deal_value = 80000
        reloaded.save()

    entries = _field_change_activities("CRM Deal", deal.pk)
    assert len(entries) == 1
    assert entries[0]["activity_type"] == "changed"
    assert entries[0]["data"]["field"] == "deal_value"
    assert entries[0]["owner"] == alice.name


def test_empty_to_set_is_reported_as_added(alice, deal):
    """Upstream's ``added`` variant (``crm/api/activities.py:92-95``) - the UI words it
    differently from a change."""
    from crm_app.api.activities import _field_change_activities

    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.probability = 60
        reloaded.save()

    entry = next(e for e in _field_change_activities("CRM Deal", deal.pk) if e["data"]["field"] == "probability")
    assert entry["activity_type"] == "added"
    assert "old_value" not in entry["data"]
