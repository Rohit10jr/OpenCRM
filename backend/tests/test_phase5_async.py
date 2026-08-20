"""Phase 5 — Celery tasks and the Beat schedule.

Covers `PHASE_5_ASYNC.md` §5. Nothing here needs a running worker, a broker or an SMTP
server: `CELERY_TASK_ALWAYS_EAGER` runs tasks inline and the `locmem` backend captures
mail, both set in `config/settings/test.py` (RUNBOOK, "Tests that would need external
services").

The most important test is :func:`test_no_sla_job_exists_in_the_beat_schedule`. It is
there because the *absence* of a job is the thing to protect: `PHASE_5_ASYNC.md` §4
establishes from source that SLA is computed on write, and a well-meaning later agent
adding a sweep would make our list views disagree with upstream's for the same data.
"""

from __future__ import annotations

import datetime

import pytest
from django.core import mail
from django.utils import timezone

from config.celery import app as celery_app
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def lead(alice, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        return CRMLead.objects.create(first_name="Ada", lead_owner=alice, status=status)


# ---------------------------------------------------------------------------
# The Beat schedule
# ---------------------------------------------------------------------------


def test_beat_schedule_matches_hooks_py():
    """`PHASE_5_ASYNC.md` §1 — one entry per `crm/hooks.py:scheduler_events` row."""
    tasks = {entry["task"] for entry in celery_app.conf.beat_schedule.values()}
    assert tasks == {
        "crm.expire_invitations",
        "crm.clear_old_versions",
        "crm.flush_expired_tokens",
        "crm.sync_leads_daily",
        "crm.sync_leads_hourly",
        "crm.sync_leads_monthly",
        "crm.sync_leads_5_minutes",
        "crm.sync_leads_10_minutes",
        "crm.sync_leads_15_minutes",
    }


def test_no_sla_job_exists_in_the_beat_schedule():
    """`PHASE_5_ASYNC.md` §4 — the absence is the point.

    Upstream computes SLA on write; ``hooks.py`` has no SLA scheduler entry at all. A
    periodic sweep would make a lead's ``sla_status`` differ from upstream's for
    identical data, so this asserts nothing SLA-shaped has crept in.
    """
    haystack = " ".join(
        [name for name in celery_app.conf.beat_schedule]
        + [entry["task"] for entry in celery_app.conf.beat_schedule.values()]
    ).lower()
    for forbidden in ("sla", "service_level", "response_by", "breach"):
        assert forbidden not in haystack, f"an SLA-shaped job appeared: {forbidden}"


def test_telemetry_is_not_scheduled():
    """`PHASE_5_ASYNC.md` §1 marks ``capture_feature_state`` **skip** — it reports to
    Frappe's analytics, which is not this deployment's business."""
    tasks = " ".join(e["task"] for e in celery_app.conf.beat_schedule.values())
    assert "telemetry" not in tasks
    assert "capture_feature_state" not in tasks


def test_lead_sync_jobs_use_the_long_queue():
    """Upstream runs them on RQ's ``long`` queue (``hooks.py:223-231``)."""
    for name, entry in celery_app.conf.beat_schedule.items():
        if "sync_leads" in entry["task"]:
            assert entry["options"]["queue"] == "long", name


def test_cron_intervals_match_the_source():
    """``*/5``, ``*/10``, ``*/15`` (``hooks.py:226-230``)."""
    by_task = {e["task"]: e["schedule"] for e in celery_app.conf.beat_schedule.values()}
    for task, expected in (
        ("crm.sync_leads_5_minutes", "*/5"),
        ("crm.sync_leads_10_minutes", "*/10"),
        ("crm.sync_leads_15_minutes", "*/15"),
    ):
        assert str(by_task[task]._orig_minute) == expected


def test_tasks_run_eagerly_in_tests():
    """Without this the rest of the file would silently assert nothing."""
    from django.conf import settings

    assert settings.CELERY_TASK_ALWAYS_EAGER is True


# ---------------------------------------------------------------------------
# expire_invitations
# ---------------------------------------------------------------------------


def _invitation(email, *, age_days=0, status="Pending", administrator=None):
    from crm_app.models import CRMInvitation

    with session_user(administrator.name if administrator else "Administrator"):
        invitation = CRMInvitation.objects.create(
            email=email, role="Sales User", status=status, key=f"k-{email}"
        )
    if age_days:
        CRMInvitation.objects.filter(pk=invitation.pk).update(
            creation=timezone.now() - datetime.timedelta(days=age_days)
        )
    return invitation


def test_expire_invitations_expires_only_stale_pending_ones(administrator):
    """``crm_invitation.py:105-116`` — pending, older than 3 days."""
    from crm_app.models import CRMInvitation
    from crm_app.tasks import expire_invitations

    fresh = _invitation("fresh@example.com", age_days=1, administrator=administrator)
    stale = _invitation("stale@example.com", age_days=5, administrator=administrator)

    assert expire_invitations() == 1
    assert CRMInvitation.objects.get(pk=fresh.pk).status == "Pending"
    assert CRMInvitation.objects.get(pk=stale.pk).status == "Expired"


def test_expire_invitations_leaves_accepted_ones_alone(administrator):
    from crm_app.models import CRMInvitation
    from crm_app.tasks import expire_invitations

    accepted = _invitation(
        "done@example.com", age_days=10, status="Accepted", administrator=administrator
    )
    expire_invitations()
    assert CRMInvitation.objects.get(pk=accepted.pk).status == "Accepted"


def test_expire_invitations_is_idempotent(administrator):
    """`PHASE_5_ASYNC.md` §5 — a retry must not double-apply."""
    from crm_app.tasks import expire_invitations

    _invitation("stale@example.com", age_days=5, administrator=administrator)
    assert expire_invitations() == 1
    assert expire_invitations() == 0


# ---------------------------------------------------------------------------
# flush_expired_tokens — §2a
# ---------------------------------------------------------------------------


def test_flush_expired_tokens_removes_only_expired_ones(alice):
    """It must never log a live session out."""
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from rest_framework_simplejwt.tokens import RefreshToken

    from crm_app.tasks import flush_expired_tokens

    RefreshToken.for_user(alice)
    live = OutstandingToken.objects.count()
    assert live >= 1

    assert flush_expired_tokens() == 0
    assert OutstandingToken.objects.count() == live


def test_flush_expired_tokens_deletes_an_expired_one(alice):
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
    from rest_framework_simplejwt.tokens import RefreshToken

    from crm_app.tasks import flush_expired_tokens

    RefreshToken.for_user(alice)
    OutstandingToken.objects.update(expires_at=timezone.now() - datetime.timedelta(days=1))

    assert flush_expired_tokens() >= 1
    assert OutstandingToken.objects.count() == 0


# ---------------------------------------------------------------------------
# Lead sync — registered, no-op behind a flag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "task_name",
    [
        "sync_leads_daily", "sync_leads_hourly", "sync_leads_monthly",
        "sync_leads_5_minutes", "sync_leads_10_minutes", "sync_leads_15_minutes",
    ],
)
def test_lead_sync_tasks_are_registered_and_no_op(task_name, settings):
    """`PHASE_5_ASYNC.md` §1 — registered now, no-op behind the flag."""
    import crm_app.tasks as tasks

    settings.ENABLE_FACEBOOK_LEAD_SYNC = False
    result = getattr(tasks, task_name)()
    assert "skipped" in result


