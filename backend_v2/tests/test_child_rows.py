import pytest

from core.exceptions import ValidationError
from tests_support.models import Widget, WidgetRow


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


def save(document, user):
    document.save(user=user)
    return document


@pytest.fixture
def widget(alice):
    return save(Widget(widget_name="Parent", widget_owner=alice), alice)


def patch_rows(client, widget, rows):
    return client.patch(f"{WIDGETS}{widget.pk}/", {"rows": rows}, format="json")


def test_a_child_link_may_name_its_document(auth_api, widget, alice):
    target = save(Widget(widget_name="Target", widget_owner=alice), alice)
    response = patch_rows(
        auth_api, widget, [{"value": "linked", "related_widget": target.pk}]
    )
    assert response.status_code == 200, response.content[:300]
    row = WidgetRow.objects.get(parent=widget)
    assert row.related_widget_id == target.pk
    assert response.json()["message"]["rows"][0]["related_widget"] == target.pk


def test_a_second_child_row_may_name_its_link(auth_api, widget, alice):
    target = save(Widget(widget_name="Other target", widget_owner=alice), alice)
    response = patch_rows(
        auth_api,
        widget,
        [
            {"value": "plain"},
            {"value": "linked", "related_widget": target.pk},
        ],
    )
    assert response.status_code == 200, response.content[:300]
    assert WidgetRow.objects.get(parent=widget, idx=2).related_widget_id == target.pk


def test_a_link_to_a_missing_document_is_a_link_validation_error(
    auth_api, widget, alice
):
    target = save(Widget(widget_name="Existing", widget_owner=alice), alice)
    assert patch_rows(
        auth_api, widget, [{"value": "old", "related_widget": target.pk}]
    ).status_code == 200

    response = patch_rows(
        auth_api, widget, [{"value": "new", "related_widget": "missing"}]
    )
    assert response.status_code == 417
    assert response.json()["exc_type"] == "LinkValidationError"
    assert response.json()["message"] == "Could not find Row #1: Related Widget: missing"
    assert list(widget.rows.values_list("value", flat=True)) == ["old"]


def test_a_row_missing_a_mandatory_value_is_a_mandatory_error(auth_api, widget):
    response = patch_rows(auth_api, widget, [{}])
    assert response.status_code == 417
    assert response.json()["exc_type"] == "MandatoryError"
    assert response.json()["messages"] == [
        "Error: <strong>Foundation Widget Row</strong> Row #1: Value missing for: Value"
    ]


def test_every_missing_value_is_reported(auth_api, widget):
    response = patch_rows(auth_api, widget, [{}, {"value": "kept"}, {}])
    assert response.status_code == 417
    assert response.json()["messages"] == [
        "Error: <strong>Foundation Widget Row</strong> Row #1: Value missing for: Value",
        "Error: <strong>Foundation Widget Row</strong> Row #3: Value missing for: Value",
    ]


def test_rows_are_seen_in_the_same_update_response(auth_api, widget):
    response = patch_rows(auth_api, widget, [{"value": "same response"}])
    assert response.status_code == 200
    assert response.json()["message"]["rows"][0]["value"] == "same response"


def test_rows_sent_on_create_are_seen_by_the_first_save(auth_api):
    response = auth_api.post(
        WIDGETS,
        {"widget_name": "Created", "rows": [{"value": "first save"}]},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    assert response.json()["message"]["rows"][0]["value"] == "first save"


def test_values_kept_by_rows_survive_the_parent_save(
    auth_api, widget, monkeypatch
):
    original_save = WidgetRow.save

    def save_and_update_parent(row, *args, **kwargs):
        result = original_save(row, *args, **kwargs)
        total = sum(
            int(value) for value in row.parent.rows.values_list("value", flat=True)
        )
        Widget.objects.filter(pk=row.parent_id).update(quantity=total)
        return result

    monkeypatch.setattr(WidgetRow, "save", save_and_update_parent)
    response = patch_rows(auth_api, widget, [{"value": "2"}, {"value": "3"}])
    assert response.status_code == 200
    assert response.json()["message"]["quantity"] == 5
    widget.refresh_from_db()
    assert widget.quantity == 5


def test_a_refused_parent_takes_its_new_rows_back(
    auth_api, widget, alice, monkeypatch
):
    assert patch_rows(auth_api, widget, [{"value": "old"}]).status_code == 200
    original_save = Widget.save

    def refuse_after_rows(document, *args, **kwargs):
        if document.pk == widget.pk and document.rows.filter(value="new").exists():
            raise ValidationError("Refused parent")
        return original_save(document, *args, **kwargs)

    monkeypatch.setattr(Widget, "save", refuse_after_rows)
    response = patch_rows(auth_api, widget, [{"value": "new"}])
    assert response.status_code == 417
    assert list(widget.rows.values_list("value", flat=True)) == ["old"]
