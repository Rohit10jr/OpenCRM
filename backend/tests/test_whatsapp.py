"""WhatsApp — access rules, the six endpoints, and what happens on write.

The access tests matter most. A WhatsApp thread is more revealing than the record it hangs
off — a deal row leaks a number, the conversation leaks the negotiation — so
`WhatsApp Message` is registered with the same deferring rule as `Comment`, `Communication`
and `File`, and these tests are what hold it there.

The provider is stubbed at one named function. Nothing here needs Meta, and nothing here
pretends a message was delivered.
"""

from __future__ import annotations

import pytest

from crm_app.integrations.whatsapp import api, provider, signals
from frappe_core.exceptions import (
    DoesNotExistError,
    PermissionError as FrappePermissionError,
)
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def whatsapp_on(settings):
    settings.ENABLE_WHATSAPP = True


@pytest.fixture
def lead_status(administrator):
    from crm_app.models import CRMLeadStatus

    with session_user(administrator.name):
        status, _ = CRMLeadStatus.objects.get_or_create(
            lead_status="New", defaults={"type": "Open"}
        )
    return status


@pytest.fixture
def alice_lead(alice, lead_status):
    from crm_app.models import CRMLead

    with session_user(alice.name):
        return CRMLead.objects.create(
            first_name="Ada", lead_owner=alice, mobile_no="+919876543210"
        )


@pytest.fixture
def bob_lead(bob, lead_status):
    from crm_app.models import CRMLead

    with session_user(bob.name):
        return CRMLead.objects.create(
            first_name="Bruno", lead_owner=bob, mobile_no="+911111111111"
        )


def _message(lead, **overrides):
    from crm_app.models import WhatsAppMessage

    fields = {
        "reference_doctype": "CRM Lead",
        "reference_name": lead.pk,
        "message": "Hello",
        "to": "+919876543210",
        "type": "Outgoing",
        "content_type": "text",
    }
    fields.update(overrides)
    return WhatsAppMessage.objects.create(**fields)


# ---------------------------------------------------------------------------
# The flag, and the seam
# ---------------------------------------------------------------------------


def test_whatsapp_is_off_by_default(db):
    assert api.is_whatsapp_enabled() is False
    assert api.is_whatsapp_installed() is False


def test_the_flag_turns_it_on(whatsapp_on):
    assert api.is_whatsapp_enabled() is True


def test_sending_refuses_loudly_rather_than_lying(whatsapp_on, alice_lead):
    """A flag that is on with no provider is a configuration error.

    Returning success would show the user their message in the timeline, marked sent, while
    the recipient never receives it — a silent failure at the worst possible place.
    """
    with pytest.raises(NotImplementedError):
        provider.send_message(_message(alice_lead))


def test_templates_are_not_rendered_rather_than_faked(whatsapp_on):
    """`WhatsApp Templates` lives in `frappe_whatsapp`, which is deliberately not vendored."""
    assert provider.render_template("welcome", ["Ada"]) is None


def test_template_parameter_substitution_is_ported():
    """Pure string work with no provider dependency, so it is ported even though templates
    are not — a future provider will need it."""
    assert provider.parse_template_parameters("Hi {{1}}, re {{2}}", ["Ada", "pricing"]) == (
        "Hi Ada, re pricing"
    )


# ---------------------------------------------------------------------------
# validate_access — both halves
# ---------------------------------------------------------------------------


def test_a_user_without_a_sales_role_is_refused(whatsapp_on, make_user, alice_lead):
    outsider = make_user("nobody@example.com", roles=[])
    with session_user(outsider.name):
        with pytest.raises(FrappePermissionError) as excinfo:
            api.validate_access()
    assert "Only sales users can access WhatsApp features." in str(excinfo.value)


def test_a_sales_user_passes_the_role_check(whatsapp_on, alice):
    with session_user(alice.name):
        assert api.validate_access() is None


def test_access_to_someone_elses_lead_is_refused(whatsapp_on, alice, bob_lead):
    """The second half: a role is not enough, the referenced document is checked too."""
    with session_user(alice.name):
        with pytest.raises(FrappePermissionError) as excinfo:
            api.validate_access("CRM Lead", bob_lead.pk)
    assert "Not permitted to access reference document" in str(excinfo.value)


