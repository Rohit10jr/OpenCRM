"""Facebook lead sync — idempotency, ownership, and the failure log.

Two acceptance criteria live here and both are easy to fail invisibly:

* *"Lead sync is idempotent — re-running creates no duplicates"* (`PHASE_7_INTEGRATIONS.md`
  §4). There are two layers, and the outer one hides a broken inner one during normal
  operation. Tested separately for that reason.
* Every created lead has a `lead_owner`. `AS_BUILT.md` §4: without it the record is
  invisible to everyone but a manager, with no error — and that section names integrations
  specifically.

Graph is stubbed at `crm_app.integrations.facebook.graph`. Nothing here talks to Facebook.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from crm_app.integrations.facebook import sync
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

FORM_ID = "fb-form-1"


@pytest.fixture
def fb_on(settings):
    settings.ENABLE_FACEBOOK_LEAD_SYNC = True


@pytest.fixture
def lead_status(administrator):
    from crm_app.models import CRMLeadStatus

    with session_user(administrator.name):
        status, _ = CRMLeadStatus.objects.get_or_create(
            lead_status="New", defaults={"type": "Open"}
        )
    return status


@pytest.fixture
def source(administrator, lead_status):
    """A page, a form with two mapped questions, and an enabled source."""
    from crm_app.models import (
        FacebookLeadForm,
        FacebookLeadFormQuestion,
        FacebookPage,
        LeadSyncSource,
    )

    with session_user(administrator.name):
        page = FacebookPage.objects.create(
            id="fb-page-1", page_name="Acme", access_token="page-token"
        )
        form = FacebookLeadForm.objects.create(id=FORM_ID, form_name="Contact us", page=page)
        FacebookLeadFormQuestion.objects.create(
            parent_form=form, idx=1, key="email", mapped_to_crm_field="email"
        )
        FacebookLeadFormQuestion.objects.create(
            parent_form=form, idx=2, key="full_name", mapped_to_crm_field="first_name"
        )
        # A question nobody mapped — dropped, per `facebook.py:94-96`.
        FacebookLeadFormQuestion.objects.create(
            parent_form=form, idx=3, key="how_did_you_hear", mapped_to_crm_field=""
        )
        record = LeadSyncSource.objects.create(
            name="acme-contact-us",
            type="Facebook",
            enabled=True,
            access_token="source-token",
            background_sync_frequency="Every 5 Minutes",
            facebook_page=page,
            facebook_lead_form=form,
        )
    return record


def _lead(lead_id="fb-lead-1", email="ada@example.com", name="Ada Lovelace"):
    return {
        "id": lead_id,
        "created_time": "2026-08-20T10:00:00+0000",
        "field_data": [
            {"name": "email", "values": [email]},
            {"name": "full_name", "values": [name]},
            {"name": "how_did_you_hear", "values": ["A friend"]},
        ],
    }


def _syncer(source, leads):
    engine = sync.FacebookSyncSource("source-token", FORM_ID, source=source)
    return engine, patch.object(sync.graph, "get_paged", return_value=leads)


# ---------------------------------------------------------------------------
# Idempotency — layer 2, the guarantee
# ---------------------------------------------------------------------------


def test_a_lead_is_created(fb_on, source):
    from crm_app.models import CRMLead

    engine, stub = _syncer(source, [_lead()])
    with stub:
        result = engine.sync()

    assert result["created"] == 1
    lead = CRMLead.objects.get(facebook_lead_id="fb-lead-1")
    assert lead.email == "ada@example.com"
    assert lead.first_name == "Ada Lovelace"
    # `source` is a real FK here, not the Link *string* upstream writes.
    assert lead.source_id == "Facebook"


def test_re_running_the_same_batch_creates_no_duplicates(fb_on, source):
    """§4's criterion, tested against the layer that actually guarantees it.

    `last_synced_at` is deliberately not relied on here — the batch is replayed verbatim,
    which is what a retry after a partial failure looks like.
    """
    from crm_app.models import CRMLead

    engine, stub = _syncer(source, [_lead()])
    with stub:
        engine.sync()
        second = engine.sync()

    assert second["duplicate"] == 1
    assert second["created"] == 0
    assert CRMLead.objects.filter(facebook_lead_id="fb-lead-1").count() == 1


def test_the_duplicate_check_is_scoped_to_the_form(fb_on, source, administrator):
    """`facebook.py:136` adds `facebook_form_id` to the filter *"only for this campaign"*.

    The same person answering two different campaigns is two leads, and merging them would
    lose which campaign produced which.
    """
    from crm_app.models import CRMLead, FacebookLeadForm, FacebookLeadFormQuestion

    with session_user(administrator.name):
        other = FacebookLeadForm.objects.create(id="fb-form-2", form_name="Webinar")
        FacebookLeadFormQuestion.objects.create(
            parent_form=other, idx=1, key="email", mapped_to_crm_field="email"
        )
        FacebookLeadFormQuestion.objects.create(
            parent_form=other, idx=2, key="full_name", mapped_to_crm_field="first_name"
        )

    engine, stub = _syncer(source, [_lead()])
    with stub:
        engine.sync()

    other_engine = sync.FacebookSyncSource("source-token", "fb-form-2", source=source)
    with patch.object(sync.graph, "get_paged", return_value=[_lead(lead_id="fb-lead-2")]):
        result = other_engine.sync()

    assert result["created"] == 1
    assert CRMLead.objects.filter(email="ada@example.com").count() == 2


def test_a_duplicate_is_logged_rather_than_raised(fb_on, source):
    """A duplicate is an expected outcome of a re-run, not a failure."""
    from crm_app.models import FailedLeadSyncLog

    engine, stub = _syncer(source, [_lead()])
    with stub:
        engine.sync()
        engine.sync()

    log = FailedLeadSyncLog.objects.filter(type="Duplicate").first()
    assert log is not None
    assert json.loads(log.lead_data)["id"] == "fb-lead-1"


def test_a_lead_missing_an_optional_answer_does_not_crash(fb_on, source):
    """Facebook omits unanswered optional questions.

    Upstream builds the duplicate filter from `field_mapping.values()` and would raise
    `KeyError` on such a payload (`facebook.py:135`). `UPSTREAM_BUGS` #30.
    """
    from crm_app.models import CRMLead

    partial = {
        "id": "fb-lead-partial",
        "field_data": [{"name": "email", "values": ["solo@example.com"]}],
    }
    engine, stub = _syncer(source, [partial])
    with stub:
        result = engine.sync()

    assert result["created"] == 1
    assert CRMLead.objects.filter(email="solo@example.com").exists()


# ---------------------------------------------------------------------------
# Idempotency — layer 1, the narrowing
# ---------------------------------------------------------------------------


def test_the_first_sync_asks_for_everything(fb_on, source):
    captured = {}

    def fake(endpoint, params, **kwargs):
        captured.update(params)
        return []

    with patch.object(sync.graph, "get_paged", fake):
        sync.FacebookSyncSource("t", FORM_ID, source=source).sync()

    assert "filtering" not in captured


def test_a_later_sync_asks_only_for_new_leads(fb_on, source):
    """`facebook.py:75-79` — `time_created > last_synced_at`."""
    engine, stub = _syncer(source, [_lead()])
    with stub:
        engine.sync()

    captured = {}

    def fake(endpoint, params, **kwargs):
        captured.update(params)
        return []

    source.refresh_from_db()
    with patch.object(sync.graph, "get_paged", fake):
        sync.FacebookSyncSource("t", FORM_ID, source=source).sync()

    filtering = json.loads(captured["filtering"])
    assert filtering[0]["field"] == "time_created"
    assert filtering[0]["operator"] == "GREATER_THAN"


def test_the_timestamp_is_recorded_after_a_sync(fb_on, source):
    assert source.last_synced_at is None
    engine, stub = _syncer(source, [_lead()])
    with stub:
        engine.sync()

    source.refresh_from_db()
    assert source.last_synced_at is not None


def test_recording_the_timestamp_does_not_restamp_modified_by(fb_on, source, alice):
    """It runs in a worker; `save()` would put the worker's identity in `modified_by`."""
    from crm_app.models import LeadSyncSource

    before = LeadSyncSource.objects.values_list("modified_by", flat=True).get(pk=source.pk)
    engine, stub = _syncer(source, [_lead()])
    with session_user(alice.name), stub:
        engine.sync()

    after = LeadSyncSource.objects.values_list("modified_by", flat=True).get(pk=source.pk)
    assert after == before