def test_lead_sync_raises_rather_than_lying_when_the_flag_is_on(settings):
    """A flag that is on with nothing behind it is a config error, not a silent success."""
    from crm_app.tasks import sync_leads_daily

    settings.ENABLE_FACEBOOK_LEAD_SYNC = True
    with pytest.raises(NotImplementedError):
        sync_leads_daily()


# ---------------------------------------------------------------------------
# update_modified_background — §2, and the reason it exists
# ---------------------------------------------------------------------------


def test_commenting_bumps_modified_so_the_lead_rises(alice, lead):
    """``crm/utils/__init__.py:238-253``.

    The default list sort is ``modified desc``, so this is what puts a lead at the top
    when someone comments on it. `PHASE_5_ASYNC.md` §2: *"Skip it and the UI feels broken
    in a way that is hard to trace back."*
    """
    from crm_app.models import CRMLead
    from frappe_platform.models import Comment

    before = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    with session_user(alice.name):
        Comment.objects.create(
            comment_type="Comment", reference_doctype="CRM Lead",
            reference_name=lead.pk, content="Called them",
        )
    after = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    assert after > before


def test_the_bump_does_not_rewrite_modified_by(alice, bob, lead):
    """The whole reason it is a bare UPDATE.

    ``save()`` would re-stamp ``modified_by`` with whoever the worker runs as, quietly
    rewriting authorship. Upstream passes ``update_modified=False`` for exactly this.
    """
    from crm_app.models import CRMLead
    from frappe_platform.models import Comment

    before = CRMLead.objects.values_list("modified_by", flat=True).get(pk=lead.pk)
    with session_user(bob.name):
        Comment.objects.create(
            comment_type="Comment", reference_doctype="CRM Lead",
            reference_name=lead.pk, content="Someone else's note",
        )
    after = CRMLead.objects.values_list("modified_by", flat=True).get(pk=lead.pk)
    assert after == before


