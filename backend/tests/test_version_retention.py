"""What `clear_old_versions` prunes, and - more importantly - what it must never touch.

The job's name invites a general "delete old audit rows" implementation. That would
silently erase the timeline: `Version` rows for Leads and Deals *are* the field-change
history `get_activities` renders, and upstream keeps them forever.

Upstream prunes exactly one doctype - `CRM View Settings` - because saved views are edited
constantly and nobody reads the history of a list view. This file pins that narrowness so
a future "this job does nothing, let me make it useful" change fails loudly.
"""

import datetime

import pytest
from django.utils import timezone

from crm_app.models import CRMDeal, CRMDealStatus
from crm_app.tasks import VERSION_CHURN_DOCTYPE, VERSION_RETENTION_DAYS, clear_old_versions
from frappe_core.session import session_user
from frappe_core.versions import Version, versions_for

pytestmark = pytest.mark.django_db


def _aged_version(ref_doctype: str, docname: str, days_old: int) -> Version:
    """A version row backdated past the retention window.

    `creation` is `auto_now_add`-ish, so it has to be rewritten with an UPDATE rather
    than passed to `create()`.
    """
    row = Version.objects.create(ref_doctype=ref_doctype, docname=docname, data="{}")
    Version.objects.filter(pk=row.pk).update(
        creation=timezone.now() - datetime.timedelta(days=days_old)
    )
    return row


# --- what it prunes ----------------------------------------------------------------------


def test_old_saved_view_versions_are_deleted():
    _aged_version(VERSION_CHURN_DOCTYPE, "42", days_old=VERSION_RETENTION_DAYS + 1)

    assert clear_old_versions() == 1
    assert not Version.objects.filter(ref_doctype=VERSION_CHURN_DOCTYPE).exists()


def test_recent_saved_view_versions_are_kept():
    _aged_version(VERSION_CHURN_DOCTYPE, "42", days_old=VERSION_RETENTION_DAYS - 1)

    assert clear_old_versions() == 0
    assert Version.objects.filter(ref_doctype=VERSION_CHURN_DOCTYPE).exists()


def test_the_window_is_configurable():
    _aged_version(VERSION_CHURN_DOCTYPE, "42", days_old=5)

    assert clear_old_versions(days=30) == 0, "5 days old, 30-day window - must survive"
    assert clear_old_versions(days=3) == 1


# --- what it must never prune -------------------------------------------------------------


@pytest.mark.parametrize("ref_doctype", ["CRM Lead", "CRM Deal"])
def test_lead_and_deal_history_is_never_pruned(ref_doctype):
    """**The guard this file exists for.**

    Ancient on purpose: a year past any plausible retention window. If someone widens the
    job to prune "old versions" generally, this is what fails, and the failure names the
    timeline rather than leaving them to discover it from a support ticket.
    """
    _aged_version(ref_doctype, "CRM-DEAL-2020-00001", days_old=365)

    assert clear_old_versions() == 0
    assert Version.objects.filter(ref_doctype=ref_doctype).count() == 1


def test_the_timeline_survives_a_prune(administrator, bob):
    """End to end rather than by row count: edit a deal, age everything past the window,
    run the job, and the field-change history is still there to render."""
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(status=status, deal_owner=bob, deal_value=100)
        deal.deal_value = 250000
        deal.save()

    Version.objects.all().update(creation=timezone.now() - datetime.timedelta(days=365))
    clear_old_versions()

    changes = [
        tuple(c) for version in versions_for("CRM Deal", deal.name) for c in version.changes()
    ]
    assert ("deal_value", 100, 250000) in changes


def test_it_deletes_nothing_today_because_we_do_not_track_saved_views(administrator):
    """The reason the job is idle, pinned as a fact rather than left in a comment.

    Not "because `Version` is unmodelled" - that was the old docstring and it was stale.
    We simply never create the rows it targets. If someone later adds TRACKED_FIELDS to
    `CRMViewSettings`, this test fails and points at the decision in
    specs/VERSION_HISTORY.md rather than letting churn appear unremarked.
    """
    from crm_app.models import CRMViewSettings

    assert not getattr(CRMViewSettings, "TRACKED_FIELDS", ())


# --- what we track, stated explicitly ------------------------------------------------------


def test_the_tracked_set_is_exactly_what_we_intend():
    """Upstream tracks six doctypes and displays two. We track three: the two the timeline
    renders, plus telephony credentials - a change to those otherwise leaves no trace
    anywhere in this port. See specs/VERSION_HISTORY.md."""
    from crm_app.models import CRMTwilioSettings
    from frappe_core import registry

    tracked = {
        dt
        for dt in registry.all_doctypes()
        if getattr(registry.get_entry(dt).model, "TRACKED_FIELDS", ())
    }
    assert tracked == {"CRM Lead", "CRM Deal", "CRM Twilio Settings"}
    assert "enabled" in CRMTwilioSettings.TRACKED_FIELDS


def test_a_telephony_credential_change_leaves_a_trace(administrator):
    """Item 5. A4 restricted *who* may change these; this records *that* one did."""
    from crm_app.models import CRMTwilioSettings

    with session_user(administrator.name):
        settings = CRMTwilioSettings.objects.create(account_sid="AC-old", api_key="SK-old")
        settings.account_sid = "AC-new"
        settings.save()

    changes = [
        tuple(c)
        for version in versions_for("CRM Twilio Settings", settings.name)
        for c in version.changes()
    ]
    assert ("account_sid", "AC-old", "AC-new") in changes


def test_the_secret_itself_never_enters_the_version_row(administrator):
    """`api_secret` and `auth_token` are not tracked, so no version row can carry them -
    the audit question is *that* a credential changed, not what it used to be. Recording
    the old value would put a secret in a second table, outside `SENSITIVE_FIELDS` and
    outside the encryption."""
    from crm_app.models import CRMTwilioSettings

    with session_user(administrator.name):
        settings = CRMTwilioSettings.objects.create(api_secret="old-secret")
        settings.api_secret = "new-secret"
        settings.save()

    blob = " ".join(v.data for v in Version.objects.all())
    assert "old-secret" not in blob
    assert "new-secret" not in blob