# ---------------------------------------------------------------------------
# Ownership — the invisible-record trap
# ---------------------------------------------------------------------------


def test_every_synced_lead_has_an_owner(fb_on, source):
    """`AS_BUILT.md` §4 names integrations specifically: a lead with no `lead_owner` is
    invisible to everyone but a manager, with no error at all.

    Upstream sets nothing (`facebook.py:52-59`), so upstream's Facebook leads are invisible
    to every Sales User. `UPSTREAM_BUGS` #29 — diverged, because reproducing it means the
    feature does not work.
    """
    from crm_app.models import CRMLead

    engine, stub = _syncer(source, [_lead()])
    with stub:
        engine.sync()

    lead = CRMLead.objects.get(facebook_lead_id="fb-lead-1")
    assert lead.lead_owner_id == sync.DEFAULT_LEAD_OWNER
    assert lead.lead_owner_id


def test_a_synced_lead_is_visible_to_a_manager(fb_on, source, administrator):
    from frappe_core.query import base_queryset

    engine, stub = _syncer(source, [_lead()])
    with stub:
        engine.sync()

    visible = base_queryset("CRM Lead", administrator.name).values_list(
        "facebook_lead_id", flat=True
    )
    assert "fb-lead-1" in set(visible)


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_one_bad_lead_does_not_stop_the_batch(fb_on, source):
    """Upstream catches per lead rather than per sync, and this is why."""
    from crm_app.models import CRMLead

    good_one = _lead("fb-1", "one@example.com", "One")
    bad = {"id": "fb-bad", "field_data": "not-a-list"}
    good_two = _lead("fb-2", "two@example.com", "Two")

    engine, stub = _syncer(source, [good_one, bad, good_two])
    with stub:
        result = engine.sync()

    assert result["created"] == 2
    assert result["failed"] == 1
    assert CRMLead.objects.filter(facebook_lead_id__in=["fb-1", "fb-2"]).count() == 2