def test_only_leads_and_deals_bump(alice, administrator):
    """``crm/utils/__init__.py:165`` — the guard is a two-item allowlist."""
    from crm_app.models import CRMOrganization
    from frappe_platform.models import Comment

    with session_user(administrator.name):
        org = CRMOrganization.objects.create(organization_name="Acme")
    before = CRMOrganization.objects.values_list("modified", flat=True).get(pk=org.pk)

    with session_user(alice.name):
        Comment.objects.create(
            comment_type="Comment", reference_doctype="CRM Organization",
            reference_name=org.pk, content="hi",
        )
    after = CRMOrganization.objects.values_list("modified", flat=True).get(pk=org.pk)
    assert after == before


def test_non_comment_types_do_not_bump(alice, lead):
    """``crm/utils/__init__.py:242`` — likes and assignments share the table."""
    from crm_app.models import CRMLead
    from frappe_platform.models import Comment

    before = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    with session_user(alice.name):
        Comment.objects.create(
            comment_type="Like", reference_doctype="CRM Lead",
            reference_name=lead.pk, content="liked",
        )
    after = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    assert after == before


def test_the_bump_is_off_when_the_setting_is_off(alice, lead, administrator):
    """``FCRM Settings.update_timestamp_on_new_communication``
    (``crm/utils/__init__.py:158-160``)."""
    from crm_app.models import CRMLead, FCRMSettings
    from frappe_platform.models import Comment

    with session_user(administrator.name):
        settings_row = FCRMSettings.load()
        settings_row.update_timestamp_on_new_communication = False
        settings_row.save()

    before = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    with session_user(alice.name):
        Comment.objects.create(
            comment_type="Comment", reference_doctype="CRM Lead",
            reference_name=lead.pk, content="quiet",
        )
    after = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    assert after == before


def test_a_communication_also_bumps(alice, lead):
    from crm_app.models import CRMLead
    from frappe_platform.models import Communication

    before = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    with session_user(alice.name):
        Communication.objects.create(
            reference_doctype="CRM Lead", reference_name=lead.pk, content="Replied"
        )
    after = CRMLead.objects.values_list("modified", flat=True).get(pk=lead.pk)
    assert after > before


def test_update_modified_background_ignores_an_unknown_doctype():
    from crm_app.tasks import update_modified_background

    assert update_modified_background("No Such DocType", "x") is False


# ---------------------------------------------------------------------------
# Invitation email — §3
# ---------------------------------------------------------------------------


def test_creating_an_invitation_sends_one_email(administrator):
    mail.outbox.clear()
    invitation = _invitation("invitee@example.com", administrator=administrator)

    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["invitee@example.com"]
    assert invitation.key in mail.outbox[0].body


def test_the_invitation_email_uses_the_default_outgoing_account(administrator):
    """`PHASE_5_ASYNC.md` §3 — identity comes from the Email Account, not
    ``DEFAULT_FROM_EMAIL``."""
    from frappe_platform.models import EmailAccount

    with session_user(administrator.name):
        EmailAccount.objects.create(
            email_account_name="Outbound", email_id="sales@acme.com", default_outgoing=True
        )

    mail.outbox.clear()
    _invitation("invitee2@example.com", administrator=administrator)
    assert mail.outbox[0].from_email == "sales@acme.com"


def test_the_invitation_email_falls_back_when_no_account_is_configured(administrator):
    from django.conf import settings as django_settings

    mail.outbox.clear()
    _invitation("invitee3@example.com", administrator=administrator)
    assert mail.outbox[0].from_email == django_settings.DEFAULT_FROM_EMAIL


