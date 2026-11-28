"""The shared actions' "remove contact" and linked-document delete (specs/CONTACTS.md §4
"Milestone 0"; temp A-42, PE-25, PE-26).

New tests on `tests_support`: no real resource opts in to these actions yet.
"""

import pytest

from core.mixins.linked import _clear_contact
from tests_support.models import (
    ContactHolder,
    ContactHolderRow,
    HolderGuard,
    NotNullContactHolder,
    PointingDocument,
    PolyContactHolder,
    PolyContactRow,
    SingletonDocument,
    StrayContact,
    TreeItem,
    Widget,
)
from tests_support import models as fixtures
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


# --- A-45: "may delete" is what the record route asks ------------------------------------


def test_a_delete_rule_that_depends_on_the_user(alice, administrator, api_as, target):
    """The same locked holder: Alice may not delete it, Administrator may."""
    locked = save(ContactHolder(widget=target, locked=True), alice)
    unlink(api_as(alice), target, [item(locked)], delete=True)
    assert ContactHolder.objects.filter(pk=locked.pk).exists()
    unlink(api_as(administrator), target, [item(locked)], delete=True)
    assert not ContactHolder.objects.filter(pk=locked.pk).exists()


def test_the_record_route_asks_the_same_question(alice, administrator, api_as, target):
    locked = save(ContactHolder(widget=None, locked=True), alice)
    url = f"/api/v1/test-contact-holders/{locked.pk}/"
    assert api_as(alice).delete(url).status_code == 403
    assert api_as(administrator).delete(url).status_code == 200


def test_a_rule_answering_none_allows_the_delete(alice, auth_api, target):
    holder = save(ContactHolder(widget=target), alice)  # its delete rule answers None
    unlink(auth_api, target, [item(holder)], delete=True)
    assert not ContactHolder.objects.filter(pk=holder.pk).exists()


def test_a_settings_record_is_never_deleted_as_a_linked_item(administrator, api_as, target):
    settings_record = SingletonDocument.load(user=administrator)
    response = unlink(api_as(administrator), target, [item(settings_record)], delete=True)
    assert response.json() == {"message": "success"}
    assert SingletonDocument.objects.filter(pk=settings_record.pk).exists()


def test_a_row_rules_only_item_is_never_deleted(alice, administrator, api_as, target):
    tree = save(fixtures.TestTree(name="root"), administrator)
    tree_item = save(TreeItem(name="leaf", tree=tree, widget=target), administrator)
    unlink(api_as(administrator), target, [item(tree_item)], delete=True)
    assert TreeItem.objects.filter(pk=tree_item.pk).exists()


def test_an_item_the_caller_may_not_write_is_left_as_it_is(alice, auth_api, target):
    frozen = save(ContactHolder(widget=target, frozen=True), alice)
    unlink(auth_api, target, [item(frozen)], delete=True)
    frozen.refresh_from_db()
    assert frozen.widget_id == target.pk


def test_an_item_another_row_protects_is_skipped_and_the_rest_is_kept(alice, auth_api, target):
    guarded = save(ContactHolder(widget=target), alice)
    save(HolderGuard(holder=guarded), alice)
    other = save(ContactHolder(widget=target), alice)
    response = unlink(auth_api, target, [item(guarded), item(other)], delete=True)
    assert response.json() == {"message": "success"}
    guarded.refresh_from_db()
    assert guarded.widget_id is None  # its link is cleared, and that is kept
    assert not ContactHolder.objects.filter(pk=other.pk).exists()


def test_pe25_a_polymorphic_contacts_table_is_the_documents_own(alice, auth_api, target):
    holder = save(PolyContactHolder(widget=target), alice)
    save(PolyContactRow(parent=holder.pk, parenttype=holder.DOCTYPE, parentfield="contacts", value="x"), alice)
    unlink(auth_api, target, [item(holder)], remove_contact=True)
    assert not PolyContactRow.objects.filter(parent=holder.pk).exists()


def test_pe25_a_contact_column_that_cannot_be_empty_is_left(alice, auth_api, target):
    holder = save(NotNullContactHolder(widget=target), alice)
    response = unlink(auth_api, target, [item(holder)], remove_contact=True)
    assert response.json() == {"message": "success"}
    holder.refresh_from_db()
    assert holder.contact == "kept"
