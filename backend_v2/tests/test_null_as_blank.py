import pytest

from tests_support.models import Widget


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"
NOTES = "Keep this value"


@pytest.fixture
def widget(alice):
    document = Widget(
        widget_name="Logo",
        status="Open",
        notes=NOTES,
        widget_owner=alice,
    )
    document.save(user=alice)
    return document


def test_null_clears_a_text_field(auth_api, widget):
    response = auth_api.patch(
        f"{WIDGETS}{widget.pk}/", {"notes": None}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["notes"] == ""
    widget.refresh_from_db()
    assert widget.notes == ""


def test_null_empties_text_and_select_fields_on_the_document_route(auth_api, widget):
    response = auth_api.patch(
        f"{WIDGETS}{widget.pk}/",
        {"widget_name": None, "status": None, "notes": None},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    widget.refresh_from_db()
    assert (widget.widget_name, widget.status, widget.notes) == ("", "", "")


def test_a_field_left_out_is_untouched(auth_api, widget):
    response = auth_api.patch(
        f"{WIDGETS}{widget.pk}/", {"status": None}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    widget.refresh_from_db()
    assert widget.status == ""
    assert widget.notes == NOTES
