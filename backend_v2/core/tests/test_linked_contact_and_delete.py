"""The shared actions' "remove contact" and linked-document delete (specs/CONTACTS.md §4
"Milestone 0"; temp A-42, PE-25, PE-26).

New tests on `tests_support`: no real resource opts in to these actions yet.
"""

import pytest

from core.mixins.linked import _clear_contact
from tests_support.models import (
    ContactHolder,
    ContactHolderRow,
    PointingDocument,
    StrayContact,
    Widget,
)
from tests_support.views import WidgetViewSet

pytestmark = pytest.mark.django_db

TEST_URLCONF = "config.test_urls"


def save(document, user):
    document.save(user=user)
    return document


@pytest.fixture
def target(alice):
    return save(Widget(widget_name="Target", widget_owner=alice), alice)


def unlink(client, target, items, **flags):
    return client.post(
        f"/api/v1/test-widgets/{target.pk}/linked-documents/", {"items": items, **flags}, format="json"
    )


def item(document):
    return {"doctype": document.DOCTYPE, "docname": document.pk}


# --- PE-25 -------------------------------------------------------------------------------


def test_remove_contact_clears_the_documents_own_field_and_table(alice, auth_api, target):
    holder = save(ContactHolder(widget=target, contact="Ada"), alice)
    for value in ("one", "two"):
        save(ContactHolderRow(holder=holder, value=value), alice)
    response = unlink(auth_api, target, [item(holder)], remove_contact=True)
    assert response.json() == {"message": "success"}
    holder.refresh_from_db()
    assert holder.contact is None
    assert not ContactHolderRow.objects.filter(holder=holder).exists()


def test_pe25_a_reverse_relation_called_contacts_is_not_the_documents_table(alice, auth_api, target):
    pointer = save(PointingDocument(widget=target), alice)
    strays = [save(StrayContact(pointer=pointer), alice) for _ in range(2)]
    response = unlink(auth_api, target, [item(pointer)], remove_contact=True)
    assert response.json() == {"message": "success"}
    assert StrayContact.objects.filter(pk__in=[stray.pk for stray in strays]).count() == 2


def test_pe25_the_helper_leaves_a_reverse_relation_alone(alice, target):
    pointer = save(PointingDocument(widget=target), alice)
    save(StrayContact(pointer=pointer), alice)
    _clear_contact(pointer, TEST_URLCONF)
    assert StrayContact.objects.filter(pointer=pointer).count() == 1


# --- PE-26 -------------------------------------------------------------------------------


def test_pe26_unlink_delete_skips_an_item_the_caller_may_not_delete(alice, auth_api, target):
    locked = save(ContactHolder(widget=target, locked=True), alice)
    open_holder = save(ContactHolder(widget=target), alice)
    response = unlink(auth_api, target, [item(locked), item(open_holder)], delete=True)
    assert response.json() == {"message": "success"}
    locked.refresh_from_db()
    assert locked.widget_id is None  # its link is still cleared
    assert not ContactHolder.objects.filter(pk=open_holder.pk).exists()


def test_pe26_bulk_delete_linked_skips_an_item_the_caller_may_not_delete(alice, auth_api, target):
    locked = save(ContactHolder(widget=target, locked=True), alice)
    response = auth_api.post(
        "/api/v1/test-widgets/bulk-delete/", {"items": [target.pk], "delete_linked": True}, format="json"
    )
    assert response.json() == {"message": "success"}
    assert not Widget.objects.filter(pk=target.pk).exists()
    locked.refresh_from_db()
    assert locked.widget_id is None


def test_bulk_delete_linked_still_deletes_what_the_caller_may_delete(alice, auth_api, target):
    holder = save(ContactHolder(widget=target), alice)
    response = auth_api.post(
        "/api/v1/test-widgets/bulk-delete/", {"items": [target.pk], "delete_linked": True}, format="json"
    )
    assert response.json() == {"message": "success"}
    assert not ContactHolder.objects.filter(pk=holder.pk).exists()


def test_the_widget_resource_does_not_remove_contacts_on_bulk_delete():
    assert WidgetViewSet.bulk_delete_remove_contact is False
