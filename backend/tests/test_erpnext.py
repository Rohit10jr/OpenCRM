"""ERPNext — the API-client subset, and the scope line.

The most important thing this file records is what is **not** here. Upstream supports
ERPNext installed on the same Frappe site, and that mode reaches directly into `Item`,
`Quotation`, `Customer` and their schema. The standing decision says this port is an API
client and that porting ERPNext's models is out of scope, so the same-site branches refuse
with a message instead — and `test_the_same_site_mode_is_refused_rather_than_silently_broken`
is what keeps that a refusal rather than a code path that appears to work.

No live ERPNext. The seam is `crm_app.integrations.erpnext.client`.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from crm_app.integrations.erpnext import api, client, customer, reconcile
from frappe_core.exceptions import ValidationError
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db

SITE = "https://erp.example.com"


@pytest.fixture
def erpnext_on(settings, administrator):
    from crm_app.models import ERPNextCRMSettings

    settings.ENABLE_ERPNEXT = True
    with session_user(administrator.name):
        row = ERPNextCRMSettings.load()
        row.enabled = True
        row.api_key = "erp-key"
        row.api_secret = "erp-secret"
        row.erpnext_site_url = SITE
        row.erpnext_company = "Acme Inc"
        row.is_erpnext_in_different_site = True
        row.sync_products = True
        row.save()
    return row


@pytest.fixture
def deal(alice, administrator):
    from crm_app.models import CRMDeal, CRMDealStatus

    with session_user(administrator.name):
        status, _ = CRMDealStatus.objects.get_or_create(
            deal_status="Qualification", defaults={"type": "Open"}
        )
    with session_user(alice.name):
        return CRMDeal.objects.create(deal_owner=alice, status=status, lead_name="Acme")


class _Response:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


# ---------------------------------------------------------------------------
# The scope line
# ---------------------------------------------------------------------------


def test_same_site_erpnext_is_always_reported_as_absent(erpnext_on):
    """Upstream asks whether the `erpnext` app is installed in this site. It never can be
    here, and saying so is what makes the frontend offer the remote configuration."""
    assert api.is_erpnext_installed() is False


def test_the_same_site_mode_is_refused_rather_than_silently_broken(erpnext_on, administrator, deal):
    """The alternative — letting the same-site branch fall through — would be an endpoint
    that returns a URL into a site that does not exist."""
    from crm_app.models import ERPNextCRMSettings

    with session_user(administrator.name):
        row = ERPNextCRMSettings.load()
        row.is_erpnext_in_different_site = False
        row.save()

    with session_user(administrator.name):
        with pytest.raises(ValidationError) as excinfo:
            api.get_customer_link(str(deal.pk))
    assert "separate site" in str(excinfo.value)


def test_a_disabled_integration_refuses_with_upstreams_wording(settings, erpnext_on, deal, alice):
    settings.ENABLE_ERPNEXT = False
    with session_user(alice.name):
        with pytest.raises(ValidationError) as excinfo:
            api.get_customer_link(str(deal.pk))
    assert "ERPNext is not integrated with the CRM" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


def test_the_credential_is_sent_as_a_frappe_token(erpnext_on):
    captured = {}

    def fake(method, url, **kwargs):
        captured.update(kwargs)
        captured["url"] = url
        return _Response({"data": []})

    with patch.object(client.http, "request", fake):
        client.get_list("Company")

    assert captured["headers"]["Authorization"] == "token erp-key:erp-secret"
    assert captured["url"] == f"{SITE}/api/resource/Company"


def test_the_secret_is_decrypted_before_use(erpnext_on):
    key, secret = client._credentials()
    assert secret == "erp-secret"
    assert erpnext_on.api_secret != "erp-secret", "the stored attribute should be ciphertext"


def test_get_list_degrades_to_empty_on_failure(erpnext_on):
    """§3: a provider outage must not break a screen that is only asking whether a remote
    record exists."""
    with patch.object(client.http, "request", side_effect=RuntimeError("network")):
        assert client.get_list("Company") == []


def test_post_api_raises_on_failure(erpnext_on):
    """Unlike `get_list`. Its callers are *creating* something remotely, and a silent
    failure means a deal that believes it has a Customer which does not exist."""
    with patch.object(client.http, "request", side_effect=RuntimeError("network")):
        with pytest.raises(client.ERPNextError):
            client.post_api("some.method", {})


def test_post_api_raises_on_an_http_error(erpnext_on):
    with patch.object(client.http, "request", return_value=_Response({}, status_code=500)):
        with pytest.raises(client.ERPNextError):
            client.post_api("some.method", {})


def test_an_unconfigured_integration_lists_nothing(settings, administrator):
    from crm_app.models import ERPNextCRMSettings

    settings.ENABLE_ERPNEXT = True
    with session_user(administrator.name):
        row = ERPNextCRMSettings.load()
        row.enabled = True
        row.save()

    assert client.is_configured() is False
    assert api.get_external_companies() == []


def test_companies_are_listed_from_the_remote_site(erpnext_on):
    body = {"data": [{"company_name": "Acme Inc"}, {"company_name": "Acme GmbH"}]}
    with patch.object(client.http, "request", return_value=_Response(body)):
        assert api.get_external_companies() == body["data"]


# ---------------------------------------------------------------------------
# Customer link and quotation URL
# ---------------------------------------------------------------------------


def test_the_customer_link_points_at_the_remote_desk(erpnext_on, deal, alice):
    body = {"data": [{"name": "CUST-0001"}]}
    with patch.object(client.http, "request", return_value=_Response(body)):
        with session_user(alice.name):
            link = api.get_customer_link(str(deal.pk))

    assert link == f"{SITE}/app/customer/CUST-0001"


def test_a_deal_with_no_remote_customer_gets_an_empty_link(erpnext_on, deal, alice):
    with patch.object(client.http, "request", return_value=_Response({"data": []})):
        with session_user(alice.name):
            assert api.get_customer_link(str(deal.pk)) == ""


def test_the_stored_customer_is_used_when_the_remote_lookup_finds_nothing(erpnext_on, deal, alice):
    """`erpnext_crm_settings.py:361-362` — the column is the fallback."""
    from crm_app.models import CRMDeal

    CRMDeal.objects.filter(pk=deal.pk).update(erpnext_customer="CUST-STORED")

    with patch.object(client.http, "request", return_value=_Response({"data": []})):
        with session_user(alice.name):
            link = api.get_customer_link(str(deal.pk))

    assert link.endswith("/CUST-STORED")


def test_reading_a_deal_you_cannot_see_is_refused(erpnext_on, deal, bob):
    with patch.object(client.http, "request", return_value=_Response({"data": []})):
        with session_user(bob.name):
            with pytest.raises(ValidationError):
                api.get_customer_link(str(deal.pk))


def test_the_quotation_url_names_the_prospect_it_just_created(erpnext_on, deal, alice):
    with patch.object(client, "post_api", return_value="PROS-0001"):
        with session_user(alice.name):
            url = api.get_quotation_url(str(deal.pk))

    assert url.startswith(f"{SITE}/app/quotation/new?")
    assert "party_name=PROS-0001" in url
    assert "quotation_to=Prospect" in url
    assert "company=Acme%20Inc" in url


def test_a_failed_prospect_creation_surfaces_upstreams_message(erpnext_on, deal, alice):
    with patch.object(client, "post_api", side_effect=client.ERPNextError("boom")):
        with session_user(alice.name):
            with pytest.raises(ValidationError) as excinfo:
                api.get_quotation_url(str(deal.pk))
    assert "Error while creating prospect in ERPNext" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Customer on status change
# ---------------------------------------------------------------------------


def test_a_customer_is_created_when_the_deal_reaches_the_configured_status(
    erpnext_on, deal, alice, administrator
):
    from crm_app.models import CRMDeal, CRMDealStatus, ERPNextCRMSettings

    with session_user(administrator.name):
        won, _ = CRMDealStatus.objects.get_or_create(
            deal_status="Won", defaults={"type": "Won"}
        )
        row = ERPNextCRMSettings.load()
        row.create_customer_on_status_change = True
        row.deal_status = won
        row.save()

    with patch.object(client, "post_api", return_value="CUST-NEW"):
        with session_user(alice.name):
            deal.status = won
            deal.save()

    assert CRMDeal.objects.get(pk=deal.pk).erpnext_customer == "CUST-NEW"


def test_no_customer_is_created_for_any_other_status(erpnext_on, deal, alice, administrator):
    """Upstream compares against *the* configured status, not any status change."""
    from crm_app.models import CRMDeal, CRMDealStatus, ERPNextCRMSettings

    with session_user(administrator.name):
        won, _ = CRMDealStatus.objects.get_or_create(deal_status="Won", defaults={"type": "Won"})
        other, _ = CRMDealStatus.objects.get_or_create(
            deal_status="Negotiation", defaults={"type": "Open"}
        )
        row = ERPNextCRMSettings.load()
        row.create_customer_on_status_change = True
        row.deal_status = won
        row.save()

    with patch.object(client, "post_api", return_value="CUST-NEW") as post:
        with session_user(alice.name):
            deal.status = other
            deal.save()

    assert post.call_count == 0
    assert CRMDeal.objects.get(pk=deal.pk).erpnext_customer == ""


def test_the_setting_gates_it(erpnext_on, deal, alice, administrator):
    from crm_app.models import CRMDealStatus, ERPNextCRMSettings

    with session_user(administrator.name):
        won, _ = CRMDealStatus.objects.get_or_create(deal_status="Won", defaults={"type": "Won"})
        row = ERPNextCRMSettings.load()
        row.create_customer_on_status_change = False
        row.deal_status = won
        row.save()

    with patch.object(client, "post_api", return_value="CUST-NEW") as post:
        with session_user(alice.name):
            deal.status = won
            deal.save()

    assert post.call_count == 0


def test_an_unreachable_erpnext_does_not_break_the_deal_save(
    erpnext_on, deal, alice, administrator
):
    """§3's headline requirement: *"an unreachable provider must never break lead or deal
    CRUD."*

    Upstream throws from its `doc_events` hook, which rolls back a status change the user
    made for reasons of their own. `UPSTREAM_BUGS` #32.
    """
    from crm_app.models import CRMDeal, CRMDealStatus, ERPNextCRMSettings

    with session_user(administrator.name):
        won, _ = CRMDealStatus.objects.get_or_create(deal_status="Won", defaults={"type": "Won"})
        row = ERPNextCRMSettings.load()
        row.create_customer_on_status_change = True
        row.deal_status = won
        row.save()

    with patch.object(client, "post_api", side_effect=client.ERPNextError("down")):
        with session_user(alice.name):
            deal.status = won
            deal.save()  # must not raise

    stored = CRMDeal.objects.get(pk=deal.pk)
    assert stored.status_id == won.pk, "the status change must have survived"
    assert stored.erpnext_customer == ""


def test_the_customer_event_is_broadcast(erpnext_on, deal, alice, administrator, monkeypatch):
    """`erpnext_crm_settings.py:632` — no payload, no user. `Deal.vue:500` refetches."""
    from crm_app.models import CRMDealStatus, ERPNextCRMSettings

    with session_user(administrator.name):
        won, _ = CRMDealStatus.objects.get_or_create(deal_status="Won", defaults={"type": "Won"})
        row = ERPNextCRMSettings.load()
        row.create_customer_on_status_change = True
        row.deal_status = won
        row.save()

    published = []
    monkeypatch.setattr(
        "crm_app.realtime.publish", lambda *a, **kw: published.append((a, kw)) or True
    )

    with patch.object(client, "post_api", return_value="CUST-NEW"):
        with session_user(alice.name):
            deal.status = won
            deal.save()

    assert published[0][0][0] == "crm_customer_created"
    assert published[0][1].get("user") is None


# ---------------------------------------------------------------------------
# Reconciliation — the phase-5 seam
# ---------------------------------------------------------------------------


@pytest.fixture
def products(administrator):
    from crm_app.models import CRMProduct

    with session_user(administrator.name):
        return [
            CRMProduct.objects.create(product_code="WIDGET", product_name="Widget"),
            CRMProduct.objects.create(product_code="GADGET", product_name="Gadget"),
        ]


def test_a_product_is_linked_to_a_matching_remote_item(erpnext_on, products):
    from crm_app.models import CRMProduct

    body = {"data": [{"item_code": "WIDGET"}]}
    with patch.object(client.http, "request", return_value=_Response(body)):
        summary = reconcile.reconcile()

    assert summary["linked_by_exact_code"] == 1
    assert CRMProduct.objects.get(pk="WIDGET").erpnext_item_code == "WIDGET"
    assert CRMProduct.objects.get(pk="GADGET").erpnext_item_code == ""


def test_an_already_linked_product_is_counted_not_relinked(erpnext_on, products):
    from crm_app.models import CRMProduct

    CRMProduct.objects.filter(pk="WIDGET").update(erpnext_item_code="WIDGET")
    body = {"data": [{"item_code": "WIDGET"}]}
    with patch.object(client.http, "request", return_value=_Response(body)):
        summary = reconcile.reconcile()

    assert summary["already_linked"] == 1
    assert summary["linked_by_exact_code"] == 0


def test_a_link_to_a_vanished_item_is_recorded_as_an_orphan(erpnext_on, products):
    from crm_app.models import CRMProduct, CRMProductSyncIssue

    CRMProduct.objects.filter(pk="WIDGET").update(erpnext_item_code="GONE")
    body = {"data": [{"item_code": "SOMETHING-ELSE"}]}
    with patch.object(client.http, "request", return_value=_Response(body)):
        summary = reconcile.reconcile()

    assert summary["unlinked_orphans"] == 1
    issue = CRMProductSyncIssue.objects.get(kind="unlinked_orphan")
    assert issue.product == "WIDGET"


def test_an_unreachable_erpnext_does_not_orphan_every_product(erpnext_on, products):
    """An empty remote list means "unknown", not "there are none".

    Treating it as "none" would mark every linked product as an orphan the first time
    ERPNext was unreachable, and fill the issue table with noise.
    """
    from crm_app.models import CRMProduct, CRMProductSyncIssue

    CRMProduct.objects.filter(pk="WIDGET").update(erpnext_item_code="WIDGET")
    with patch.object(client.http, "request", side_effect=RuntimeError("network")):
        summary = reconcile.reconcile()

    assert summary["unlinked_orphans"] == 0
    assert CRMProductSyncIssue.objects.count() == 0


def test_repeated_reconciliation_does_not_pile_up_identical_issues(erpnext_on, products):
    """It runs on a schedule. Upstream appends unconditionally — `UPSTREAM_BUGS` #31."""
    from crm_app.models import CRMProduct, CRMProductSyncIssue

    CRMProduct.objects.filter(pk="WIDGET").update(erpnext_item_code="GONE")
    body = {"data": [{"item_code": "OTHER"}]}
    with patch.object(client.http, "request", return_value=_Response(body)):
        reconcile.reconcile()
        reconcile.reconcile()

    assert CRMProductSyncIssue.objects.filter(kind="unlinked_orphan").count() == 1


