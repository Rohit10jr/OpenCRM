"""Contact's primary rules on a document save, email validation, and the missing-contact
refusal: FINDINGS.md 10, 11 and 12.

Upstream's Contact.validate (frappe/contacts/doctype/contact/contact.py:65) runs
set_primary_email and set_primary("phone") / set_primary("mobile_no") on every save;
every Data field whose options is Email is validated (base_document.py:936-940); and
crm/api/contact.py asks has_permission, which is False for a name that does not exist.
"""

from urllib.parse import quote

import pytest

from crm_app.models import CRMDeal, CRMDealStatus, CRMLead, CRMLeadStatus
from frappe_core.session import session_user
from frappe_platform.models import Contact, ContactEmail, ContactPhone

pytestmark = pytest.mark.django_db

CONTACTS = "/api/resource/" + quote("Contact")


@pytest.fixture
def contact(alice):
    with session_user(alice.name):
        return Contact.objects.create(first_name="ZZ", last_name="Jane")


def _put(client, contact, body):
    return client.put(f"{CONTACTS}/{quote(contact.name)}", body, format="json")


# --- 10: the primary rules -----------------------------------------------------------


def test_a_lone_email_row_becomes_primary_and_the_column_follows(auth_api, contact):
    """contact.py:183-184 - one row is the primary, and it is persisted as such."""
    data = _put(auth_api, contact, {"email_ids": [{"email_id": "acme@zz.test"}]}).json()["data"]
    assert data["email_ids"][0]["is_primary"] is True
    assert data["email_id"] == "acme@zz.test"
    assert ContactEmail.objects.get(parent_contact=contact).is_primary is True


def test_a_bare_email_column_with_no_rows_is_cleared(auth_api, contact):
    """contact.py:176-178 - the rows are the truth, the column only mirrors them."""
    data = _put(auth_api, contact, {"email_id": "orphan@zz.test"}).json()["data"]
    assert data["email_id"] == ""


def test_two_rows_with_no_primary_leave_the_column_empty(auth_api, contact):
    """contact.py:193-194. The earlier port fell back to the first row."""
    data = _put(
        auth_api, contact, {"email_ids": [{"email_id": "a@zz.test"}, {"email_id": "b@zz.test"}]}
    ).json()["data"]
    assert data["email_id"] == ""
    assert [row["is_primary"] for row in data["email_ids"]] == [False, False]


def test_two_primary_emails_are_refused(auth_api, contact):
    response = _put(
        auth_api,
        contact,
        {"email_ids": [{"email_id": "a@zz.test", "is_primary": 1}, {"email_id": "b@zz.test", "is_primary": 1}]},
    )
    assert response.status_code == 417
    assert response.json()["message"] == "Only one <strong>Email ID</strong> can be set as primary."


def test_phone_and_mobile_follow_their_own_flags(auth_api, contact):
    data = _put(
        auth_api,
        contact,
        {"phone_nos": [{"phone": "+1 333", "is_primary_mobile_no": 1}, {"phone": "+1 444", "is_primary_phone": 1}]},
    ).json()["data"]
    assert data["mobile_no"] == "+1 333"
    assert data["phone"] == "+1 444"


def test_a_lone_phone_row_is_not_made_primary(auth_api, contact):
    """Only the email rule promotes a lone row (contact.py:183); set_primary does not."""
    data = _put(auth_api, contact, {"phone_nos": [{"phone": "+1 333"}]}).json()["data"]
    assert data["mobile_no"] == ""
    assert data["phone"] == ""


@pytest.mark.parametrize(
    "flag,label", [("is_primary_phone", "Phone"), ("is_primary_mobile_no", "Mobile No")]
)
def test_two_primary_numbers_are_refused(auth_api, contact, flag, label):
    response = _put(
        auth_api, contact, {"phone_nos": [{"phone": "+1 1", flag: 1}, {"phone": "+1 2", flag: 1}]}
    )
    assert response.status_code == 417
    assert response.json()["message"] == f"Only one <strong>{label}</strong> can be set as primary."


def test_rows_sent_on_create_are_applied_by_the_first_save(auth_api, alice):
    response = auth_api.post(
        CONTACTS,
        {"first_name": "ZZ", "last_name": "New", "email_ids": [{"email_id": "new@zz.test"}]},
        format="json",
    )
    assert response.status_code == 201, response.content[:300]
    data = response.json()["data"]
    assert data["email_ids"][0]["is_primary"] is True
    assert data["email_id"] == "new@zz.test"


# --- 11: email addresses are validated -------------------------------------------------


def test_an_email_row_that_is_not_an_address_is_refused(auth_api, contact):
    """frappe.utils.validate_email_address(throw=True): InvalidEmailAddressError."""
    response = _put(auth_api, contact, {"email_ids": [{"email_id": "not-an-email"}]})
    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "InvalidEmailAddressError"
    assert body["message"] == "not-an-email is not a valid Email Address"


