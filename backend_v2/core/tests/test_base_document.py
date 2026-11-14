import pytest
from django.db.models.deletion import ProtectedError

from core.exceptions import (
    InvalidEmailAddressError,
    LinkValidationError,
    api_exception_handler,
    link_exists_error,
)
from tests_support.models import (
    EmailDocument,
    PointingDocument,
    SeriesDocument,
    TextLinkDocument,
    Widget,
)

pytestmark = pytest.mark.django_db


def save(document, user):
    document.save(user=user)
    return document


def test_passed_user_is_stamped_on_create_and_update(administrator, alice):
    document = save(SeriesDocument(label="first"), administrator)
    assert document.owner == administrator
    assert document.modified_by == administrator
    document.label = "second"
    document.save(user=alice)
    document.refresh_from_db()
    assert document.owner == administrator
    assert document.modified_by == alice


def test_save_without_a_user_is_a_type_error():
    with pytest.raises(TypeError, match="user"):
        SeriesDocument(label="x").save()


@pytest.mark.parametrize("user", [None, ""])
def test_save_refuses_an_empty_user(user):
    with pytest.raises(TypeError, match=r"^`user` is required to save a document$"):
        SeriesDocument(label="x").save(user=user)


@pytest.mark.parametrize("user", [None, ""])
def test_create_for_user_refuses_an_empty_user(user):
    with pytest.raises(TypeError, match=r"^`user` is required to save a document$"):
        SeriesDocument.objects.create_for_user(user=user, label="x")


def test_email_fields_use_the_old_validation_message(administrator):
    with pytest.raises(
        InvalidEmailAddressError,
        match=r"^not an email is not a valid Email Address$",
    ):
        save(EmailDocument(recipients="not an email"), administrator)


def test_email_field_accepts_display_names_and_multiple_addresses(administrator):
    document = save(
        EmailDocument(recipients="Ada <ada@example.com>, bob@example.com"),
        administrator,
    )
    assert document.recipients == "Ada <ada@example.com>, bob@example.com"


def test_fetch_from_overwrites_the_target_on_every_save(administrator):
    widget = save(Widget(widget_name="One", status="Open"), administrator)
    pointer = save(
        PointingDocument(widget=widget, widget_status="Caller value"), administrator
    )
    assert pointer.widget_status == "Open"
    widget.status = "Closed"
    widget.save(user=administrator)
    pointer.widget_status = "Stale"
    pointer.save(user=administrator)
    assert pointer.widget_status == "Closed"


def test_text_link_refuses_a_missing_document(administrator):
    with pytest.raises(
        LinkValidationError,
        match=r"^Could not find Widget: missing$",
    ):
        save(TextLinkDocument(widget_name="missing"), administrator)


def test_text_link_allows_a_declared_dangling_document(administrator):
    document = save(
        TextLinkDocument(audit_widget_name="missing"), administrator
    )
    document.refresh_from_db()
    assert document.audit_widget_name == "missing"


def test_text_link_rewrites_to_stored_spelling(administrator):
    widget = save(Widget(widget_name="One"), administrator)
    document = save(
        TextLinkDocument(widget_name=widget.name.lower()), administrator
    )
    assert document.widget_name == widget.name


def test_protected_delete_becomes_link_exists_error(administrator):
    widget = save(Widget(widget_name="One"), administrator)
    pointer = save(PointingDocument(widget=widget), administrator)
    with pytest.raises(ProtectedError) as caught:
        widget.delete()
    error = link_exists_error(caught.value)
    assert error.message == (
        f"Cannot delete or cancel because Foundation Widget {widget.name} "
        f"is linked with Foundation Pointing {pointer.name}"
    )
    response = api_exception_handler(caught.value, {})
    assert response.status_code == 417
    assert response.data["exc_type"] == "LinkExistsError"
    assert response.data["message"] == error.message
