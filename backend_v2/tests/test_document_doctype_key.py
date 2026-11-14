import pytest

from tests_support.models import Widget


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


@pytest.fixture
def widget(alice):
    document = Widget(widget_name="Original", widget_owner=alice)
    document.save(user=alice)
    return document


def test_a_document_and_its_child_rows_name_their_doctype(auth_api, widget):
    response = auth_api.patch(
        f"{WIDGETS}{widget.pk}/",
        {
            "rows": [{"value": "FK row"}],
            "poly_rows": [{"value": "generic row"}],
        },
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    data = response.json()["message"]
    assert data["doctype"] == "Foundation Widget"
    assert data["rows"][0]["doctype"] == "Foundation Widget Row"
    assert data["poly_rows"][0]["doctype"] == "Foundation Widget Note"


def test_the_document_route_names_it_too(auth_api, widget):
    response = auth_api.get(f"{WIDGETS}{widget.pk}/")
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["doctype"] == "Foundation Widget"


def test_duplicate_posts_the_fetched_document_back_and_gets_a_copy(
    auth_api, widget
):
    auth_api.patch(
        f"{WIDGETS}{widget.pk}/",
        {"rows": [{"value": "copied row"}]},
        format="json",
    )
    fetched = auth_api.get(f"{WIDGETS}{widget.pk}/").json()["message"]
    response = auth_api.post(
        WIDGETS,
        {**fetched, "widget_name": "Copy"},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    created = response.json()["message"]
    assert created["name"] != widget.pk
    assert created["doctype"] == "Foundation Widget"
    assert created["widget_name"] == "Copy"
    assert [row["value"] for row in created["rows"]] == ["copied row"]
    assert Widget.objects.get(pk=widget.pk).rows.count() == 1