def test_a_failure_is_logged_with_its_traceback(fb_on, source):
    from crm_app.models import FailedLeadSyncLog

    engine, stub = _syncer(source, [{"id": "fb-bad", "field_data": "not-a-list"}])
    with stub:
        engine.sync()

    log = FailedLeadSyncLog.objects.get(type="Failure")
    assert log.traceback
    assert log.source_id == source.pk


def test_an_unmapped_question_is_dropped(fb_on, source):
    """`facebook.py:94-96` — a question with no `mapped_to_crm_field` has nowhere to go."""
    from crm_app.models import CRMLead

    engine, stub = _syncer(source, [_lead()])
    with stub:
        engine.sync()

    lead = CRMLead.objects.get(facebook_lead_id="fb-lead-1")
    assert "A friend" not in (lead.first_name or "")


# ---------------------------------------------------------------------------
# The scheduled tasks phase 5 registered
# ---------------------------------------------------------------------------


def test_the_tasks_are_no_ops_with_the_flag_off(db, settings):
    from crm_app.tasks import sync_leads_5_minutes

    settings.ENABLE_FACEBOOK_LEAD_SYNC = False
    assert "skipped" in sync_leads_5_minutes()


def test_a_task_syncs_the_sources_on_its_schedule(fb_on, source):
    from crm_app.tasks import sync_leads_5_minutes

    with patch.object(sync.graph, "get_paged", return_value=[_lead()]):
        result = sync_leads_5_minutes()

    assert str(source.pk) in result["sources"]
    assert result["sources"][str(source.pk)]["created"] == 1


def test_a_task_ignores_sources_on_another_schedule(fb_on, source):
    from crm_app.tasks import sync_leads_daily

    with patch.object(sync.graph, "get_paged", return_value=[_lead()]):
        result = sync_leads_daily()

    assert result["sources"] == {}


def test_a_disabled_source_is_not_synced(fb_on, source, administrator):
    from crm_app.models import LeadSyncSource
    from crm_app.tasks import sync_leads_5_minutes

    LeadSyncSource.objects.filter(pk=source.pk).update(enabled=False)

    with patch.object(sync.graph, "get_paged", return_value=[_lead()]):
        result = sync_leads_5_minutes()

    assert result["sources"] == {}


