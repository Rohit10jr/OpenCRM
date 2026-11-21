"""A delete is refused while a text Link or a PROTECT foreign key names the record, before
the dynamic links (specs/CONTACTS.md §11.3; owner, temp A-48 6.3, A-74; upstream v15
`frappe/model/delete_doc.py:141-153`). New: the old backend checks dynamic links only.
"""

import pytest

from configuration.models import Currency, SystemSettings
from tests_support.models import DynamicReference, TextLinkDocument, Widget

pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


def widget(user, name):
    row = Widget(name=name, widget_name=name, widget_owner=user)
    row.save(user=user)
    return row


def test_a_text_link_refuses_the_record_route_delete(auth_api, alice):
    target = widget(alice, "W-1")
    pointer = TextLinkDocument(widget_name="W-1")
    pointer.save(user=alice)

    response = auth_api.delete(f"{WIDGETS}{target.pk}/")

    assert response.status_code == 417
    assert response.json()["exc_type"] == "LinkExistsError"
    assert response.json()["message"] == (
        f"Cannot delete or cancel because Foundation Widget W-1 is linked with "
        f"Foundation Text Link {pointer.pk}"
    )
    assert Widget.objects.filter(pk="W-1").exists()


def test_it_deletes_once_the_text_link_is_cleared(auth_api, alice):
    target = widget(alice, "W-1")
    pointer = TextLinkDocument(widget_name="W-1")
    pointer.save(user=alice)
    TextLinkDocument.objects.filter(pk=pointer.pk).update(widget_name="")

    assert auth_api.delete(f"{WIDGETS}{target.pk}/").status_code == 200
    assert not Widget.objects.filter(pk="W-1").exists()


def test_the_static_link_is_answered_before_the_dynamic_one(auth_api, alice):
    target = widget(alice, "W-1")
    pointer = TextLinkDocument(widget_name="W-1")
    pointer.save(user=alice)
    DynamicReference(reference_doctype="Foundation Widget", reference_name="W-1").save(user=alice)

    response = auth_api.delete(f"{WIDGETS}{target.pk}/")

    assert response.status_code == 417
    assert "Foundation Text Link" in response.json()["message"]


def test_bulk_delete_is_refused_too(auth_api, alice):
    widget(alice, "W-1")
    TextLinkDocument(audit_widget_name="W-1").save(user=alice)
    response = auth_api.post(
        f"{WIDGETS}bulk-delete/", {"items": ["W-1"]}, format="json"
    )
    assert response.status_code == 417
    assert Widget.objects.filter(pk="W-1").exists()


def test_a_currency_in_use_gets_the_disable_sentence(administrator, api_as):
    """Currency has `enabled`; System Settings' `currency` is a text Link to it."""
    settings_row = SystemSettings.objects.get(pk="System Settings")
    SystemSettings.objects.filter(pk=settings_row.pk).update(currency="INR")

    response = api_as(administrator).delete("/api/v1/currencies/INR/")

    assert response.status_code == 417
    assert response.json()["message"] == "You can disable this Currency instead of deleting it."
    assert Currency.objects.filter(pk="INR").exists()


def test_a_currency_not_in_use_is_deleted(administrator, api_as):
    SystemSettings.objects.update(currency="")
    from configuration.models import FCRMSettings

    FCRMSettings.objects.update(currency="")
    assert api_as(administrator).delete("/api/v1/currencies/XAF/").status_code == 200
    assert not Currency.objects.filter(pk="XAF").exists()