def test_sending_records_the_timestamp(administrator):
    from crm_app.models import CRMInvitation

    invitation = _invitation("stamped@example.com", administrator=administrator)
    assert CRMInvitation.objects.get(pk=invitation.pk).email_sent_at is not None


def test_the_invitation_email_retries_a_transport_failure():
    """`PHASE_5_ASYNC.md` §3 — *"a Celery task with retry"*.

    Narrow on purpose: retrying every ``Exception`` would replay a bug in the task three
    times before surfacing it.
    """
    import smtplib

    from crm_app.tasks import send_invitation_email

    assert smtplib.SMTPException in send_invitation_email.autoretry_for
    assert OSError in send_invitation_email.autoretry_for
    assert Exception not in send_invitation_email.autoretry_for
    assert send_invitation_email.max_retries == 3


def test_the_invitation_email_is_idempotent(administrator):
    """A Celery redelivery must not send a second invite."""
    from crm_app.tasks import send_invitation_email

    invitation = _invitation("once@example.com", administrator=administrator)
    mail.outbox.clear()

    assert send_invitation_email(str(invitation.pk)) is False
    assert mail.outbox == []


# ---------------------------------------------------------------------------
# Bulk delete — permission-checked inside the task
# ---------------------------------------------------------------------------


def test_bulk_delete_task_checks_permission_as_the_requesting_user(alice, bob, administrator):
    """`PHASE_5_ASYNC.md` §5 — *inside* the task, not only at request time.

    The task runs later in a worker with no request context, so the user has to be
    carried explicitly; without it the ambient session is ``Guest``.
    """
    from crm_app.models import CRMLead, CRMLeadStatus
    from crm_app.tasks import delete_bulk_docs_task
    from frappe_core.exceptions import PermissionError as FrappePermissionError

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        theirs = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)

    with pytest.raises(FrappePermissionError):
        delete_bulk_docs_task("CRM Lead", [theirs.name], user=alice.name)

    assert CRMLead.objects.filter(pk=theirs.name).exists()


def test_bulk_delete_task_deletes_what_the_user_may_delete(alice, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus
    from crm_app.tasks import delete_bulk_docs_task

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        mine = CRMLead.objects.create(first_name="Mine", lead_owner=alice, status=status)

    assert delete_bulk_docs_task("CRM Lead", [mine.name], user=alice.name) == "success"
    assert not CRMLead.objects.filter(pk=mine.name).exists()


def test_bulk_delete_re_authorizes_the_queued_arguments(alice, bob, administrator):
    """A queued message is an argument list like any other.

    Even with the request-time check passing, the task must refuse names ``user`` may not
    delete *now* — a replayed, hand-crafted or long-delayed message otherwise deletes
    whatever it says it may.
    """
    from crm_app.models import CRMLead, CRMLeadStatus
    from crm_app.tasks import delete_bulk_docs_task
    from frappe_core.exceptions import PermissionError as FrappePermissionError

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        theirs = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)

    with pytest.raises(FrappePermissionError):
        delete_bulk_docs_task("CRM Lead", [theirs.name], False, alice.name)
    assert CRMLead.objects.filter(pk=theirs.name).exists()


def test_bulk_delete_without_a_user_is_denied_rather_than_unfiltered(alice, administrator):
    """``session_user(None)`` binds Guest. The failure direction has to be deny."""
    from crm_app.models import CRMLead, CRMLeadStatus
    from crm_app.tasks import delete_bulk_docs_task
    from frappe_core.exceptions import PermissionError as FrappePermissionError

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        mine = CRMLead.objects.create(first_name="Mine", lead_owner=alice, status=status)

    with pytest.raises(FrappePermissionError):
        delete_bulk_docs_task("CRM Lead", [mine.name])
    assert CRMLead.objects.filter(pk=mine.name).exists()


def test_a_large_batch_is_enqueued(alice, administrator, monkeypatch):
    """``crm/api/doc.py:833`` — over ten items upstream enqueues instead of deleting
    inline. The threshold existed as a constant before phase 5 and did nothing."""
    from crm_app.api.doc import BULK_DELETE_ENQUEUE_THRESHOLD, delete_bulk_docs
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        names = [
            CRMLead.objects.create(
                first_name=f"L{i}", lead_owner=alice, status=status
            ).name
            for i in range(BULK_DELETE_ENQUEUE_THRESHOLD + 1)
        ]

    enqueued = []
    monkeypatch.setattr(
        "crm_app.tasks.delete_bulk_docs_task.delay",
        lambda *a, **kw: enqueued.append((a, kw)),
    )
    with session_user(alice.name):
        assert delete_bulk_docs("CRM Lead", names) == "success"

    assert len(enqueued) == 1
    assert enqueued[0][0][0] == "CRM Lead"
    # The user is carried explicitly; a worker has no request to read it from.
    assert enqueued[0][0][3] == alice.name


