"""The two General settings that move a lead's or deal's communication status
(docs/FINDINGS.md 60, BROWSER_TESTING.md S20).

``on_communication_update`` (``crm/utils/__init__.py:261-290``) runs on every save of a
communication. With "Mark as replied on response" on, a sent one sets the document's
``communication_status`` to Replied; with "Reopen on new communication" on, a received
one sets it to Open. Only the latest communication on the document counts, and the same
column write bumps ``modified`` when the third switch is on. Both switches are off by
default, and the port stored them and read neither.
"""

import datetime

import pytest
from django.core.mail.backends.locmem import EmailBackend
from django.utils import timezone

from crm_app import communication as communication_service
from crm_app.models import CRMCommunicationStatus, CRMLead, CRMLeadStatus, FCRMSettings
from frappe_core.session import session_user
from frappe_platform.models import Communication, EmailAccount

pytestmark = pytest.mark.django_db

MAKE = "/api/method/frappe.core.doctype.communication.email.make"


@pytest.fixture(autouse=True)
def statuses(administrator):
    """``install.py:148-158``: ``seed_defaults`` writes Open and Replied."""
    with session_user(administrator.name):
        for name in ("Open", "Replied"):
            CRMCommunicationStatus.objects.get_or_create(status=name)


@pytest.fixture
def lead(alice, administrator):
    with session_user(administrator.name):
        status = CRMLeadStatus.objects.filter(lead_status="New").first() or (
            CRMLeadStatus.objects.create(lead_status="New", type="Open")
        )
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=alice, status=status)
    CRMLead.objects.filter(pk=lead.pk).update(communication_status_id="Open")
    return lead


def switches(reopen=False, replied=False, timestamp=True):
    FCRMSettings.load()
    FCRMSettings.objects.update(
        auto_reopen_on_new_communication=reopen,
        auto_mark_replied_on_response=replied,
        update_timestamp_on_new_communication=timestamp,
    )


def communicate(lead, sent_or_received, user, when=None):
    with session_user(user.name):
        row = Communication.objects.create(
            reference_doctype="CRM Lead",
            reference_name=lead.pk,
            sent_or_received=sent_or_received,
            communication_type="Communication",
            content="hello",
        )
    if when is not None:
        Communication.objects.filter(pk=row.pk).update(creation=when)
        row.refresh_from_db()
    return row


def status_of(lead) -> str | None:
    return CRMLead.objects.values_list("communication_status", flat=True).get(pk=lead.pk)


def test_with_both_switches_off_nothing_moves(lead, alice):
    switches()
    communicate(lead, "Sent", alice)
    assert status_of(lead) == "Open"
    CRMLead.objects.filter(pk=lead.pk).update(communication_status_id="Replied")
    communicate(lead, "Received", alice)
    assert status_of(lead) == "Replied"


def test_a_sent_communication_marks_the_lead_replied(lead, alice):
    switches(replied=True)
    communicate(lead, "Sent", alice)
    assert status_of(lead) == "Replied"


def test_a_received_communication_reopens_the_lead(lead, alice):
    switches(reopen=True)
    CRMLead.objects.filter(pk=lead.pk).update(communication_status_id="Replied")
    communicate(lead, "Received", alice)
    assert status_of(lead) == "Open"


def test_each_switch_moves_only_its_own_direction(lead, alice):
    """Reopen does nothing for a sent communication, Replied nothing for a received one."""
    switches(reopen=True)
    communicate(lead, "Sent", alice)
    assert status_of(lead) == "Open"
    switches(replied=True)
    communicate(lead, "Received", alice)
    assert status_of(lead) == "Open"


def test_only_the_latest_communication_counts(lead, alice):
    """``frappe.get_last_doc(..., order_by="creation desc")``: an older thread saved
    again does not undo what the newer one set."""
    switches(reopen=True, replied=True)
    old = communicate(lead, "Received", alice, when=timezone.now() - datetime.timedelta(days=2))
    communicate(lead, "Sent", alice)
    assert status_of(lead) == "Replied"

    with session_user(alice.name):
        old.subject = "edited"
        old.save()
    assert status_of(lead) == "Replied"


def test_one_write_bumps_modified_and_leaves_modified_by_alone(lead, alice, bob):
    """Inline, no worker needed: ``set_value(..., update_modified=False)``."""
    switches(replied=True)
    before = CRMLead.objects.values_list("modified", "modified_by").get(pk=lead.pk)
    communicate(lead, "Sent", bob)
    after = CRMLead.objects.values_list("modified", "modified_by").get(pk=lead.pk)
    assert after[0] > before[0]
    assert after[1] == before[1]


def test_sending_an_email_from_a_lead_marks_it_replied(auth_api, lead, administrator, monkeypatch):
    """The path the switch exists for: the send button (``email.make``)."""
    monkeypatch.setattr(communication_service, "open_backend", lambda account: EmailBackend())
    with session_user(administrator.name):
        EmailAccount.objects.create(
            email_account_name="Support",
            email_id="support@example.com",
            enable_outgoing=True,
            default_outgoing=True,
        )
    switches(replied=True)
    response = auth_api.post(
        MAKE,
        {
            "doctype": "CRM Lead",
            "name": lead.name,
            "subject": "Re: your quote",
            "content": "<p>Yes.</p>",
            "recipients": "buyer@example.test",
            "send_email": 1,
            "now": 1,
        },
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    assert status_of(lead) == "Replied"
