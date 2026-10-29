"""The shared call-log path and phone resolution — phase 7.

Provider-neutral, so these run with every integration flag **off**, which is the default
and is deliberate: the manual "Log a call" flow and the number-resolution the frontend does
on an incoming call both work without Twilio or Exotel configured.

`PHASE_7_INTEGRATIONS.md` §4 asks that "call logs land in `crm_call_log` identically for
both providers". That is a property of *this* module — the provider adapters call
`record_call` and nothing else — so it is tested here once rather than twice per provider.
"""

from __future__ import annotations

import pytest

from crm_app.integrations import call_log as path
from crm_app.integrations import phone
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def lead_status(administrator):
    """`status` is auto-defaulted on create, but only if the row it defaults *to* exists —
    `AS_BUILT.md` §5. Without this every `CRMLead.objects.create` here hits a NOT NULL."""
    from crm_app.models import CRMLeadStatus

    with session_user(administrator.name):
        status, _ = CRMLeadStatus.objects.get_or_create(
            lead_status="New", defaults={"type": "Open"}
        )
    return status


@pytest.fixture
def lead(alice, lead_status):
    from crm_app.models import CRMLead

    with session_user(alice.name):
        return CRMLead.objects.create(
            first_name="Ada", lead_owner=alice, mobile_no="+91 98765 43210"
        )


@pytest.fixture
def call(db):
    log, _ = path.record_call(
        call_id="CA-test-0001",
        medium=path.MEDIUM_MANUAL,
        call_type="Incoming",
        status="Completed",
        from_number="+919876543210",
        to_number="+911111111111",
    )
    return log


# ---------------------------------------------------------------------------
# parse / compare
# ---------------------------------------------------------------------------


def test_a_malformed_number_returns_rather_than_raises():
    """It runs on an inbound webhook. An exception here turns a junk caller ID into a 500."""
    result = phone.parse_phone_number("not a number")
    assert result["success"] is False
    assert "error" in result


def test_the_same_number_in_different_formats_compares_equal():
    assert phone.are_same_phone_number("+91 98765-43210", "09876543210") is True
    assert phone.are_same_phone_number("+919876543210", "(98765) 43210") is True


def test_different_numbers_do_not_compare_equal():
    assert phone.are_same_phone_number("+919876543210", "+919876543211") is False


def test_validation_can_be_relaxed_for_an_unparseable_caller():
    """``validate=False`` is upstream's ``exact_match`` path.

    ``+91 1111111111`` parses and normalises fine but is not a real allocation, so
    `is_valid_number` rejects it. With validation on the pair does not match; with it off
    the comparison is purely "do these normalise to the same E.164".
    """
    assert phone.are_same_phone_number("+911111111111", "01111111111", validate=True) is False
    assert phone.are_same_phone_number("+911111111111", "01111111111", validate=False) is True


# ---------------------------------------------------------------------------
# get_contact — the two-stage match
# ---------------------------------------------------------------------------


def test_an_unknown_number_returns_the_number_not_none(db):
    """Callers branch on ``.get("name")``; returning None would break them.

    The echoed value is the **national** number, not what was passed in — upstream hands
    `get_contact` the national part when the number parses (`api.py:161`) and the fallback
    echoes its own argument. Asserting the property rather than the exact string, because
    the quirk is upstream's and not something this port should tidy.
    """
    result = phone.get_contact_by_phone_number("+919999999999")
    assert result.get("name") is None
    assert result["mobile_no"] == "9999999999"


def test_an_empty_number_is_handled(db):
    assert phone.get_contact("") == {"mobile_no": ""}


def test_a_lead_is_found_by_its_mobile_number(lead):
    result = phone.get_contact_by_phone_number("+91 98765 43210")
    assert result.get("lead") == lead.pk
    assert result.get("full_name") == lead.lead_name


def test_a_lead_is_found_despite_stored_punctuation(alice, lead_status):
    """Stage 1 normalises the **stored** value column-side, not just the search term."""
    from crm_app.models import CRMLead

    with session_user(alice.name):
        stored = CRMLead.objects.create(
            first_name="Punct", lead_owner=alice, mobile_no="+91 (98765)-43211"
        )
    assert phone.get_contact_by_phone_number("+919876543211").get("lead") == stored.pk


