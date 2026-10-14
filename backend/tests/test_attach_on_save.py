"""Attach-on-save: the file an Attach field names becomes the document's attachment.

Upstream runs ``attach_files_to_document`` (``frappe/core/doctype/file/utils.py:354-415``)
on every document's ``on_update`` (``frappe/hooks.py:205,227``). frappe-ui uploads privately
unless told otherwise, and the image uploaders - brand logo and favicon, profile photo, the
lead, contact and organization images - never tell it otherwise nor name a document, so
each lands as a private, unattached File row that only its uploader may read. Attaching it
to the document is what lets a colleague fetch it: the File rule defers to the attached
document, and FCRM Settings is readable by every CRM role (FINDINGS.md 85).
"""

import pytest

from crm_app.models import FCRMSettings
from frappe_core.session import session_user
from frappe_platform.files import attach_fields_of, find_file_by_url
from frappe_platform.models import File

pytestmark = pytest.mark.django_db

SET_VALUE = "/api/method/frappe.client.set_value"
LOGO = "/private/files/acme-logo.png"


def private_upload(owner, url=LOGO):
    """What the uploader leaves behind: a private row, attached to nothing."""
    with session_user(owner.name):
        row = File(file_url=url, is_private=True)
        row.save()
    assert row.attached_to_doctype == "" and row.is_private is True
    return row


def attachment(url):
    row = File._default_manager.get(file_url=url)
    return row.attached_to_doctype, row.attached_to_name, row.attached_to_field


# --- which fields count ---------------------------------------------------------------


def test_the_attach_fields_come_from_the_json_for_crm_doctypes_and_the_model_otherwise():
    assert set(attach_fields_of("FCRM Settings")) == {"brand_logo", "favicon"}
    assert attach_fields_of("CRM Organization") == ["organization_logo"]
    # Platform doctypes ship no JSON; the model's ATTACH_FIELDS stands in.
    assert attach_fields_of("User") == ["user_image"]
    assert attach_fields_of("Contact") == ["image"]
    assert attach_fields_of("CRM Task") == []


# --- the brand logo, the case that was reported ---------------------------------------


def test_the_brand_logo_is_the_uploaders_alone_until_the_settings_are_saved(administrator, bob):
    private_upload(administrator)
    with session_user(bob.name):
        assert find_file_by_url(LOGO) is None, "unattached and private: the owner only"

    with session_user(administrator.name):
        settings = FCRMSettings.load()
        settings.brand_logo = LOGO
        settings.save()

    assert attachment(LOGO) == ("FCRM Settings", "FCRM Settings", "brand_logo")
    assert File._default_manager.get(file_url=LOGO).is_private is True, "utils.py:398: follows the URL"
    with session_user(bob.name):
        assert find_file_by_url(LOGO) is not None, "attached: whoever may read the settings may fetch it"


def test_the_brand_page_save_attaches_through_the_api(api_as, administrator, bob):
    """The path the Brand page takes: ``set_value`` on FCRM Settings as a manager."""
    with session_user(administrator.name):
        FCRMSettings.load()
    private_upload(administrator)

    response = api_as(administrator).post(
        SET_VALUE,
        {"doctype": "FCRM Settings", "name": "FCRM Settings", "fieldname": "brand_logo", "value": LOGO},
        format="json",
    )

    assert response.status_code == 200, response.content[:300]
    assert attachment(LOGO) == ("FCRM Settings", "FCRM Settings", "brand_logo")
    with session_user(bob.name):
        assert find_file_by_url(LOGO) is not None


# --- the other images ------------------------------------------------------------------


def test_a_profile_photo_becomes_the_users_attachment(alice, bob):
    url = "/private/files/alice.png"
    private_upload(alice, url)

    alice.user_image = url
    alice.save()

    assert attachment(url) == ("User", alice.name, "user_image")
    with session_user(bob.name):
        assert find_file_by_url(url) is not None, "a colleague sees the avatar"


# --- the branches of utils.py:370-415 --------------------------------------------------


def test_an_attachment_of_this_document_is_left_as_it_is(administrator):
    private_upload(administrator)
    with session_user(administrator.name):
        settings = FCRMSettings.load()
        settings.brand_logo = LOGO
        settings.save()
        settings.brand_name = "Acme"
        settings.save()

    assert File._default_manager.filter(file_url=LOGO).count() == 1, "a second save adds nothing"


def test_another_documents_attachment_is_not_stolen(administrator, alice):
    """``utils.py:381-386``: only an *unattached* row is claimed; otherwise a new row."""
    with session_user(administrator.name):
        File(
            file_url=LOGO,
            is_private=True,
            attached_to_doctype="User",
            attached_to_name=alice.name,
            attached_to_field="user_image",
        ).save()
        settings = FCRMSettings.load()
        settings.brand_logo = LOGO
        settings.save()

    rows = File._default_manager.filter(file_url=LOGO).order_by("attached_to_doctype")
    assert [(r.attached_to_doctype, r.attached_to_field) for r in rows] == [
        ("FCRM Settings", "brand_logo"),
        ("User", "user_image"),
    ]


def test_a_url_with_no_file_row_gets_one(administrator):
    """``utils.py:404-415``: a URL-only row, in Home/Attachments, public when the URL is."""
    url = "/files/acme-favicon.png"
    with session_user(administrator.name):
        settings = FCRMSettings.load()
        settings.favicon = url
        settings.save()

    row = File._default_manager.get(file_url=url)
    assert (row.attached_to_doctype, row.attached_to_field) == ("FCRM Settings", "favicon")
    assert row.is_private is False
    assert row.file_name == "acme-favicon.png"
    assert row.folder == "Home/Attachments"


def test_an_empty_or_foreign_value_attaches_nothing(administrator):
    with session_user(administrator.name):
        settings = FCRMSettings.load()
        settings.brand_logo = ""
        settings.favicon = "data:image/png;base64,AAAA"
        settings.save()

    assert File._default_manager.count() == 0
