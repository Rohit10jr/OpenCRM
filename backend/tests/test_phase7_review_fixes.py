"""The phase-7 review's findings, each pinned by a test.

Kept in one file rather than scattered, because what they have in common is more useful
than where they happened to land: **every one of them is a second door**. An endpoint or a
mechanism that did the same job as a guarded one, without the guard.

* `frappe.client.get_single_value` read singleton fields without the row rule or
  `RESTRICTED_FIELDS` — a second door onto the credentials the generic route protects.
* The Twilio webhooks took the signature as a *parameter*, so the guard existed and the
  production path never reached it.
* The WhatsApp write endpoints did not consult their own feature flag.
* `get_external_companies` called out to a remote site for a disabled integration.
* `dismiss_sync_issue` wrote to a child table, going around the rule on its parent.
* The Facebook duplicate check ran before the insert, so two workers could both pass it.

Written after the fixes, and each was confirmed to fail before them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

import pytest

from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# High — frappe.client.get_single_value bypassed both mechanisms
# ---------------------------------------------------------------------------


@pytest.fixture
def exotel_configured(settings, administrator):
    from crm_app.models import CRMExotelSettings

    settings.ENABLE_EXOTEL = True
    with session_user(administrator.name):
        row = CRMExotelSettings.load()
        row.enabled = True
        row.api_key = "key"
        row.api_token = "token"
        row.webhook_verify_token = "the-webhook-secret"
        row.save()
    return row


def test_a_sales_user_cannot_read_the_webhook_secret_through_get_single_value(
    exotel_configured, alice
):
    """The worst of the review's findings.

    `webhook_verify_token` is the **entire** authentication on a public, `allow_guest`
    webhook. Before the fix any authenticated user could read it here and forge call
    events into the CRM.
    """
    from crm_app.api.client import client_get_single_value

    with session_user(alice.name):
        with pytest.raises(FrappePermissionError):
            client_get_single_value("CRM Exotel Settings", "webhook_verify_token")


def test_a_sales_user_cannot_read_the_erpnext_api_key_through_get_single_value(
    settings, administrator, alice
):
    from crm_app.api.client import client_get_single_value
    from crm_app.models import ERPNextCRMSettings

    settings.ENABLE_ERPNEXT = True
    with session_user(administrator.name):
        row = ERPNextCRMSettings.load()
        row.enabled = True
        row.api_key = "erp-key"
        row.save()

    with session_user(alice.name):
        with pytest.raises(FrappePermissionError):
            client_get_single_value("ERPNext CRM Settings", "api_key")


def test_the_row_rule_applies_too_not_just_the_field_rule(exotel_configured, alice):
    """Two separate gaps. Even an *unrestricted* field on a manager-only singleton was
    readable, because no row rule was consulted at all."""
    from crm_app.api.client import client_get_single_value

    with session_user(alice.name):
        with pytest.raises(FrappePermissionError):
            client_get_single_value("CRM Exotel Settings", "enabled")


def test_a_manager_can_still_read_what_they_are_meant_to(exotel_configured, administrator):
    """The fix must not close the screen it exists for."""
    from crm_app.api.client import client_get_single_value

    with session_user(administrator.name):
        assert client_get_single_value("CRM Exotel Settings", "webhook_verify_token") == (
            "the-webhook-secret"
        )


def test_a_truly_sensitive_field_stays_closed_even_to_a_manager(exotel_configured, administrator):
    """`api_token` is `SENSITIVE_FIELDS`: nobody reads it over the wire, manager or not.
    It is reached through `get_password`, in code."""
    from crm_app.api.client import client_get_single_value

    with session_user(administrator.name):
        with pytest.raises(FrappePermissionError):
            client_get_single_value("CRM Exotel Settings", "api_token")


def test_an_open_singleton_is_still_readable(db, alice, administrator):
    """`FCRM Settings` is read by every screen in the product — the fix must not have
    closed it."""
    from crm_app.api.client import client_get_single_value
    from crm_app.models import FCRMSettings

    with session_user(administrator.name):
        FCRMSettings.load()

    with session_user(alice.name):
        # Does not raise, whatever the value is.
        client_get_single_value("FCRM Settings", "crm_timeline_timestamp_format")


# ---------------------------------------------------------------------------
# High — the Twilio guard the production path never reached
# ---------------------------------------------------------------------------


def test_the_twilio_endpoints_ask_for_the_request(db):
    """The mechanism, asserted directly.

    Without `wants_request`, the handler cannot see the header the signature arrives in,
    and the check can only ever pass in a test.
    """
    from frappe_core.whitelist import get_method

    for path in (
        "crm.integrations.twilio.api.voice",
        "crm.integrations.twilio.api.twilio_incoming_call_handler",
        "crm.integrations.twilio.api.update_recording_info",
        "crm.integrations.twilio.api.update_call_status_info",
    ):
        assert getattr(get_method(path), "__frappe_wants_request__", False) is True, path


def test_the_request_wins_over_the_parameters(db):
    """`signature_and_url` prefers the request. If the parameters won, a caller could
    supply a URL they had signed themselves."""
    from crm_app.integrations.twilio.handler import signature_and_url

    class _Req:
        META = {"HTTP_X_TWILIO_SIGNATURE": "from-header"}

        def build_absolute_uri(self):
            return "https://real/url"

    url, signature = signature_and_url(_Req(), "https://attacker/url", "from-param")
    assert (url, signature) == ("https://real/url", "from-header")


def test_only_webhooks_ask_for_the_request(db):
    """`wants_request` is opt-in and should stay rare — an endpoint that takes the request
    can reach around the payload contract."""
    from frappe_core.whitelist import all_methods, get_method

    wanting = {
        path
        for path in all_methods()
        if getattr(get_method(path), "__frappe_wants_request__", False)
    }
    assert wanting == {
        "crm.integrations.twilio.api.voice",
        "crm.integrations.twilio.api.twilio_incoming_call_handler",
        "crm.integrations.twilio.api.update_recording_info",
        "crm.integrations.twilio.api.update_call_status_info",
    }


# ---------------------------------------------------------------------------
# Medium — WhatsApp wrote while switched off
# ---------------------------------------------------------------------------


@pytest.fixture
def lead(alice, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        CRMLeadStatus.objects.get_or_create(lead_status="New", defaults={"type": "Open"})
    with session_user(alice.name):
        return CRMLead.objects.create(first_name="Ada", lead_owner=alice)


def test_whatsapp_refuses_to_create_a_message_when_switched_off(settings, alice, lead):
    from crm_app.integrations.whatsapp import api
    from crm_app.models import WhatsAppMessage

    settings.ENABLE_WHATSAPP = False
    with session_user(alice.name):
        with pytest.raises(FrappePermissionError):
            api.create_whatsapp_message("CRM Lead", lead.pk, message="Hi", to="+91")

    assert not WhatsAppMessage.objects.exists()


def test_whatsapp_refuses_a_template_when_switched_off(settings, alice, lead):
    from crm_app.integrations.whatsapp import api

    settings.ENABLE_WHATSAPP = False
    with session_user(alice.name):
        with pytest.raises(FrappePermissionError):
            api.send_whatsapp_template("CRM Lead", lead.pk, "welcome", "+91")


def test_whatsapp_refuses_a_reaction_when_switched_off(settings, alice, lead):
    from crm_app.integrations.whatsapp import api
    from crm_app.models import WhatsAppMessage

    settings.ENABLE_WHATSAPP = True
    with session_user(alice.name):
        existing = WhatsAppMessage.objects.create(
            reference_doctype="CRM Lead", reference_name=lead.pk, message="Hi"
        )

    settings.ENABLE_WHATSAPP = False
    with session_user(alice.name):
        with pytest.raises(FrappePermissionError):
            api.react_on_whatsapp_message("👍", existing.pk)


def test_reading_history_still_works_when_switched_off(settings, alice, lead):
    """Deliberately not gated: turning the integration off must not hide conversations
    that already happened."""
    from crm_app.integrations.whatsapp import api
    from crm_app.models import WhatsAppMessage

    settings.ENABLE_WHATSAPP = True
    with session_user(alice.name):
        WhatsAppMessage.objects.create(
            reference_doctype="CRM Lead", reference_name=lead.pk, message="Old thread"
        )

    settings.ENABLE_WHATSAPP = False
    with session_user(alice.name):
        rows = api.get_whatsapp_messages("CRM Lead", lead.pk)

    assert [r["message"] for r in rows] == ["Old thread"]


# ---------------------------------------------------------------------------
# Medium — an outbound call from a disabled integration
# ---------------------------------------------------------------------------


def test_a_disabled_erpnext_makes_no_outbound_request(settings, administrator):
    from unittest.mock import patch

    from crm_app.integrations.erpnext import api, client
    from crm_app.models import ERPNextCRMSettings

    settings.ENABLE_ERPNEXT = False
    with session_user(administrator.name):
        row = ERPNextCRMSettings.load()
        row.enabled = True
        row.api_key = "k"
        row.api_secret = "s"
        row.erpnext_site_url = "https://erp.example.com"
        row.save()

    with patch.object(client.http, "request") as request:
        assert api.get_external_companies() == []
    assert request.call_count == 0, "a disabled integration must not call out"


# ---------------------------------------------------------------------------
# Medium — writing a child table around its parent's rule
# ---------------------------------------------------------------------------


def test_a_sales_user_cannot_dismiss_a_sync_issue(settings, administrator, alice):
    from crm_app.integrations.erpnext import api
    from crm_app.models import CRMProductSyncIssue, ERPNextCRMSettings

    settings.ENABLE_ERPNEXT = True
    with session_user(administrator.name):
        row = ERPNextCRMSettings.load()
        row.enabled = True
        row.save()
        issue = CRMProductSyncIssue.objects.create(
            parenttype="ERPNext CRM Settings", parent=str(row.pk), idx=1,
            product="WIDGET", kind="unlinked_orphan",
        )

    with session_user(alice.name):
        with pytest.raises(Exception):
            api.dismiss_sync_issue(issue.pk)

    assert CRMProductSyncIssue.objects.get(pk=issue.pk).dismissed is False


def test_a_manager_can_still_dismiss_one(settings, administrator):
    from crm_app.integrations.erpnext import api
    from crm_app.models import CRMProductSyncIssue, ERPNextCRMSettings

    settings.ENABLE_ERPNEXT = True
    with session_user(administrator.name):
        row = ERPNextCRMSettings.load()
        row.enabled = True
        row.save()
        issue = CRMProductSyncIssue.objects.create(
            parenttype="ERPNext CRM Settings", parent=str(row.pk), idx=1,
            product="WIDGET", kind="unlinked_orphan",
        )
        assert api.dismiss_sync_issue(issue.pk) is True

    assert CRMProductSyncIssue.objects.get(pk=issue.pk).dismissed is True


# ---------------------------------------------------------------------------
# Medium — idempotency that two workers could race past
# ---------------------------------------------------------------------------


def test_the_database_refuses_a_duplicate_facebook_lead(db, alice, administrator):
    """The application check runs before the insert, so it is a race. This is the backstop.

    Simulating the race properly needs two connections; asserting the constraint exists and
    bites is the honest equivalent — it is the database that has to hold the line.
    """
    from django.db import IntegrityError, transaction

    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        CRMLeadStatus.objects.get_or_create(lead_status="New", defaults={"type": "Open"})

    with session_user(alice.name):
        CRMLead.objects.create(
            first_name="Ada", lead_owner=alice,
            facebook_form_id="form-1", facebook_lead_id="lead-1",
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CRMLead.objects.create(
                    first_name="Ada again", lead_owner=alice,
                    facebook_form_id="form-1", facebook_lead_id="lead-1",
                )


def test_the_same_lead_id_on_another_form_is_allowed(db, alice, administrator):
    """The constraint is per form, matching the duplicate check's own scoping."""
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        CRMLeadStatus.objects.get_or_create(lead_status="New", defaults={"type": "Open"})

    with session_user(alice.name):
        CRMLead.objects.create(
            first_name="A", lead_owner=alice,
            facebook_form_id="form-1", facebook_lead_id="lead-1",
        )
        CRMLead.objects.create(
            first_name="B", lead_owner=alice,
            facebook_form_id="form-2", facebook_lead_id="lead-1",
        )

    assert CRMLead.objects.filter(facebook_lead_id="lead-1").count() == 2


def test_manually_created_leads_are_unaffected(db, alice, administrator):
    """The constraint is **partial**. An unconditional one would permit exactly one lead
    with both columns blank — that is, one manually created lead in the entire system."""
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        CRMLeadStatus.objects.get_or_create(lead_status="New", defaults={"type": "Open"})

    with session_user(alice.name):
        for i in range(3):
            CRMLead.objects.create(first_name=f"Manual {i}", lead_owner=alice)

    assert CRMLead.objects.filter(facebook_lead_id="").count() == 3
