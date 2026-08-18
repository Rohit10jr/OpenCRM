"""Phase 1 cluster 1 - the Frappe platform doctypes.

PHASE_1_MODELS.md section 1. These ship no JSON in the CRM repo, so each assertion is
tied to the CRM usage that justifies the field.

The credential tests are the important ones: registering ``User`` and ``Email Account``
as doctypes makes them routable through the generic endpoint, which is exactly how a
password hash escapes if nobody checks.
"""

import json
from urllib.parse import quote

import pytest

from frappe_core import registry
from frappe_core.query import fetch_rows
from frappe_core.session import session_user
from frappe_platform.models import (
    Comment,
    Communication,
    Contact,
    ContactEmail,
    ContactPhone,
    EmailAccount,
    EmailTemplate,
    File,
    Tag,
    ToDo,
    User,
)

pytestmark = pytest.mark.django_db


# --- everything is registered and routable ------------------------------------


@pytest.mark.parametrize(
    "doctype,model",
    [
        ("User", User),
        ("Contact", Contact),
        ("ToDo", ToDo),
        ("Communication", Communication),
        ("Comment", Comment),
        ("Email Template", EmailTemplate),
        ("File", File),
        ("Tag", Tag),
        ("Email Account", EmailAccount),
    ],
)
def test_platform_doctype_is_registered(doctype, model):
    """Registration and routability are two things, and `ToDo` is why.

    It is registered - the permission engine queries it on every Lead and Deal read - but
    deliberately unpublished, because a writable ``/api/resource/ToDo`` let any user
    assign themselves to any document and thereby read it. See
    ``specs/UNROUTED_DOCTYPES.md``; the unrouted set is pinned in
    ``tests/test_unrouted_doctypes.py``.
    """
    assert registry.get_model(doctype) is model
    if registry.get_entry(doctype).routable:
        assert doctype in registry.routable_doctypes()
    else:
        assert doctype not in registry.routable_doctypes()


@pytest.mark.parametrize("doctype", ["Contact Email", "Contact Phone"])
def test_contact_child_tables_are_not_routable(doctype):
    assert registry.get_entry(doctype).is_child_table is True
    assert doctype not in registry.routable_doctypes()


# --- credentials never reach the wire -----------------------------------------


def test_user_serializer_omits_the_password_hash():
    fields = registry.get_entry("User").get_serializer_class()().get_fields()
    assert "password" not in fields
    assert "last_login" not in fields


def test_email_account_serializer_omits_the_password():
    fields = registry.get_entry("Email Account").get_serializer_class()().get_fields()
    assert "password" not in fields


def test_password_is_not_selectable_by_name(alice):
    from frappe_core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="not readable"):
        fetch_rows("User", fields=["name", "password"])


def test_password_is_not_swept_up_by_star(alice):
    rows = fetch_rows("User", fields=["*"])
    assert rows
    assert "password" not in rows[0]
    assert "last_login" not in rows[0]


def test_password_is_not_selectable_over_http(auth_api, alice):
    response = auth_api.get(
        "/api/resource/User", {"fields": json.dumps(["name", "password"])}
    )
    assert response.status_code == 417
    assert "not readable" in response.json()["message"]


def test_star_over_http_does_not_leak_the_hash(auth_api, alice):
    response = auth_api.get("/api/resource/User", {"fields": json.dumps(["*"])})
    assert response.status_code == 200
    body = json.dumps(response.json())
    assert "password" not in body
    assert alice.password not in body


def test_reading_a_user_document_does_not_leak_the_hash(auth_api, alice):
    response = auth_api.get(f"/api/resource/User/{quote(alice.name)}")
    assert response.status_code == 200
    assert "password" not in response.json()["data"]


def test_password_cannot_be_ordered_by(alice):
    from frappe_core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="Cannot order by"):
        fetch_rows("User", fields=["name"], order_by="password desc")


def test_email_account_password_is_not_selectable(db):
    from frappe_core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="not readable"):
        fetch_rows("Email Account", fields=["name", "password"])


def test_a_normal_field_is_still_selectable(alice):
    """The block list must not be so broad it breaks ordinary reads."""
    rows = fetch_rows("User", fields=["name", "full_name", "enabled"])
    assert rows and "full_name" in rows[0]


# --- Contact ------------------------------------------------------------------


@pytest.fixture
def contact(alice):
    with session_user(alice.name):
        return Contact.objects.create(first_name="Jane", last_name="Doe")


def test_contact_full_name_is_derived(contact):
    assert contact.full_name == "Jane Doe"


def test_contact_is_named_from_its_full_name(contact):
    assert contact.name == "Jane Doe"


def test_contact_name_collision_gets_a_numeric_suffix(alice, contact):
    """First collision is ``-1``, not ``-2``.

    Corrected against ``frappe/model/naming.py:506-530``, which uses ``count = "1"``
    when no numbered sibling exists. Full coverage in ``test_contact_naming.py``.
    """
    with session_user(alice.name):
        second = Contact.objects.create(first_name="Jane", last_name="Doe")
    assert second.name == "Jane Doe-1"


def test_contact_name_does_not_include_the_company(alice):
    """``company_name`` is a fallback, never a suffix.

    This test previously asserted ``"Jane Doe-Acme"``, locking in phase 1's guess.
    ``get_full_name`` (``frappe/contacts/doctype/contact/contact.py:463-473``) uses
    company **only** when first/middle/last are all empty - see
    ``test_company_is_used_when_there_is_no_person_name``.
    """
    with session_user(alice.name):
        c = Contact.objects.create(first_name="Jane", last_name="Doe", company_name="Acme")
    assert c.name == "Jane Doe"