def test_a_converted_lead_is_not_matched(alice, lead_status):
    """``.where(Lead.converted == 0)`` — a converted lead's number belongs to its contact."""
    from crm_app.models import CRMLead

    with session_user(alice.name):
        gone = CRMLead.objects.create(
            first_name="Gone", lead_owner=alice, mobile_no="+919876543212", converted=True
        )
    assert phone.get_contact_by_phone_number("+919876543212").get("lead") is None
    assert CRMLead.objects.filter(pk=gone.pk).exists()


def test_a_contact_is_found_through_its_secondary_number(administrator):
    """Upstream searches the ``phone_nos`` child rows, not ``mobile_no``, precisely so a
    call from a secondary number resolves (`api.py:307-309`)."""
    from frappe_platform.models import Contact, ContactPhone

    with session_user(administrator.name):
        contact = Contact.objects.create(first_name="Jane", mobile_no="+919000000000")
        ContactPhone.objects.create(
            parent_contact=contact, phone="+919876543213", idx=1
        )

    assert phone.get_contact_by_phone_number("+919876543213").get("name") == contact.pk


def test_a_digit_run_alone_does_not_match(administrator):
    """Stage 1 over-matches on purpose; stage 2 must throw the over-match away.

    The stored number is chosen so it **does** survive stage 1: normalised it is
    ``9198765432100``, which contains the searched ``9876543210`` as a substring. It is a
    different (and invalid) number, so `are_same_phone_number` must reject it.

    A first draft used ``+919843210999``, which shares the digits but not as a contiguous
    run — it never reached stage 2, so the test passed without exercising the thing it
    names. That is the vacuous-test failure the runbook warns about, caught by checking the
    stage-1 predicate by hand rather than trusting a green tick.

    **Mutation-checked, and the result was informative.** Disabling *either* half of stage 2
    alone leaves this passing: `are_same_phone_number` rejects the pair twice over, once
    because ``+9198765432100`` is not a valid allocation and again because the two E.164
    forms differ. It fails only with both disabled. So the coverage is real, and the
    redundancy is worth knowing about before someone "simplifies" one of them away.
    """
    from frappe_platform.models import Contact, ContactPhone

    with session_user(administrator.name):
        contact = Contact.objects.create(first_name="Coincidence")
        ContactPhone.objects.create(parent_contact=contact, phone="+9198765432100", idx=1)

    assert phone.get_contact_by_phone_number("+919876543210").get("name") is None


def test_a_deals_primary_contact_wins_over_a_lead(alice, administrator, lead_status):
    """Upstream returns from inside the contact loop before ever querying leads."""
    from crm_app.models import CRMContacts, CRMDeal, CRMDealStatus, CRMLead
    from frappe_platform.models import Contact, ContactPhone

    number = "+919876543214"
    with session_user(alice.name):
        CRMLead.objects.create(first_name="Loser", lead_owner=alice, mobile_no=number)

    with session_user(administrator.name):
        status, _ = CRMDealStatus.objects.get_or_create(
            deal_status="Qualification", defaults={"type": "Open"}
        )
        deal = CRMDeal.objects.create(deal_owner=alice, status=status)
        contact = Contact.objects.create(first_name="Winner")
        ContactPhone.objects.create(parent_contact=contact, phone=number, idx=1)
        CRMContacts.objects.create(parent_deal=deal, contact=contact, is_primary=True, idx=1)

    result = phone.get_contact_by_phone_number(number)
    assert result.get("deal") == deal.pk
    assert result.get("name") == contact.pk


def test_the_tuple_order_is_docname_then_doctype(lead):
    """Upstream's order, and the handlers unpack it that way."""
    docname, doctype = phone.get_contact_lead_or_deal_from_number("+919876543210")
    assert (docname, doctype) == (lead.pk, "CRM Lead")


def test_an_unknown_number_resolves_to_a_pair_of_nones(db):
    assert phone.get_contact_lead_or_deal_from_number("+919999999999") == (None, None)


# ---------------------------------------------------------------------------
# record_call — the dedupe point
# ---------------------------------------------------------------------------


def test_a_call_is_logged_under_the_providers_id(db):
    log, created = path.record_call(
        call_id="CA-abc", medium=path.MEDIUM_TWILIO, call_type="Incoming", status="Ringing"
    )
    assert created is True
    assert log.pk == "CA-abc"
    assert log.telephony_medium == "Twilio"