def test_a_lead_email_is_validated(auth_api, alice):
    """crm_lead.py:146 validates the lead's email explicitly, before the owner check."""
    with session_user(alice.name):
        CRMLeadStatus.objects.create(lead_status="New", type="Open")
    response = auth_api.post(
        "/api/resource/" + quote("CRM Lead"),
        {"first_name": "ZZ", "email": "nope", "lead_owner": alice.name},
        format="json",
    )
    assert response.status_code == 417
    assert response.json()["exc_type"] == "InvalidEmailAddressError"
    assert response.json()["message"] == "nope is not a valid Email Address"
    assert not CRMLead.objects.filter(first_name="ZZ").exists()


def test_a_deals_email_comes_from_its_contact_rows(auth_api, alice):
    """A deal's email is derived from its primary contact on every save
    (crm_deal.py:120-149), upstream too, so a typed value never reaches the Email
    check there; the address is validated on the contact's row instead."""
    with session_user(alice.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        deal = CRMDeal.objects.create(deal_owner=alice, status=status)
    response = auth_api.put(
        "/api/resource/" + quote("CRM Deal") + "/" + quote(deal.name), {"email": "x y"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["data"]["email"] == ""


def test_a_semicolon_is_not_a_separator(auth_api, contact):
    """``frappe.utils.split_emails`` splits on commas and newlines only, so a
    semicolon-joined pair is one invalid address upstream, not two valid ones."""
    response = _put(auth_api, contact, {"email_ids": [{"email_id": "a@zz.test;b@zz.test"}]})
    assert response.status_code == 417
    assert response.json()["exc_type"] == "InvalidEmailAddressError"


def test_the_invalid_address_is_html_escaped(auth_api, contact):
    response = _put(auth_api, contact, {"email_ids": [{"email_id": "<b>x</b>"}]})
    assert response.json()["message"] == "&lt;b&gt;x&lt;/b&gt; is not a valid Email Address"


def test_a_display_name_form_is_accepted(auth_api, contact):
    """validate_email_address extracts the address from ``Name <addr>``."""
    response = _put(auth_api, contact, {"email_ids": [{"email_id": "Jane <jane@zz.test>"}]})
    assert response.status_code == 200, response.content[:300]


# --- 12: a missing contact is a permission error ------------------------------------------


def test_a_missing_contact_is_not_permitted(auth_api):
    response = auth_api.post(
        "/api/method/crm.api.contact.create_new",
        {"contact": "ZZ Nobody", "field": "email", "value": "x@y.test"},
        format="json",
    )
    assert response.status_code == 403
    assert response.json()["exc_type"] == "PermissionError"
    assert response.json()["message"] == "Not permitted"


def test_a_comment_on_a_missing_document_is_not_found(auth_api):
    """crm.api.comment.add_comment reaches frappe.get_doc upstream: DoesNotExistError."""
    response = auth_api.post(
        "/api/method/crm.api.comment.add_comment",
        {"reference_doctype": "CRM Lead", "reference_name": "CRM-LEAD-2099-00001", "content": "hi"},
        format="json",
    )
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"


# --- 23: a delete never validates the rows it removes --------------------------------------


def test_a_contact_whose_rows_would_fail_a_save_can_still_be_deleted(api_as, administrator, contact):
    """delete_doc.py:207-227 removes the child rows without running validate. The
    cascade here fires the row signal that re-derives the primaries, and two rows
    flagged primary phone - which a save refuses, but hand testing produced - made the
    delete answer 417 "Only one Phone can be set as primary."."""
    # bulk_create sends no signal, so the rows land as-is; it runs no naming either,
    # hence the explicit names.
    ContactPhone.objects.bulk_create(
        [
            ContactPhone(name="zz-row-1", parent_contact=contact, phone="+1 1", is_primary_phone=True),
            ContactPhone(name="zz-row-2", parent_contact=contact, phone="+1 1", is_primary_phone=True),
        ]
    )

    response = api_as(administrator).delete(f"{CONTACTS}/{quote(contact.name)}")

    assert response.status_code == 200, response.content[:300]
    assert not Contact.objects.filter(pk=contact.pk).exists()
    assert not ContactPhone.objects.filter(parent_contact_id=contact.pk).exists()


def test_a_row_deleted_on_its_own_still_resyncs_the_contact(auth_api, contact):
    """The guard brackets the contact's own delete only: removing one row of a live
    contact re-derives its mirror columns as before."""
    _put(auth_api, contact, {"email_ids": [{"email_id": "acme@zz.test"}]})
    contact.refresh_from_db()
    assert contact.email_id == "acme@zz.test"

    ContactEmail.objects.get(parent_contact=contact).delete()

    contact.refresh_from_db()
    assert contact.email_id == ""