def test_one_broken_source_does_not_stop_the_others(fb_on, source, administrator):
    """A bad token on one form must not silently stop every other form on the schedule."""
    from crm_app.models import FacebookLeadForm, LeadSyncSource

    with session_user(administrator.name):
        other_form = FacebookLeadForm.objects.create(id="fb-form-3", form_name="Other")
        LeadSyncSource.objects.create(
            name="broken",
            type="Facebook",
            enabled=True,
            access_token="bad",
            background_sync_frequency="Every 5 Minutes",
            facebook_lead_form=other_form,
        )

    from crm_app.tasks import sync_leads_5_minutes

    def fake(endpoint, params, **kwargs):
        if "fb-form-3" in endpoint:
            raise sync.graph.FacebookApiError("Invalid OAuth access token")
        return [_lead()]

    with patch.object(sync.graph, "get_paged", fake):
        result = sync_leads_5_minutes()

    assert result["sources"][str(source.pk)]["created"] == 1
    assert "error" in result["sources"]["broken"]


def test_the_frequency_map_covers_every_registered_task():
    """A typo here would be a source that silently never syncs, so it is a KeyError
    instead."""
    from crm_app.models.lead_syncing import SYNC_FREQUENCY_CHOICES
    from crm_app.tasks import FREQUENCY_LABELS

    assert set(FREQUENCY_LABELS.values()) == {c[0] for c in SYNC_FREQUENCY_CHOICES}


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def test_both_access_tokens_are_encrypted_at_rest(fb_on, source):
    """**Stricter than upstream** for the page token, which is plain `Small Text` there.

    A page access token reads every lead the page has collected and can post as the page.
    `UPSTREAM_BUGS` #28.
    """
    from crm_app.models import FacebookPage, LeadSyncSource

    stored_source = LeadSyncSource.objects.get(pk=source.pk)
    assert stored_source.access_token != "source-token"
    assert stored_source.get_password("access_token") == "source-token"

    page = FacebookPage.objects.get(pk="fb-page-1")
    assert page.access_token != "page-token"
    assert page.get_password("access_token") == "page-token"


def test_neither_token_is_selectable(fb_on):
    from crm_app.models import FacebookPage, LeadSyncSource
    from frappe_core.field_security import sensitive_fields

    assert "access_token" in sensitive_fields(LeadSyncSource)
    assert "access_token" in sensitive_fields(FacebookPage)


def test_the_failure_log_is_manager_only(fb_on, source, alice, administrator):
    """It holds the raw Graph payload — a real person's name, email and phone — for a lead
    that never became a CRM record and has no other rule protecting it."""
    from frappe_core.query import base_queryset

    engine, stub = _syncer(source, [{"id": "fb-bad", "field_data": "not-a-list"}])
    with stub:
        engine.sync()

    assert base_queryset("Failed Lead Sync Log", alice.name).count() == 0
    assert base_queryset("Failed Lead Sync Log", administrator.name).count() == 1


def test_the_sync_source_is_manager_only(fb_on, source, alice):
    from frappe_core.query import base_queryset

    assert base_queryset("Lead Sync Source", alice.name).count() == 0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_two_enabled_sources_cannot_share_a_form(fb_on, source, administrator):
    """`lead_sync_source.py:34-47`. Both would fetch the same leads and race to insert
    them — caught by the duplicate check, but as a stream of logs rather than as the
    configuration error it is. Message preserved verbatim."""
    from crm_app.models import LeadSyncSource
    from frappe_core.exceptions import ValidationError

    with session_user(administrator.name):
        clash = LeadSyncSource(
            name="second",
            type="Facebook",
            enabled=True,
            facebook_lead_form_id=FORM_ID,
        )
        with pytest.raises(ValidationError) as excinfo:
            clash.validate_same_fb_form_active()

    assert "already enabled for this Facebook Lead Form" in str(excinfo.value)


def test_a_disabled_source_may_share_a_form(fb_on, source, administrator):
    from crm_app.models import LeadSyncSource

    with session_user(administrator.name):
        second = LeadSyncSource(
            name="second", type="Facebook", enabled=False, facebook_lead_form_id=FORM_ID
        )
        second.validate_same_fb_form_active()  # does not raise
