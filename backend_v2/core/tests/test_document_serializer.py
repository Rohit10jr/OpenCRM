from decimal import Decimal

import pytest

from core.exceptions import DuplicateEntryError
from tests_support.models import (
    FieldDocument,
    PromptDocument,
    SecuredDocument,
    Widget,
)
from tests_support.serializers import (
    FieldDocumentSerializer,
    PromptDocumentSerializer,
    SecuredDocumentSerializer,
    WidgetSerializer,
)


pytestmark = pytest.mark.django_db


def _widget(user, **values):
    widget = Widget(**values)
    widget.save(user=user)
    return widget


def test_wire_shapes_render_caches_as_json_strings(alice):
    widget = _widget(alice, _assign=["alice@example.com"], _comments=[])

    data = WidgetSerializer(widget, context={"user": alice}).data

    assert data["_assign"] == '["alice@example.com"]'
    assert data["_liked_by"] == "[]"
    assert data["_comments"] == "[]"


def test_null_as_blank_converts_writable_text_null_to_empty_string(alice):
    serializer = WidgetSerializer(
        data={"widget_name": None, "status": None},
        context={"user": alice},
    )

    assert serializer.is_valid(), serializer.errors
    widget = serializer.save()

    assert widget.widget_name == ""
    assert widget.status == ""


def test_wire_shapes_render_document_decimals_as_padded_strings(alice):
    widget = _widget(alice, amount=Decimal("1000"))

    data = WidgetSerializer(widget, context={"user": alice}).data

    assert data["amount"] == "1000.000000"


def test_field_security_hides_restricted_field_only_from_sales_user(
    alice, make_user
):
    manager = make_user(
        "manager@example.com", first_name="Manager", roles=["Sales Manager"]
    )
    document = SecuredDocument(manager_note="managers only")
    document.save(user=manager)

    sales_data = SecuredDocumentSerializer(
        document, context={"user": alice}
    ).data
    manager_data = SecuredDocumentSerializer(
        document, context={"user": manager}
    ).data

    assert "manager_note" not in sales_data
    assert manager_data["manager_note"] == "managers only"
    assert "secret" not in manager_data
    assert "encrypted_secret" not in manager_data


def test_field_security_drops_privileged_write_from_sales_user(alice):
    serializer = SecuredDocumentSerializer(
        data={"manager_value": "not allowed"}, context={"user": alice}
    )

    assert serializer.is_valid(), serializer.errors
    document = serializer.save()

    assert document.manager_value == ""


@pytest.mark.parametrize(
    ("model", "serializer_class", "existing_values", "attempted_values", "name"),
    [
        (
            FieldDocument,
            FieldDocumentSerializer,
            {"title": "Taken Field Name"},
            {"title": "Taken Field Name"},
            "Taken Field Name",
        ),
        (
            PromptDocument,
            PromptDocumentSerializer,
            {"name": "Taken Prompt Name"},
            {"name": "Taken Prompt Name"},
            "Taken Prompt Name",
        ),
    ],
)
def test_name_lookup_duplicate_name_sentence_for_field_and_prompt_naming(
    alice,
    model,
    serializer_class,
    existing_values,
    attempted_values,
    name,
):
    existing = model(**existing_values)
    existing.save(user=alice)
    serializer = serializer_class(data=attempted_values, context={"user": alice})
    assert serializer.is_valid(), serializer.errors

    with pytest.raises(DuplicateEntryError) as caught:
        serializer.save()

    assert caught.value.message == (
        f"{model.DOCTYPE} <strong>{name}</strong> already exists"
    )
    assert caught.value.title == "Duplicate Name"


def test_document_serializer_without_a_user_is_refused(alice):
    widget = _widget(alice)

    with pytest.raises(TypeError, match="serializer context"):
        WidgetSerializer(widget).data

    serializer = WidgetSerializer(data={"widget_name": "missing actor"})
    with pytest.raises(TypeError, match="serializer context"):
        serializer.is_valid()
