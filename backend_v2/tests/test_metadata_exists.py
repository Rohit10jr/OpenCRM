"""What exists for the metadata calls, beyond today's serializers (A-36 findings 1 and 6).

New: a child table declared in any form `core.children` accepts (a tuple, a bare label,
or the parent model's POLYMORPHIC_CHILD_TABLES) exists when its parent is served; and a
child whose parent's bundle leaves it out answers for itself.
"""

import pytest

from configuration import metadata
from tests_support.models import Widget, WidgetNote, WidgetRow

pytestmark = pytest.mark.django_db


def _routed(monkeypatch, serializer_tables, polymorphic=None):
    serializer = type("S", (), {"CHILD_TABLES": serializer_tables})
    viewset = type("V", (), {"serializer_class": serializer})
    monkeypatch.setattr(metadata, "routed_rule_map", lambda: {Widget: viewset})
    if polymorphic is not None:
        monkeypatch.setattr(Widget, "POLYMORPHIC_CHILD_TABLES", polymorphic, raising=False)


def test_a_tuple_declaration_makes_its_child_exist(monkeypatch):
    _routed(monkeypatch, {"rows": ("tests_support.WidgetRow", "parent")})
    assert WidgetRow in metadata._served_children()


def test_a_bare_label_declaration_makes_its_child_exist_and_does_not_500(monkeypatch):
    """A bare label names a child with a single link to its parent."""
    from configuration.models import CRMDropdownItem, FCRMSettings

    serializer = type("S", (), {"CHILD_TABLES": {"dropdown_items": "configuration.CRMDropdownItem"}})
    viewset = type("V", (), {"serializer_class": serializer})
    monkeypatch.setattr(metadata, "routed_rule_map", lambda: {FCRMSettings: viewset})
    assert CRMDropdownItem in metadata._served_children()


def test_a_polymorphic_child_exists(monkeypatch):
    _routed(monkeypatch, {}, polymorphic={"poly_rows": "tests_support.WidgetNote"})
    assert WidgetNote in metadata._served_children()


def test_a_child_left_out_of_its_parents_bundle_answers_for_itself(auth_api, monkeypatch):
    """Simulates a parent whose Table field the caller may not read: the parent's bundle
    omits the child, so getdoctype falls back to the child's own bundle."""
    real = metadata.get_meta_bundle

    def parent_without_child(doctype, model, user):
        bundle = real(doctype, model, user)
        return [doc for doc in bundle if doc["name"] != "CRM Dropdown Item"] if doctype == "FCRM Settings" else bundle

    monkeypatch.setattr(metadata, "get_meta_bundle", parent_without_child)
    body = auth_api.get("/api/v1/meta/doctype/", {"doctype": "CRM Dropdown Item", "with_parent": 1}).json()
    assert [doc["name"] for doc in body["docs"]] == ["CRM Dropdown Item"]
    assert "parent_dt" not in body
