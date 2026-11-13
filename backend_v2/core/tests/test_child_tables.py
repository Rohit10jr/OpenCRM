import pytest
from django.db.models.signals import post_save, pre_save

from core.exceptions import MandatoryError
from tests_support.models import Widget, WidgetNote, WidgetRow
from tests_support.serializers import WidgetSerializer


pytestmark = pytest.mark.django_db


def test_document_doctype_key_is_on_documents_and_child_rows(alice):
    serializer = WidgetSerializer(
        data={
            "widget_name": "Inline rows",
            "rows": [{"value": "FK row"}],
            "poly_rows": [{"value": "generic row"}],
        },
        context={"user": alice},
    )
    assert serializer.is_valid(), serializer.errors
    widget = serializer.save(user=alice)

    data = WidgetSerializer(widget, context={"user": alice}).data

    assert data["doctype"] == "Foundation Widget"
    assert data["rows"][0]["doctype"] == "Foundation Widget Row"
    assert data["poly_rows"][0]["doctype"] == "Foundation Widget Note"


def test_child_rows_are_replaced_wholesale_in_the_old_write_order(alice):
    events = []

    def parent_saved(sender, instance, **kwargs):
        events.append("parent")

    def child_saved(sender, instance, **kwargs):
        events.append("child")

    pre_save.connect(parent_saved, sender=Widget)
    post_save.connect(child_saved, sender=WidgetRow)
    post_save.connect(child_saved, sender=WidgetNote)
    try:
        serializer = WidgetSerializer(
            data={
                "rows": [{"value": "first"}],
                "poly_rows": [{"value": "poly first"}],
            },
            context={"user": alice},
        )
        assert serializer.is_valid(), serializer.errors
        widget = serializer.save()
        assert events == ["parent", "child", "child", "parent"]

        events.clear()
        serializer = WidgetSerializer(
            widget,
            data={
                "rows": [{"value": "replacement"}],
                "poly_rows": [{"value": "poly replacement"}],
            },
            partial=True,
            context={"user": alice},
        )
        assert serializer.is_valid(), serializer.errors
        serializer.save()
        assert events == ["child", "child", "parent"]
    finally:
        pre_save.disconnect(parent_saved, sender=Widget)
        post_save.disconnect(child_saved, sender=WidgetRow)
        post_save.disconnect(child_saved, sender=WidgetNote)

    assert list(widget.rows.values_list("value", flat=True)) == ["replacement"]
    assert list(
        WidgetNote.objects.filter(
            parent=widget.pk, parenttype=Widget.DOCTYPE
        ).values_list("value", flat=True)
    ) == ["poly replacement"]


def test_child_rows_refuse_a_missing_mandatory_value_with_old_message(alice):
    serializer = WidgetSerializer(
        data={"rows": [{}]}, context={"user": alice}
    )
    assert serializer.is_valid(), serializer.errors

    with pytest.raises(MandatoryError) as caught:
        serializer.save()

    assert caught.value.messages == [
        "Error: <strong>Foundation Widget Row</strong> Row #1: "
        "Value missing for: Value"
    ]
    assert not Widget.objects.exists()


def test_child_rows_polymorphic_rows_cascade_with_the_parent(alice):
    serializer = WidgetSerializer(
        data={"poly_rows": [{"value": "remove me"}]},
        context={"user": alice},
    )
    assert serializer.is_valid(), serializer.errors
    widget = serializer.save()

    widget.delete()

    assert not WidgetNote.objects.exists()