def test_the_phase_five_seam_is_filled(erpnext_on, products, settings):
    """`crm_app/tasks.py:_reconcile_products` raised `NotImplementedError` from phase 5
    until now, which is why `KNOWN_ISSUES.md` §5 records that no Celery task had ever
    published to a browser end to end."""
    from crm_app.tasks import run_product_reconciliation

    with patch.object(client.http, "request", return_value=_Response({"data": []})):
        summary = run_product_reconciliation(user="Administrator")

    assert "skipped" not in summary
    assert "already_linked" in summary


def test_the_reconciliation_publishes_its_completion_event(erpnext_on, products, monkeypatch):
    published = []
    monkeypatch.setattr(
        "crm_app.realtime.publish", lambda *a, **kw: published.append((a, kw)) or True
    )
    from crm_app.tasks import run_product_reconciliation

    with patch.object(client.http, "request", return_value=_Response({"data": []})):
        run_product_reconciliation(user="Administrator")

    assert published[0][0][0] == "crm_product_sync_complete"


# ---------------------------------------------------------------------------
# Sync issues and status
# ---------------------------------------------------------------------------


def test_open_issues_exclude_dismissed_ones(erpnext_on, products, administrator):
    from crm_app.models import CRMProductSyncIssue

    with session_user(administrator.name):
        CRMProductSyncIssue.objects.create(
            parenttype="ERPNext CRM Settings", parent="Settings", idx=1,
            product="WIDGET", kind="unlinked_orphan", dismissed=False,
        )
        CRMProductSyncIssue.objects.create(
            parenttype="ERPNext CRM Settings", parent="Settings", idx=2,
            product="GADGET", kind="unlinked_orphan", dismissed=True,
        )
        issues = api.get_open_sync_issues()

    assert [i["product"] for i in issues] == ["WIDGET"]


