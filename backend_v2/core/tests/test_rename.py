"""Port the generic rename contract from ``backend/tests/test_rename.py``.

Cases deferred with their real doctypes: Contact email/phone rows and Organization are
CONTACTS; Lead unique columns and Deal links are SALES; ToDo, Comment and Notification
dynamic links are ACTIVITIES. The tests here exercise each generic reference shape on
``tests_support`` models instead.
"""

import pytest

from core.models import Version
from tests_support.models import (
    DynamicReference,
    PointingDocument,
    TextLinkDocument,
    Widget,
    WidgetNote,
    WidgetRow,
)


pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


def save(document, user):
    document.save(user=user)
    return document


def widget(user, name, **values):
    return save(Widget(name=name, widget_name=name, widget_owner=user, **values), user)


def rename(client, url_name, new_name, **extra):
    return client.post(
        f"{WIDGETS}{url_name}/rename/",
        {"new_name": new_name, **extra},
        format="json",
    )


def test_permission_refusal_is_417_even_when_the_record_is_list_invisible(
    auth_api, alice, bob
):
    hidden = widget(bob, "Hidden Widget", status="Locked")

    response = rename(auth_api, hidden.pk, "Renamed Widget")

    assert response.status_code == 417
    assert response.json()["message"] == (
        f"You need write permission on {Widget.DOCTYPE} {hidden.pk} to rename"
    )


def test_rename_repoints_every_old_reference_shape_without_deleting_rows(
    auth_api, alice
):
    target = widget(alice, "Old Widget")
    parent = widget(alice, "Row Parent")
    pointer = save(PointingDocument(widget=target), alice)
    dynamic = save(
        DynamicReference(
            reference_doctype=Widget.DOCTYPE,
            reference_name=target.pk,
        ),
        alice,
    )
    row = save(
        WidgetRow(parent=parent, value="row", related_widget=target), alice
    )
    poly_row = save(
        WidgetNote(
            parent=target.pk,
            parenttype=Widget.DOCTYPE,
            parentfield="poly_rows",
            value="note",
        ),
        alice,
    )
    version = save(
        Version(ref_doctype=Widget.DOCTYPE, docname=target.pk, data="{}"), alice
    )
    text_link = save(TextLinkDocument(widget_name=target.pk), alice)

    response = rename(auth_api, target.pk, "New Widget")

    assert response.status_code == 200
    assert response.json() == {"message": "New Widget"}
    assert Widget.objects.filter(pk="New Widget").exists()
    assert not Widget.objects.filter(pk="Old Widget").exists()
    pointer.refresh_from_db()
    dynamic.refresh_from_db()
    row.refresh_from_db()
    poly_row.refresh_from_db()
    version.refresh_from_db()
    text_link.refresh_from_db()
    assert pointer.widget_id == "New Widget"
    assert (dynamic.reference_doctype, dynamic.reference_name) == (
        Widget.DOCTYPE,
        "New Widget",
    )
    assert row.related_widget_id == "New Widget"
    assert (poly_row.parenttype, poly_row.parent) == (
        Widget.DOCTYPE,
        "New Widget",
    )
    assert (version.ref_doctype, version.docname) == (
        Widget.DOCTYPE,
        "New Widget",
    )
    assert text_link.widget_name == "New Widget"  # PE-5
    assert PointingDocument.objects.filter(pk=pointer.pk).exists()
    assert DynamicReference.objects.filter(pk=dynamic.pk).exists()
    assert WidgetRow.objects.filter(pk=row.pk).exists()
    assert WidgetNote.objects.filter(pk=poly_row.pk).exists()
    assert Version.objects.filter(pk=version.pk).exists()


def test_rename_repoints_declared_text_links_only_where_they_match(
    auth_api, alice
):
    """PE-5: the old backend kept the old name here (no old test covered it)."""
    target = widget(alice, "Mr")
    other = widget(alice, "Mrs")
    matching = save(
        TextLinkDocument(widget_name=target.pk, audit_widget_name=target.pk), alice
    )
    unrelated = save(TextLinkDocument(widget_name=other.pk), alice)

    response = rename(auth_api, target.pk, "Mr.")

    assert response.status_code == 200
    matching.refresh_from_db()
    unrelated.refresh_from_db()
    assert (matching.widget_name, matching.audit_widget_name) == ("Mr.", "Mr.")
    assert unrelated.widget_name == "Mrs"


def test_rename_resolves_a_text_link_label_regardless_of_case(
    auth_api, alice, monkeypatch
):
    """core.links accepts any case in the declared label, so rename must too (A-20)."""
    monkeypatch.setattr(
        TextLinkDocument,
        "TEXT_LINK_FIELDS",
        {"widget_name": ("tests_support.widget", "Widget")},
    )
    target = widget(alice, "Lower Label")
    document = save(TextLinkDocument(widget_name=target.pk), alice)

    response = rename(auth_api, target.pk, "Lower Label Renamed")

    assert response.status_code == 200
    document.refresh_from_db()
    assert document.widget_name == "Lower Label Renamed"


