from decimal import Decimal

import pytest

from core.exceptions import ValidationError
from core.query import (
    by_name,
    coerce_offset,
    coerce_page_length,
    fetch_rows,
    resolve_fields,
    resolve_group_by,
    resolve_order_by,
)
from tests_support.models import AutoIncrementDocumentFixture, SecuredDocument, Widget

pytestmark = pytest.mark.django_db


def test_by_name_returns_none_queryset_for_an_impossible_integer_key():
    assert not by_name(AutoIncrementDocumentFixture, "not-an-integer").exists()


def test_fields_default_and_star_include_only_readable_concrete_fields(alice):
    default = resolve_fields(SecuredDocument, None, user=alice)
    star = resolve_fields(SecuredDocument, ["*"], user=alice)
    assert default == star
    assert "secret" not in default
    assert "encrypted_secret" not in default
    assert "manager_note" not in default
    assert "name" in default


@pytest.mark.parametrize("fields", [["secret"], ["manager_note"]])
def test_hidden_fields_are_refused_in_fields(alice, fields):
    with pytest.raises(ValidationError, match="Field '.*' is not readable"):
        resolve_fields(SecuredDocument, fields, user=alice)


def test_unknown_field_is_refused_in_fields(alice):
    with pytest.raises(ValidationError, match="Unknown field 'missing' for this document type"):
        resolve_fields(Widget, ["missing"], user=alice)


def test_field_allowlist_uses_hidden_wording_for_a_real_column(alice):
    with pytest.raises(ValidationError, match="Field 'status' is not readable"):
        resolve_fields(Widget, ["status"], user=alice, selectable={"name"})


def test_fields_deduplicate_without_relation_traversal(alice):
    assert resolve_fields(Widget, ["name", "name"], user=alice) == ["name"]
    with pytest.raises(ValidationError, match="Unknown field"):
        resolve_fields(Widget, ["widget_owner__email"], user=alice)


def test_order_by_accepts_comma_clauses_and_table_prefixes(alice):
    assert resolve_order_by(
        Widget,
        "`tabFoundation Widget`.modified desc, Foundation.widget_name ASC",
        user=alice,
    ) == ["-modified", "widget_name"]


def test_order_by_hidden_unknown_malformed_and_allowlist_refusals(alice):
    with pytest.raises(ValidationError, match="Cannot order by 'secret'"):
        resolve_order_by(SecuredDocument, "secret desc", user=alice)
    with pytest.raises(ValidationError, match="Cannot order by unknown field 'missing'"):
        resolve_order_by(Widget, "missing", user=alice)
    with pytest.raises(ValidationError, match="Cannot parse sort clause 'name sideways'"):
        resolve_order_by(Widget, "name sideways", user=alice)
    with pytest.raises(ValidationError, match="Cannot order by 'status'"):
        resolve_order_by(Widget, "status", user=alice, sortable={"name"})


def test_group_by_accepts_prefix_and_refuses_hidden_unknown_and_allowlist(alice):
    assert resolve_group_by(Widget, "`tabWidget`.status", user=alice) == "status"
    with pytest.raises(ValidationError, match="Cannot group by 'secret'"):
        resolve_group_by(SecuredDocument, "secret", user=alice)
    with pytest.raises(ValidationError, match="Cannot group by unknown field 'missing'"):
        resolve_group_by(Widget, "missing", user=alice)
    with pytest.raises(ValidationError, match="Cannot group by 'status'"):
        resolve_group_by(Widget, "status", user=alice, sortable={"name"})


@pytest.mark.parametrize("value,expected", [(None, 20), ("", 20), (0, 0), (500, 500), (501, 500)])
def test_page_length_defaults_zero_and_cap(value, expected):
    assert coerce_page_length(value) == expected


def test_negative_and_invalid_page_length_messages():
    with pytest.raises(ValidationError, match="Page length cannot be negative"):
        coerce_page_length(-1)
    with pytest.raises(ValidationError, match="Invalid page length 'many'"):
        coerce_page_length("many")


@pytest.mark.parametrize("value,expected", [(None, 0), ("", 0), (-1, 0), (3, 3)])
def test_offset_coercion(value, expected):
    assert coerce_offset(value) == expected


def test_invalid_offset_message():
    with pytest.raises(ValidationError, match="Invalid offset 'later'"):
        coerce_offset("later")


def test_fetch_rows_keeps_decimal_numeric_and_caches_json_text(alice):
    Widget.objects.create_for_user(
        user=alice,
        widget_name="one",
        amount=Decimal("1000.000000"),
        _assign=[alice.name],
        _liked_by=[],
        _comments=[],
    )
    row = fetch_rows(
        Widget.objects.all(),
        user=alice,
        fields=["amount", "_assign", "_liked_by", "_comments"],
    )[0]
    assert row["amount"] == Decimal("1000.000000")
    assert row["_assign"] == f'["{alice.name}"]'
    assert row["_liked_by"] == "[]"
    assert row["_comments"] == "[]"


def test_fetch_rows_applies_row_rule_queryset_before_client_filter(alice):
    for label, status in (("visible", "Open"), ("hidden", "Open"), ("other", "Closed")):
        Widget.objects.create_for_user(user=alice, widget_name=label, status=status)
    base = Widget.objects.exclude(widget_name="hidden")
    rows = fetch_rows(base, user=alice, fields=["widget_name"], filters={"status": "Open"})
    assert rows == [{"widget_name": "visible"}]


def test_fetch_rows_paginates_and_zero_means_no_limit(alice):
    for label in ("a", "b", "c"):
        Widget.objects.create_for_user(user=alice, widget_name=label)
    base = Widget.objects.order_by("widget_name")
    assert [row["widget_name"] for row in fetch_rows(base, user=alice, fields=["widget_name"], limit_start=1, limit_page_length=1)] == ["b"]
    assert [row["widget_name"] for row in fetch_rows(base, user=alice, fields=["widget_name"], limit_start=1, limit_page_length=0)] == ["b", "c"]