def test_dismissing_an_issue_hides_it(erpnext_on, products, administrator):
    from crm_app.models import CRMProductSyncIssue

    with session_user(administrator.name):
        issue = CRMProductSyncIssue.objects.create(
            parenttype="ERPNext CRM Settings", parent="Settings", idx=1,
            product="WIDGET", kind="unlinked_orphan",
        )
        assert api.dismiss_sync_issue(issue.pk) is True
        assert api.get_open_sync_issues() == []


def test_the_sync_status_reports_unsynced_products(erpnext_on, products, administrator):
    from crm_app.models import CRMProduct

    CRMProduct.objects.filter(pk="WIDGET").update(erpnext_item_code="WIDGET")
    with session_user(administrator.name):
        status = api.get_product_sync_status()

    assert status["products"]["count"] == 2
    assert status["unsynced"]["products"] == 1
    assert status["unsynced"]["sync_products"] is True


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def test_the_secret_is_encrypted_and_not_selectable(erpnext_on):
    from crm_app.models import ERPNextCRMSettings
    from frappe_core.field_security import restricted_fields, sensitive_fields

    assert "api_secret" in sensitive_fields(ERPNextCRMSettings)
    assert "api_key" in restricted_fields(ERPNextCRMSettings)

    stored = ERPNextCRMSettings.objects.get(pk="Settings")
    assert stored.api_secret != "erp-secret"
    assert stored.get_password("api_secret") == "erp-secret"


def test_the_settings_are_manager_only(erpnext_on, alice, administrator):
    from frappe_core.query import base_queryset

    assert base_queryset("ERPNext CRM Settings", alice.name).count() == 0
    assert base_queryset("ERPNext CRM Settings", administrator.name).count() == 1
