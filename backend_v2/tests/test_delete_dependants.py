import pytest

from tests_support.models import Widget, WidgetNote


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


@pytest.fixture
def widget_with_dependants(auth_api):
    response = auth_api.post(
        WIDGETS,
        {
            "widget_name": "Doomed",
            "poly_rows": [{"value": "remove"}],
        },
        format="json",
    )
    return Widget.objects.get(pk=response.json()["message"]["name"])


def test_delete_takes_polymorphic_children_with_the_parent(
    auth_api, widget_with_dependants
):
    response = auth_api.delete(f"{WIDGETS}{widget_with_dependants.pk}/")
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": None}
    assert not Widget.objects.filter(pk=widget_with_dependants.pk).exists()
    assert not WidgetNote.objects.filter(parent=widget_with_dependants.pk).exists()


def test_the_orm_delete_path_cleans_up_too(widget_with_dependants):
    name = widget_with_dependants.pk
    widget_with_dependants.delete()
    assert not WidgetNote.objects.filter(parent=name).exists()