def test_a_redelivered_webhook_updates_rather_than_duplicating(db):
    """§3: *"dedupe by provider message ID"*. `autoname=field:id` makes that a primary-key
    constraint rather than a check somebody can forget."""
    from crm_app.models import CRMCallLog

    path.record_call(
        call_id="CA-dup", medium=path.MEDIUM_EXOTEL, call_type="Incoming", status="Ringing"
    )
    log, created = path.record_call(
        call_id="CA-dup",
        medium=path.MEDIUM_EXOTEL,
        call_type="Incoming",
        status="Completed",
        duration=42,
    )

    assert created is False
    assert CRMCallLog.objects.filter(pk="CA-dup").count() == 1
    assert log.status == "Completed"
    assert log.duration == 42


def test_a_later_callback_does_not_blank_what_an_earlier_one_set(db):
    """A provider sends several callbacks per call and the last one is not a superset."""
    path.record_call(
        call_id="CA-partial",
        medium=path.MEDIUM_TWILIO,
        call_type="Outgoing",
        status="In Progress",
        from_number="+911111111111",
        to_number="+912222222222",
        recording_url="https://example.com/rec.mp3",
    )
    log, _ = path.record_call(
        call_id="CA-partial", medium=path.MEDIUM_TWILIO, call_type="Outgoing", status="Completed"
    )

    assert log.recording_url == "https://example.com/rec.mp3"
    assert getattr(log, "from") == "+911111111111"
    assert getattr(log, "to") == "+912222222222"


def test_both_providers_produce_the_same_shape(db):
    """§4: *"Call logs land in `crm_call_log` identically for both providers."*"""
    twilio, _ = path.record_call(
        call_id="CA-t", medium=path.MEDIUM_TWILIO, call_type="Incoming",
        status="Completed", from_number="+911", to_number="+912", duration=10,
    )
    exotel, _ = path.record_call(
        call_id="CA-e", medium=path.MEDIUM_EXOTEL, call_type="Incoming",
        status="Completed", from_number="+911", to_number="+912", duration=10,
    )

    def shape(log):
        return {
            f: getattr(log, f)
            for f in ("status", "type", "duration", "reference_doctype", "reference_docname")
        } | {"from": getattr(log, "from"), "to": getattr(log, "to")}

    assert shape(twilio) == shape(exotel)
    assert {twilio.telephony_medium, exotel.telephony_medium} == {"Twilio", "Exotel"}


# ---------------------------------------------------------------------------
# links
# ---------------------------------------------------------------------------


def test_linking_is_idempotent(call, lead):
    """Webhooks get redelivered; two links to the same document would double the timeline."""
    assert path.link_with_reference_doc(call, "CRM Lead", lead.pk) is True
    assert path.link_with_reference_doc(call, "CRM Lead", lead.pk) is False
    assert len(path.get_links(call)) == 1


def test_a_call_can_link_to_several_documents(call, lead):
    from crm_app.models import FCRMNote

    note = FCRMNote.objects.create(title="Call Note", content="Discussed pricing")
    path.link_with_reference_doc(call, "CRM Lead", lead.pk)
    path.link_with_reference_doc(call, "FCRM Note", note.pk)

    assert {link["link_doctype"] for link in path.get_links(call)} == {"CRM Lead", "FCRM Note"}


def test_an_empty_link_is_refused(call):
    assert path.link_with_reference_doc(call, "CRM Lead", "") is False
    assert path.link_with_reference_doc(call, "", "x") is False
    assert path.get_links(call) == []


def test_resolving_sets_both_the_reference_and_the_link(call, lead):
    """The reference columns are the primary association; the link table is the looser
    'also mentions' set. Upstream writes both and they are not the same thing."""
    docname, doctype = path.resolve_and_link(call, "+919876543210")

    assert (docname, doctype) == (lead.pk, "CRM Lead")
    call.refresh_from_db()
    assert call.reference_doctype == "CRM Lead"
    assert call.reference_docname == lead.pk
    assert path.get_links(call)[0]["link_name"] == lead.pk


def test_an_unresolvable_number_still_leaves_the_call_logged(call):
    """§3: a provider problem must never break CRUD. An unknown caller is normal."""
    assert path.resolve_and_link(call, "+919999999999") == (None, None)
    call.refresh_from_db()
    assert call.reference_docname == ""


def test_the_reference_write_does_not_restamp_modified_by(call, lead, alice):
    """It runs from a webhook, where the ambient user is whatever authenticated — often
    nobody. `save()` would put that in `modified_by`."""
    from crm_app.models import CRMCallLog

    before = CRMCallLog.objects.values_list("modified_by", flat=True).get(pk=call.pk)
    with session_user(alice.name):
        path.set_reference(call, "CRM Lead", lead.pk)
    after = CRMCallLog.objects.values_list("modified_by", flat=True).get(pk=call.pk)
    assert after == before