def test_a_small_batch_still_deletes_inline(alice, administrator, monkeypatch):
    from crm_app.api.doc import delete_bulk_docs
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        mine = CRMLead.objects.create(first_name="Mine", lead_owner=alice, status=status)

    enqueued = []
    monkeypatch.setattr(
        "crm_app.tasks.delete_bulk_docs_task.delay",
        lambda *a, **kw: enqueued.append(a),
    )
    with session_user(alice.name):
        delete_bulk_docs("CRM Lead", [mine.name])

    assert enqueued == []
    assert not CRMLead.objects.filter(pk=mine.name).exists()


def test_the_enqueued_batch_really_is_deleted(alice, administrator):
    """Eager mode runs the task inline, so this exercises the whole enqueue path end to
    end rather than only the fact that ``.delay`` was called."""
    from crm_app.api.doc import BULK_DELETE_ENQUEUE_THRESHOLD, delete_bulk_docs
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        names = [
            CRMLead.objects.create(
                first_name=f"L{i}", lead_owner=alice, status=status
            ).name
            for i in range(BULK_DELETE_ENQUEUE_THRESHOLD + 1)
        ]
        assert delete_bulk_docs("CRM Lead", names) == "success"

    assert not CRMLead.objects.filter(pk__in=names).exists()


def test_bulk_delete_respects_a_write_rule_stricter_than_the_read_rule(alice, administrator):
    """The bug a phase-5 review found.

    ``CRM View Settings`` is readable when public and deletable only by its owner or an
    admin (``permissions/metadata_docs.py``). Authorizing bulk delete from the *list*
    filter alone let this endpoint delete what ``DELETE /api/resource/<dt>/<name>``
    refuses.
    """
    from crm_app.api.doc import delete_bulk_docs
    from crm_app.models import CRMViewSettings
    from frappe_core.exceptions import PermissionError as FrappePermissionError

    with session_user(administrator.name):
        public = CRMViewSettings.objects.create(
            label="Everyone's", dt="CRM Lead", user=administrator, public=True
        )

    with session_user(alice.name):
        # Alice can see it...
        assert CRMViewSettings.objects.filter(pk=public.pk).exists()
        # ...and must not be able to delete it.
        with pytest.raises(FrappePermissionError):
            delete_bulk_docs("CRM View Settings", [public.name])

    assert CRMViewSettings.objects.filter(pk=public.pk).exists()


@pytest.mark.parametrize("ptype", ["read", "write", "delete", "create"])
def test_the_batched_object_rule_agrees_with_the_single_object_one(
    ptype, alice, bob, make_user, administrator
):
    """The invariant the C9 batching rests on.

    ``has_permission_batch`` is an optimisation: it must return exactly what calling
    ``has_permission`` per row returns. Two implementations of one rule is how a
    permission engine drifts, so this pins them together across a spread of rows —
    owned, someone else's, and unsaved — for every ptype the batch hook branches on.
    """
    from crm_app.models import CRMLead, CRMLeadStatus
    from frappe_core import permissions
    from frappe_core.session import session_user as _as

    carol = make_user("carol@example.com", first_name="Carol", roles=["Sales Manager"])

    with _as(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        mine = CRMLead.objects.create(first_name="Mine", lead_owner=alice, status=status)
        theirs = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)
        others = CRMLead.objects.create(first_name="Others", lead_owner=carol, status=status)
    unsaved = CRMLead(first_name="Draft", lead_owner=alice, status=status)

    rows = [mine, theirs, others, unsaved]
    # Carol is a Sales Manager: the branch the two implementations are most likely to
    # disagree on, because it short-circuits before the row-dependent step.
    for user in (alice.name, bob.name, carol.name, administrator.name, "Guest"):
        one_by_one = [
            r for r in rows if permissions.check_object_permission(r, ptype, user)
        ]
        batched = permissions.filter_object_permitted("CRM Lead", rows, ptype, user)
        assert [r.first_name for r in batched] == [
            r.first_name for r in one_by_one
        ], f"{user} / {ptype}"


