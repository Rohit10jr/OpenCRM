"""frappe.client.rename_doc renames in place: FINDINGS.md 13.

``frappe/model/rename_doc.py`` changes the name and repoints every Link, Dynamic Link,
child ``parent`` and version that named it. The port inserted a copy and deleted the
original, so a protected document could not be renamed and a cascading one lost its
rows. ``validate_rename``'s refusals are reproduced with its wording.
"""


import pytest

from crm_app.models import CRMContacts, CRMDeal, CRMDealStatus, CRMOrganization
from frappe_core.session import session_user
from frappe_core.versions import Version
from frappe_platform.models import Comment, Contact, ContactEmail, ContactPhone, ToDo

pytestmark = pytest.mark.django_db

RENAME = "/api/method/frappe.client.rename_doc"


def rename(client, doctype, old, new, **extra):
    return client.post(
        RENAME, {"doctype": doctype, "old_name": old, "new_name": new, **extra}, format="json"
    )


@pytest.fixture
def linked(alice, administrator):
    """An organization a deal points at (PROTECT), and a contact with email and phone
    rows (CASCADE) that the same deal lists in its contacts table."""
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        org = CRMOrganization.objects.create(organization_name="ZZ Contact Org")
        contact = Contact.objects.create(first_name="ZZ Jane", last_name="Roe")
        ContactEmail.objects.create(parent_contact=contact, email_id="jane@zz.test", is_primary=True)
        ContactEmail.objects.create(parent_contact=contact, email_id="jane.alt@zz.test")
        ContactPhone.objects.create(parent_contact=contact, phone="+1 111")
    with session_user(alice.name):
        deal = CRMDeal.objects.create(deal_owner=alice, status=status, organization=org)
        CRMContacts.objects.create(parent_deal=deal, contact=contact, is_primary=True, idx=1)
    return org, contact, deal


def test_a_protected_document_can_be_renamed_and_its_links_follow(auth_api, linked):
    org, contact, deal = linked

    response = rename(auth_api, "CRM Organization", "ZZ Contact Org", "ZZ Renamed Org")

    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"] == "ZZ Renamed Org"
    deal.refresh_from_db()
    assert deal.organization_id == "ZZ Renamed Org"
    assert CRMOrganization.objects.filter(pk="ZZ Renamed Org").exists()
    assert not CRMOrganization.objects.filter(pk="ZZ Contact Org").exists()


def test_a_cascading_document_keeps_its_rows_and_its_place_on_others(auth_api, linked):
    org, contact, deal = linked

    assert rename(auth_api, "Contact", "ZZ Jane Roe", "ZZ Jane Renamed").status_code == 200

    renamed = Contact.objects.get(pk="ZZ Jane Renamed")
    assert ContactEmail.objects.filter(parent_contact=renamed).count() == 2
    assert ContactPhone.objects.filter(parent_contact=renamed).count() == 1
    assert CRMContacts.objects.get(parent_deal=deal).contact_id == "ZZ Jane Renamed"
    assert not Contact.objects.filter(pk="ZZ Jane Roe").exists()


def test_dynamic_links_and_versions_follow(auth_api, alice, linked):
    """Comment, ToDo and Version name the document by doctype and name, with no foreign
    key; ``rename_dynamic_links`` and ``rename_versions`` upstream."""
    org, contact, deal = linked
    with session_user(alice.name):
        Comment.objects.create(
            comment_type="Comment", content="hi", reference_doctype="Contact", reference_name="ZZ Jane Roe"
        )
        ToDo.objects.create(
            allocated_to=alice, description="call", reference_type="Contact", reference_name="ZZ Jane Roe"
        )
        Version.objects.create(ref_doctype="Contact", docname="ZZ Jane Roe", data="{}")
        # The same name on another doctype must not move.
        Comment.objects.create(
            comment_type="Comment", content="other", reference_doctype="CRM Lead", reference_name="ZZ Jane Roe"
        )

    assert rename(auth_api, "Contact", "ZZ Jane Roe", "ZZ Jane Renamed").status_code == 200

    assert Comment.objects.filter(reference_doctype="Contact", reference_name="ZZ Jane Renamed").count() == 1
    assert ToDo.objects.filter(reference_type="Contact", reference_name="ZZ Jane Renamed").count() == 1
    assert Version.objects.filter(ref_doctype="Contact", docname="ZZ Jane Renamed").count() == 1
    assert Comment.objects.filter(reference_doctype="CRM Lead", reference_name="ZZ Jane Roe").count() == 1


