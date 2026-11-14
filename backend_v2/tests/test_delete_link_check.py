import pytest

from tests_support.models import DynamicReference, PointingDocument, Widget


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


def save(document, user):
    document.save(user=user)
    return document


@pytest.fixture
def widget(alice):
    return save(Widget(widget_name="Linked", widget_owner=alice), alice)


def refusal(response, message):
    assert response.status_code == 417, response.content[:300]
    assert response.json()["exc_type"] == "LinkExistsError"
    assert response.json()["message"] == message


def test_delete_is_refused_while_a_static_link_remains(auth_api, widget, alice):
    pointer = save(PointingDocument(widget=widget), alice)
    response = auth_api.delete(f"{WIDGETS}{widget.pk}/")
    refusal(
        response,
        "Cannot delete or cancel because Foundation Widget "
        f"{widget.pk} is linked with Foundation Pointing {pointer.pk}",
    )
    assert Widget.objects.filter(pk=widget.pk).exists()


def test_delete_is_refused_while_a_dynamic_link_remains(auth_api, widget, alice):
    reference = save(
        DynamicReference(
            reference_doctype="Foundation Widget", reference_name=widget.pk
        ),
        alice,
    )
    response = auth_api.delete(f"{WIDGETS}{widget.pk}/")
    refusal(
        response,
        "Cannot delete or cancel because Foundation Widget "
        f"{widget.pk} is linked with Foundation Dynamic Reference {reference.pk}",
    )
    assert Widget.objects.filter(pk=widget.pk).exists()


def test_cancelled_dynamic_link_does_not_hide_a_later_active_link(
    auth_api, widget, alice
):
    save(
        DynamicReference(
            name="a-cancelled",
            reference_doctype="Foundation Widget",
            reference_name=widget.pk,
            docstatus=2,
        ),
        alice,
    )
    active = save(
        DynamicReference(
            name="b-active",
            reference_doctype="Foundation Widget",
            reference_name=widget.pk,
        ),
        alice,
    )

    response = auth_api.delete(f"{WIDGETS}{widget.pk}/")

    refusal(
        response,
        "Cannot delete or cancel because Foundation Widget "
        f"{widget.pk} is linked with Foundation Dynamic Reference {active.pk}",
    )
    assert Widget.objects.filter(pk=widget.pk).exists()


def test_cancelled_dynamic_link_alone_does_not_block_delete(auth_api, widget, alice):
    save(
        DynamicReference(
            reference_doctype="Foundation Widget",
            reference_name=widget.pk,
            docstatus=2,
        ),
        alice,
    )

    response = auth_api.delete(f"{WIDGETS}{widget.pk}/")

    assert response.status_code == 200
    assert response.json() == {"message": None}
    assert not Widget.objects.filter(pk=widget.pk).exists()


def test_a_reference_created_by_another_user_still_blocks_delete(
    auth_api, widget, bob
):
    reference = save(
        DynamicReference(
            reference_doctype="Foundation Widget", reference_name=widget.pk
        ),
        bob,
    )
    response = auth_api.delete(f"{WIDGETS}{widget.pk}/")
    refusal(
        response,
        "Cannot delete or cancel because Foundation Widget "
        f"{widget.pk} is linked with Foundation Dynamic Reference {reference.pk}",
    )