def test_filter_object_permitted_falls_back_when_no_batch_hook_is_registered(
    alice, administrator
):
    """A doctype without the optional hook must still get the right answer, one call at
    a time — the fallback is what makes the hook optional."""
    from crm_app.models import CRMViewSettings
    from frappe_core import permissions, registry

    assert registry.get_entry("CRM View Settings").has_permission_batch is None

    with session_user(administrator.name):
        public = CRMViewSettings.objects.create(
            label="Everyone's", dt="CRM Lead", user=administrator, public=True
        )

    assert permissions.filter_object_permitted(
        "CRM View Settings", [public], "read", alice.name
    ) == [public]
    assert (
        permissions.filter_object_permitted(
            "CRM View Settings", [public], "delete", alice.name
        )
        == []
    )


def test_bulk_delete_task_is_idempotent(alice, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus
    from crm_app.tasks import delete_bulk_docs_task

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        mine = CRMLead.objects.create(first_name="Mine", lead_owner=alice, status=status)

    delete_bulk_docs_task("CRM Lead", [mine.name], user=alice.name)
    # A redelivery finds nothing left and must not raise.
    assert delete_bulk_docs_task("CRM Lead", [mine.name], user=alice.name) == "success"


# ---------------------------------------------------------------------------
# Product reconcile — emits the event phase 6 consumes
# ---------------------------------------------------------------------------


def test_product_reconciliation_is_a_no_op_behind_the_flag(settings):
    from crm_app.tasks import run_product_reconciliation

    settings.ENABLE_ERPNEXT = False
    assert "skipped" in run_product_reconciliation()


def test_a_skipped_reconciliation_does_not_announce_itself(settings, monkeypatch, alice):
    """``reconcile_job.py:24-25`` returns *before* the publish.

    Phase 5 published unconditionally so phase 6 would have an emitter to wire up. A
    phase-6 review caught it: announcing a sync that never ran is not a smaller version
    of the right behaviour.
    """
    import crm_app.tasks as tasks

    settings.ENABLE_ERPNEXT = False
    published = []
    monkeypatch.setattr(
        "crm_app.realtime.publish",
        lambda event, message=None, user=None: published.append((event, user)) or True,
    )
    tasks.run_product_reconciliation(user=alice.name)
    assert published == []


def test_product_reconciliation_publishes_its_completion_event(settings, monkeypatch, alice):
    """``reconcile_job.py:35`` — `PHASE_6_REALTIME.md` §2 lists this event as in scope.

    The reconciliation body is phase 7, so it is stubbed here; everything around it —
    the gate, the publish, the summary — is this phase's and is what is under test.
    """
    import crm_app.tasks as tasks

    settings.ENABLE_ERPNEXT = True
    monkeypatch.setattr(tasks, "_reconcile_products", lambda: {"created_in_crm": 0})
    published = []
    monkeypatch.setattr(
        "crm_app.realtime.publish",
        lambda event, message=None, user=None: published.append((event, user)) or True,
    )

    assert tasks.run_product_reconciliation(user=alice.name) == {"created_in_crm": 0}
    assert published == [("crm_product_sync_complete", alice.name)]


def test_reconciliation_still_refuses_to_run_without_a_provider(settings):
    """The flag being on with nothing behind it is a config error, not a silent success."""
    from crm_app.tasks import run_product_reconciliation

    settings.ENABLE_ERPNEXT = True
    with pytest.raises(NotImplementedError):
        run_product_reconciliation()


def test_publishing_is_never_load_bearing(monkeypatch):
    """`PHASE_6_REALTIME.md` §4 — nothing may break when Channels is switched off.

    This asserted ``publish(...) is False`` while phase 5's stub had no transport at all.
    Phase 6 supplied one, so that assertion was about the stub rather than the property.
    The property itself is unchanged and is what is checked here: with no channel layer,
    publishing degrades to False and never raises. ``test_phase6_realtime.py`` covers the
    same ground from the other side — a *broken* layer, and a write that still succeeds
    with realtime off.
    """
    from crm_app import realtime

    monkeypatch.setattr(realtime, "get_channel_layer", lambda: None)
    assert realtime.publish("anything", user="nobody@example.com") is False
    assert realtime.publish_to_doc("CRM Lead", "x", "anything") is False