def test_a_missing_reference_document_is_reported_as_such(whatsapp_on, alice):
    with session_user(alice.name):
        with pytest.raises(DoesNotExistError) as excinfo:
            api.validate_access("CRM Lead", "no-such-lead")
    assert "does not exist" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The row rule — the reason this doctype is not world-readable
# ---------------------------------------------------------------------------


def test_a_message_on_an_invisible_lead_is_invisible(whatsapp_on, alice, bob, bob_lead):
    """The defect `attachments.py` exists for, applied to a conversation.

    Without the rule, `/api/resource/WhatsApp Message` would serve the thread of a lead the
    caller is refused.
    """
    from frappe_core.query import base_queryset

    with session_user(bob.name):
        hidden = _message(bob_lead, message="Our floor is 40k")

    with session_user(alice.name):
        visible = set(base_queryset("WhatsApp Message", alice.name).values_list("pk", flat=True))

    assert hidden.pk not in visible


def test_a_message_on_your_own_lead_is_visible(whatsapp_on, alice, alice_lead):
    from frappe_core.query import base_queryset

    with session_user(alice.name):
        mine = _message(alice_lead)
        visible = set(base_queryset("WhatsApp Message", alice.name).values_list("pk", flat=True))

    assert mine.pk in visible


def test_the_object_rule_refuses_a_message_on_an_invisible_lead(whatsapp_on, alice, bob, bob_lead):
    from frappe_core import permissions

    with session_user(bob.name):
        hidden = _message(bob_lead)

    assert permissions.check_object_permission(hidden, "read", alice.name) is False
    assert permissions.check_object_permission(hidden, "write", alice.name) is False


def test_the_doctype_is_registered_with_a_rule():
    """`test_route_surface.py` enforces this globally; this names it locally so a reader of
    this file sees the decision."""
    from frappe_core import registry

    entry = registry.get_entry("WhatsApp Message")
    assert entry.has_permission is not None
    assert entry.permission_query_conditions is not None


# ---------------------------------------------------------------------------
# get_whatsapp_messages
# ---------------------------------------------------------------------------


def test_messages_are_returned_for_a_readable_lead(whatsapp_on, alice, alice_lead):
    with session_user(alice.name):
        _message(alice_lead, message="First")
        _message(alice_lead, message="Second")
        rows = api.get_whatsapp_messages("CRM Lead", alice_lead.pk)

    assert [r["message"] for r in rows] == ["First", "Second"]


def test_reactions_are_filtered_out_of_the_timeline(whatsapp_on, alice, alice_lead):
    """`whatsapp.py:252` — a reaction renders on the message it reacts to."""
    with session_user(alice.name):
        _message(alice_lead, message="Hello")
        _message(alice_lead, message="👍", content_type="reaction")
        rows = api.get_whatsapp_messages("CRM Lead", alice_lead.pk)

    assert [r["message"] for r in rows] == ["Hello"]


def test_a_reply_carries_a_preview_of_what_it_replies_to(whatsapp_on, alice, alice_lead):
    with session_user(alice.name):
        _message(alice_lead, message="Original", message_id="wamid.1", type="Incoming")
        _message(alice_lead, message="Answer", is_reply=True, reply_to_message_id="wamid.1")
        rows = api.get_whatsapp_messages("CRM Lead", alice_lead.pk)

    reply = [r for r in rows if r["message"] == "Answer"][0]
    assert reply["reply_to_message"] == "Original"


def test_reading_someone_elses_thread_is_refused(whatsapp_on, alice, bob, bob_lead):
    with session_user(bob.name):
        _message(bob_lead)
    with session_user(alice.name):
        with pytest.raises(FrappePermissionError):
            api.get_whatsapp_messages("CRM Lead", bob_lead.pk)