def test_a_notifications_type_reference_follows_too(auth_api, alice, linked):
    """CRM Notification names the document twice: as the thing notified about
    (``notification_type_*``) and as the place to land (``reference_*``)."""
    from crm_app.models import CRMNotification

    with session_user(alice.name):
        CRMNotification.objects.create(
            from_user=alice, to_user=alice, type="Mention", message="m",
            notification_type_doctype="Contact", notification_type_doc="ZZ Jane Roe",
            reference_doctype="Contact", reference_name="ZZ Jane Roe",
        )
    assert rename(auth_api, "Contact", "ZZ Jane Roe", "ZZ Jane Renamed").status_code == 200
    row = CRMNotification.objects.get(notification_type_doctype="Contact")
    assert row.notification_type_doc == "ZZ Jane Renamed"
    assert row.reference_name == "ZZ Jane Renamed"


def test_a_row_under_a_non_key_unique_constraint_can_be_renamed(auth_api, alice):
    """A lead with Facebook ids is unique per form; the copy inserted beside the
    original would collide where upstream's in-place UPDATE never could, so the values
    are parked until the original is gone."""
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(alice.name):
        CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(
            first_name="ZZ Social", lead_owner=alice, facebook_form_id="f1", facebook_lead_id="l1"
        )
    response = rename(auth_api, "CRM Lead", lead.name, "CRM-LEAD-2099-00001")
    assert response.status_code == 200, response.content[:300]
    renamed = CRMLead.objects.get(pk="CRM-LEAD-2099-00001")
    assert (renamed.facebook_form_id, renamed.facebook_lead_id) == ("f1", "l1")
    assert not CRMLead.objects.filter(pk=lead.name).exists()


def test_the_renamed_row_keeps_its_stamps(auth_api, linked):
    org, contact, deal = linked
    rename(auth_api, "CRM Organization", "ZZ Contact Org", "ZZ Renamed Org")
    renamed = CRMOrganization.objects.get(pk="ZZ Renamed Org")
    assert renamed.owner_id == org.owner_id
    assert renamed.creation == org.creation


# --- validate_rename's refusals, verbatim ----------------------------------------------


def test_renaming_a_missing_document(auth_api):
    response = rename(auth_api, "CRM Organization", "ZZ Nobody", "ZZ Whoever")
    assert response.status_code == 417
    assert response.json()["message"] == (
        "Can't rename ZZ Nobody to ZZ Whoever because ZZ Nobody doesn't exist."
    )


def test_renaming_to_the_same_name(auth_api, linked):
    response = rename(auth_api, "CRM Organization", "ZZ Contact Org", "ZZ Contact Org")
    assert response.status_code == 417
    assert response.json()["message"] == (
        "No changes made because old and new name are the same."
    )


def test_renaming_onto_an_existing_name(auth_api, linked, administrator):
    with session_user(administrator.name):
        CRMOrganization.objects.create(organization_name="ZZ Taken")
    response = rename(auth_api, "CRM Organization", "ZZ Contact Org", "ZZ Taken")
    assert response.status_code == 417
    assert response.json()["message"] == (
        "Another CRM Organization with name ZZ Taken exists, select another name"
    )


def test_renaming_needs_write_permission(api_as, bob, linked):
    """bob is a Sales User who owns nothing here; upstream refuses with a 417 and this
    sentence, not a 403."""
    response = rename(api_as(bob), "CRM Deal", linked[2].name, "CRM-DEAL-2099-00001")
    assert response.status_code == 417
    assert response.json()["message"] == (
        f"You need write permission on CRM Deal {linked[2].name} to rename"
    )


def test_merge_is_still_refused(auth_api, linked):
    response = rename(auth_api, "CRM Organization", "ZZ Contact Org", "ZZ Other", merge=True)
    assert response.json()["messages"] == ["Merging documents is not supported"]