def test_primary_email_is_denormalised_onto_the_contact(contact):
    """``crm/api/contact.py:20`` reads ``doc.email_id`` to sync it onto linked deals."""
    ContactEmail.objects.create(parent_contact=contact, email_id="jane@acme.com", is_primary=True)
    contact.refresh_from_db()
    assert contact.email_id == "jane@acme.com"


def test_primary_mobile_is_denormalised_onto_the_contact(contact):
    ContactPhone.objects.create(
        parent_contact=contact, phone="+15550001", is_primary_mobile_no=True
    )
    contact.refresh_from_db()
    assert contact.mobile_no == "+15550001"


def test_primary_phone_and_mobile_are_separate(contact):
    """``test_crm_deal.py:451-454`` sets the two flags independently."""
    ContactPhone.objects.create(parent_contact=contact, phone="+15550001", is_primary_mobile_no=True)
    ContactPhone.objects.create(parent_contact=contact, phone="+15550002", is_primary_phone=True)
    contact.refresh_from_db()
    assert contact.mobile_no == "+15550001"
    assert contact.phone == "+15550002"


def test_first_email_wins_when_none_is_flagged_primary(contact):
    ContactEmail.objects.create(parent_contact=contact, email_id="first@acme.com")
    ContactEmail.objects.create(parent_contact=contact, email_id="second@acme.com")
    contact.refresh_from_db()
    assert contact.email_id == "first@acme.com"


def test_removing_the_primary_email_clears_the_cache(contact):
    email = ContactEmail.objects.create(
        parent_contact=contact, email_id="jane@acme.com", is_primary=True
    )
    email.delete()
    contact.refresh_from_db()
    assert contact.email_id == ""


def test_contact_default_list_data_matches_the_override(contact):
    """Verbatim from ``crm/overrides/contact.py``."""
    data = registry.get_entry("Contact").default_list_data()
    assert [c["key"] for c in data["columns"]] == [
        "full_name",
        "email_id",
        "mobile_no",
        "company_name",
        "modified",
    ]
    assert data["rows"] == [
        "name",
        "full_name",
        "company_name",
        "email_id",
        "mobile_no",
        "modified",
        "image",
    ]


# --- ToDo backs assignment ----------------------------------------------------


def test_todo_statuses_match_frappe():
    values = [c[0] for c in ToDo._meta.get_field("status").choices]
    assert values == ["Open", "Closed", "Cancelled"]


def test_todo_allocated_to_is_a_user_fk(alice):
    todo = ToDo.objects.create(allocated_to=alice, reference_type="X", reference_name="Y")
    assert todo.allocated_to_id == alice.name


def test_todo_is_hash_named(alice):
    todo = ToDo.objects.create(allocated_to=alice)
    assert len(todo.name) == 10


# --- Email Template -----------------------------------------------------------


def test_email_template_takes_a_client_supplied_name(alice):
    with session_user(alice.name):
        template = EmailTemplate(name="Welcome", subject="Hi")
        template.save()
    assert template.name == "Welcome"


def test_email_template_default_list_data_matches_the_override():
    data = registry.get_entry("Email Template").default_list_data()
    assert [c["key"] for c in data["columns"]] == [
        "name",
        "subject",
        "enabled",
        "reference_doctype",
        "modified",
    ]


# --- Email Account ------------------------------------------------------------


def test_email_account_is_named_from_its_account_name(alice):
    with session_user(alice.name):
        account = EmailAccount.objects.create(
            email_account_name="Support", email_id="support@acme.com"
        )
    assert account.name == "Support"


def test_email_account_defaults_match_api_settings(alice):
    """``crm/api/settings.py:22-28`` relies on these defaults."""
    with session_user(alice.name):
        account = EmailAccount.objects.create(email_account_name="X")
    assert account.email_sync_option == "ALL"
    assert account.initial_sync_count == 100
    assert account.create_contact is True
    assert account.track_email_status is True
    assert account.use_tls is True
    assert account.use_imap is True


# --- Tag / File / Communication / Comment -------------------------------------


def test_tag_is_named_by_its_text(alice):
    with session_user(alice.name):
        tag = Tag(name="urgent")
        tag.save()
    assert tag.name == "urgent"


def test_file_records_what_it_is_attached_to(alice):
    with session_user(alice.name):
        f = File.objects.create(
            file_name="a.pdf", file_url="/files/a.pdf", attached_to_doctype="Comment",
            attached_to_name="c1",
        )
    assert f.attached_to_doctype == "Comment"


def test_communication_defaults_to_the_countable_type(alice):
    """``crm/api/doc.py:645-655`` counts ``communication_type="Communication"``."""
    with session_user(alice.name):
        c = Communication.objects.create(subject="Hello")
    assert c.communication_type == "Communication"


def test_comment_defaults_to_the_countable_type(alice):
    """``crm/api/doc.py:666`` counts ``comment_type="Comment"``."""
    with session_user(alice.name):
        c = Comment.objects.create(content="Hi")
    assert c.comment_type == "Comment"


# --- standard fields are present on every platform doctype --------------------


@pytest.mark.parametrize(
    "model", [Contact, ToDo, Communication, Comment, EmailTemplate, File, Tag, EmailAccount]
)
def test_platform_doctypes_carry_the_standard_fields(model):
    names = {f.name for f in model._meta.get_fields() if getattr(f, "concrete", False)}
    assert {"name", "owner", "modified_by", "creation", "modified", "idx", "docstatus"} <= names
    assert {"_assign", "_liked_by", "_comments", "_user_tags"} <= names


def test_user_is_deliberately_not_a_base_document():
    """Django requires AUTH_USER_MODEL to derive from AbstractBaseUser."""
    from frappe_core.models import BaseDocument

    assert not issubclass(User, BaseDocument)
    assert "_assign" not in {f.name for f in User._meta.get_fields()}