def test_a_deal_also_shows_its_originating_leads_thread(whatsapp_on, alice, administrator, lead_status):
    """`whatsapp.py:122-140` — a conversation started before conversion must not vanish."""
    from crm_app.models import CRMDeal, CRMDealStatus, CRMLead

    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=alice)
    with session_user(administrator.name):
        status, _ = CRMDealStatus.objects.get_or_create(
            deal_status="Qualification", defaults={"type": "Open"}
        )
        deal = CRMDeal.objects.create(deal_owner=alice, status=status, lead=lead)

    with session_user(alice.name):
        _message(lead, message="Before conversion")
        _message(deal, reference_doctype="CRM Deal", message="After")
        rows = api.get_whatsapp_messages("CRM Deal", deal.pk)

    assert "Before conversion" in [r["message"] for r in rows]
    assert "After" in [r["message"] for r in rows]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def test_a_message_can_be_created_on_a_readable_lead(whatsapp_on, alice, alice_lead):
    from crm_app.models import WhatsAppMessage

    with session_user(alice.name):
        name = api.create_whatsapp_message(
            "CRM Lead", alice_lead.pk, message="Hi", to="+919876543210"
        )

    record = WhatsAppMessage.objects.get(pk=name)
    assert record.message == "Hi"
    assert record.reference_name == alice_lead.pk


def test_creating_a_message_on_someone_elses_lead_is_refused(whatsapp_on, alice, bob_lead):
    from crm_app.models import WhatsAppMessage

    with session_user(alice.name):
        with pytest.raises(FrappePermissionError):
            api.create_whatsapp_message("CRM Lead", bob_lead.pk, message="Hi", to="+91")

    assert not WhatsAppMessage.objects.filter(reference_name=bob_lead.pk).exists()


def test_an_attachment_becomes_the_message_when_there_is_no_text(whatsapp_on, alice, alice_lead):
    """`whatsapp.py:287` — `message or attach`."""
    from crm_app.models import WhatsAppMessage

    with session_user(alice.name):
        name = api.create_whatsapp_message(
            "CRM Lead", alice_lead.pk, message="", to="+91", attach="/files/quote.pdf"
        )
    assert WhatsAppMessage.objects.get(pk=name).message == "/files/quote.pdf"


def test_replying_to_an_invisible_message_is_refused(whatsapp_on, alice, bob, bob_lead, alice_lead):
    """Replying is a way of reaching a second document, so upstream re-validates against
    the original's reference as well."""
    with session_user(bob.name):
        theirs = _message(bob_lead, message_id="wamid.private")

    with session_user(alice.name):
        with pytest.raises(FrappePermissionError):
            api.create_whatsapp_message(
                "CRM Lead", alice_lead.pk, message="Hi", to="+91", reply_to=theirs.pk
            )


def test_replying_to_a_missing_message_is_reported(whatsapp_on, alice, alice_lead):
    with session_user(alice.name):
        with pytest.raises(DoesNotExistError) as excinfo:
            api.create_whatsapp_message(
                "CRM Lead", alice_lead.pk, message="Hi", to="+91", reply_to="nope"
            )
    assert "Referenced WhatsApp message does not exist." in str(excinfo.value)


def test_a_template_message_is_marked_as_one(whatsapp_on, alice, alice_lead):
    from crm_app.models import WhatsAppMessage

    with session_user(alice.name):
        name = api.send_whatsapp_template("CRM Lead", alice_lead.pk, "welcome", "+91")

    record = WhatsAppMessage.objects.get(pk=name)
    assert record.message_type == "Template"
    assert record.use_template is True
    assert record.template == "welcome"


def test_a_reaction_goes_back_to_the_other_party(whatsapp_on, alice, alice_lead):
    """`whatsapp.py:329` — for an incoming message the reaction is addressed to `from`."""
    from crm_app.models import WhatsAppMessage

    with session_user(alice.name):
        incoming = _message(
            alice_lead, type="Incoming", message_id="wamid.9", **{"from": "+919876543210"}
        )
        name = api.react_on_whatsapp_message("👍", incoming.pk)

    record = WhatsAppMessage.objects.get(pk=name)
    assert record.to == "+919876543210"
    assert record.content_type == "reaction"
    assert record.reply_to_message_id == "wamid.9"