def test_rename_parks_and_restores_a_non_key_unique_value(auth_api, alice):
    original = widget(alice, "Unique Widget", external_id="external-1")

    response = rename(auth_api, original.pk, "Unique Widget Renamed")

    assert response.status_code == 200
    renamed = Widget.objects.get(pk="Unique Widget Renamed")
    assert renamed.external_id == "external-1"


def test_renamed_row_keeps_its_stamps(auth_api, alice):
    original = widget(alice, "Stamped Widget")

    rename(auth_api, original.pk, "Stamped Widget Renamed")

    renamed = Widget.objects.get(pk="Stamped Widget Renamed")
    assert renamed.owner_id == original.owner_id
    assert renamed.modified_by_id == original.modified_by_id
    assert renamed.creation == original.creation
    assert renamed.modified == original.modified


def test_old_name_and_doctype_body_inputs_are_ignored(auth_api, alice):
    original = widget(alice, "URL Widget")

    response = rename(
        auth_api,
        original.pk,
        "Body Inputs Ignored",
        old_name="wrong old name",
        doctype="Wrong DocType",
        surplus="ignored",
    )

    assert response.json() == {"message": "Body Inputs Ignored"}
    assert Widget.objects.filter(pk="Body Inputs Ignored").exists()


def test_old_and_new_names_may_contain_slashes(auth_api, alice):
    original = widget(alice, "R/GA")

    response = rename(auth_api, original.pk, "N/EW")

    assert response.status_code == 200
    assert response.json() == {"message": "N/EW"}
    assert Widget.objects.filter(pk="N/EW").exists()


def test_merge_refusal_runs_before_missing_and_uses_the_old_message(auth_api):
    response = rename(auth_api, "Missing", "Other", merge=True)

    assert response.status_code == 417
    assert response.json()["message"] == "Merging documents is not supported"


def test_missing_refusal_runs_before_same_name(auth_api):
    response = rename(auth_api, "Missing", "Missing")

    assert response.status_code == 417
    assert response.json()["message"] == (
        "Can't rename Missing to Missing because Missing doesn't exist."
    )


def test_same_name_refusal_runs_before_taken(auth_api, alice):
    original = widget(alice, "Same Widget")

    response = rename(auth_api, original.pk, original.pk)

    assert response.status_code == 417
    assert response.json()["message"] == (
        "No changes made because old and new name are the same."
    )


def test_taken_refusal_runs_before_write_permission(auth_api, alice, bob):
    original = widget(bob, "Locked Widget", status="Locked")
    widget(alice, "Taken Widget")

    response = rename(auth_api, original.pk, "Taken Widget")

    assert response.status_code == 417
    assert response.json()["message"] == (
        f"Another {Widget.DOCTYPE} with name Taken Widget exists, select another name"
    )


def test_write_refusal_runs_before_name_validation(auth_api, bob):
    original = widget(bob, "Locked Invalid Widget", status="Locked")

    response = rename(auth_api, original.pk, "<invalid>")

    assert response.status_code == 417
    assert response.json()["message"] == (
        f"You need write permission on {Widget.DOCTYPE} {original.pk} to rename"
    )


def test_new_name_is_validated_last(auth_api, alice):
    original = widget(alice, "Invalid Target Widget")

    response = rename(auth_api, original.pk, "<invalid>")

    assert response.status_code == 409
    assert response.json()["message"] == (
        "Name cannot contain special characters like '<', '>'"
    )


# --- PE-31 (owner, 20 Nov 2026): the naming field follows the new name ---------------------


def test_pe31_a_field_named_document_takes_the_new_name_in_its_field(administrator):
    from core.rename import rename_document
    from tests_support.models import FieldDocument

    save(FieldDocument(title="Old Title"), administrator)
    assert rename_document(FieldDocument, "Old Title", "New Title") == "New Title"

    renamed = FieldDocument.objects.get(pk="New Title")
    assert renamed.title == "New Title"
    assert not FieldDocument.objects.filter(pk="Old Title").exists()


def test_pe31_a_unique_naming_field_is_not_parked(administrator):
    """The copy already holds the new name there, so no blank stand-in is written: a
    row whose unique naming field is already blank does not collide (A-71 finding 6)."""
    from configuration.models import Currency
    from core.rename import rename_document

    Currency(currency_name="TST").save(user=administrator)
    Currency.objects.bulk_create([Currency(name="BLANK", currency_name="")])

    assert rename_document(Currency, "TST", "TSX") == "TSX"
    assert Currency.objects.get(pk="TSX").currency_name == "TSX"


def test_pe31_a_document_not_named_by_a_field_keeps_its_fields(auth_api, alice):
    """Widget's name is not taken from `widget_name`, so the rename leaves it."""
    widget(alice, "W-1")
    response = rename(auth_api, "W-1", "W-2")
    assert response.status_code == 200, response.content[:300]
    assert Widget.objects.get(pk="W-2").widget_name == "W-1"