def test_reacting_checks_the_role_before_looking_the_message_up(whatsapp_on, make_user, alice, alice_lead):
    """Upstream calls `validate_access()` with no arguments first, so a caller with no CRM
    role cannot use this endpoint to probe which message ids exist."""
    with session_user(alice.name):
        existing = _message(alice_lead)

    outsider = make_user("outsider@example.com", roles=[])
    with session_user(outsider.name):
        with pytest.raises(FrappePermissionError) as excinfo:
            api.react_on_whatsapp_message("👍", existing.pk)
    assert "Only sales users" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def test_an_incoming_message_resolves_its_lead_from_the_number(whatsapp_on, alice, alice_lead):
    from crm_app.models import WhatsAppMessage

    with session_user(alice.name):
        record = WhatsAppMessage.objects.create(
            type="Incoming", message="Hi", **{"from": "+919876543210"}
        )

    record.refresh_from_db()
    assert record.reference_doctype == "CRM Lead"
    assert record.reference_name == alice_lead.pk


def test_an_unresolvable_number_still_stores_the_message(whatsapp_on, alice):
    """§3: a lookup failure must not lose the message."""
    from crm_app.models import WhatsAppMessage

    with session_user(alice.name):
        record = WhatsAppMessage.objects.create(
            type="Incoming", message="Hi", **{"from": "+919999999999"}
        )

    record.refresh_from_db()
    assert record.reference_name == ""
    assert WhatsAppMessage.objects.filter(pk=record.pk).exists()


def test_an_existing_reference_is_not_overwritten(whatsapp_on, alice, alice_lead, bob_lead):
    """A message created through the endpoint already knows its document; the number lookup
    must not second-guess it."""
    with session_user(alice.name):
        record = _message(alice_lead, type="Incoming", **{"from": "+911111111111"})

    record.refresh_from_db()
    assert record.reference_name == alice_lead.pk


def test_the_message_event_is_a_broadcast(whatsapp_on, alice, alice_lead, monkeypatch):
    """`AS_BUILT.md` records this specifically so phase 7 would not reach for
    `publish_to_doc` by analogy with `docinfo_update`."""
    published = []
    monkeypatch.setattr(
        "crm_app.realtime.publish",
        lambda *a, **kw: published.append((a, kw)) or True,
    )

    with session_user(alice.name):
        _message(alice_lead)

    args, kwargs = published[0]
    assert args[0] == "whatsapp_message"
    assert set(args[1]) == {"reference_doctype", "reference_name"}
    assert kwargs.get("user") is None


def test_an_incoming_message_notifies_the_assigned_agent(whatsapp_on, alice, bob, alice_lead):
    from crm_app.models import CRMNotification
    from frappe_core.assignment import assign_to_user

    with session_user(alice.name):
        assign_to_user("CRM Lead", alice_lead.pk, bob.name)
        _message(alice_lead, type="Incoming", **{"from": "+919876543210"})

    notification = CRMNotification.objects.filter(to_user=bob, type="WhatsApp").first()
    assert notification is not None
    assert notification.notification_type_doctype == "CRM Lead"


def test_an_outgoing_message_notifies_nobody(whatsapp_on, alice, bob, alice_lead):
    """Upstream returns early for outgoing: it is the agent's own message."""
    from crm_app.models import CRMNotification
    from frappe_core.assignment import assign_to_user

    with session_user(alice.name):
        assign_to_user("CRM Lead", alice_lead.pk, bob.name)
        _message(alice_lead, type="Outgoing")

    assert not CRMNotification.objects.filter(type="WhatsApp").exists()


def test_the_notification_text_escapes_the_reference_name(whatsapp_on, alice, alice_lead):
    """It is rendered as HTML in the notification list, and upstream escapes it
    (`whatsapp.py:67`).

    A first draft created an ordinary lead and asserted `"<script" not in ...`. That could
    not fail: a lead's name is `CRM-LEAD-2026-00001`, generated by the naming series and
    never attacker-influenced, so nothing hostile ever reached the interpolation. This calls
    `notify_agent` with a crafted `reference_name` instead, which is the only way to make
    the escaping observable.
    """
    from crm_app.models import CRMNotification

    with session_user(alice.name):
        message = _message(alice_lead, type="Incoming")

    # The assignee lookup is keyed on the same `reference_name` being crafted here, so it
    # is stubbed: the subject under test is the interpolation, not the assignment.
    message.reference_name = "<script>alert(1)</script>"
    CRMNotification.objects.all().delete()

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            "frappe_core.assignment.get_assigned_users", lambda *a, **kw: [alice.name]
        )
        assert signals.notify_agent(message) == 1

    text = CRMNotification.objects.get(type="WhatsApp").notification_text
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
