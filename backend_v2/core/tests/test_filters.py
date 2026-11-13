import datetime

import pytest

from core.exceptions import FilterError
from core.filters import (
    _like_to_lookup,
    apply_filters,
    build_q,
    normalize_filters,
    resolve_me_tokens,
)
from tests_support.models import SecuredDocument, Widget

pytestmark = pytest.mark.django_db


@pytest.fixture
def widgets(alice, bob):
    values = (
        ("Alpha", "Open", 10, alice),
        ("BETA", "Open", 20, bob),
        ("gamma", "Closed", 30, alice),
        ("", "Lost", None, None),
    )
    for label, status, quantity, owner in values:
        Widget.objects.create_for_user(
            user=alice,
            widget_name=label,
            status=status,
            quantity=quantity,
            widget_owner=owner,
        )
    return Widget.objects.all()


def names(rows):
    return sorted(row["widget_name"] for row in rows)


def fetch_rows(queryset, *, user, fields, filters=None, or_filters=None, **kwargs):
    """Keep the filter rewrite independent of the query module built next."""
    queryset = apply_filters(
        queryset, filters=filters, or_filters=or_filters, user=user
    )
    return list(queryset.values(*fields))


@pytest.mark.parametrize(
    "raw,expected",
    [
        ({"status": "Open"}, [("status", "=", "Open")]),
        ({"status": ["in", ["Open"]]}, [("status", "in", ["Open"])]),
        ([["CRM Lead", "status", "=", "Open"]], [("status", "=", "Open")]),
        ([["status", "=", "Open"]], [("status", "=", "Open")]),
        ([["status", "Open"]], [("status", "=", "Open")]),
        ({"tags": ["a", "b"]}, [("tags", "=", ["a", "b"])]),
    ],
)
def test_filter_input_shapes(raw, expected):
    assert normalize_filters(raw) == expected


@pytest.mark.parametrize(
    "raw,message",
    [
        ("bad", "Unsupported filter shape: str"),
        (["bad"], "Filter entry must be a list, got str"),
        ([["one"]], "Filter entry must have 2-4 elements, got 1"),
    ],
)
def test_shape_errors_are_filter_errors(raw, message, alice):
    with pytest.raises(FilterError, match=message):
        build_q(Widget, raw, user=alice)


def test_unknown_operator_lists_supported_operators(alice):
    with pytest.raises(FilterError) as caught:
        build_q(Widget, [["status", "~=", "Open"]], user=alice)
    assert str(caught.value).startswith("Unsupported filter operator '~='. Supported: =, !=")


def test_unknown_field_is_rejected(alice):
    with pytest.raises(FilterError, match="Unknown field 'missing' for this document type"):
        build_q(Widget, [["missing", "=", "x"]], user=alice)


def test_operator_is_trimmed_and_case_insensitive(alice):
    assert normalize_filters([["status", " IN ", ["Open"]]]) == [("status", "in", ["Open"])]


def test_me_tokens_resolve_recursively(alice):
    value = {"outer": ["@me", ["%@me%"]]}
    assert resolve_me_tokens(value, alice) == {
        "outer": [alice.name, [f"%{alice.name}%"]]
    }


def test_me_in_nested_or_filters(widgets, alice):
    rows = fetch_rows(
        widgets,
        user=alice,
        fields=["widget_name"],
        or_filters=[["widget_owner", "in", ["@me", "nobody@example.com"]]],
    )
    assert names(rows) == ["Alpha", "gamma"]


@pytest.mark.parametrize(
    "filters",
    [
        {"widget_owner": "@me"},
        {"widget_owner": ["=", "@me"]},
        [["Foundation Widget", "widget_owner", "=", "@me"]],
    ],
)
def test_me_resolves_in_every_filter_shape(widgets, alice, filters):
    rows = fetch_rows(widgets, user=alice, fields=["widget_name"], filters=filters)
    assert names(rows) == ["Alpha", "gamma"]


def test_non_me_values_are_untouched(alice):
    assert resolve_me_tokens(["a", 1, None, True], alice) == ["a", 1, None, True]


@pytest.mark.parametrize(
    "pattern,lookup,operand",
    [("%foo%", "icontains", "foo"), ("foo%", "istartswith", "foo"), ("%foo", "iendswith", "foo"), ("foo", "iexact", "foo")],
)
def test_like_wildcard_mapping(pattern, lookup, operand):
    assert _like_to_lookup(pattern) == (lookup, operand)


def test_interior_like_wildcards_become_anchored_regex():
    assert _like_to_lookup("a%b_c") == ("iregex", "^a.*b.c$")


def test_like_case_folding_and_anchored_prefix_run_in_sql(widgets, alice):
    upper = fetch_rows(
        widgets, user=alice, fields=["widget_name"],
        filters={"widget_name": ["like", "%GAMMA%"]},
    )
    prefix = fetch_rows(
        widgets, user=alice, fields=["widget_name"],
        filters={"widget_name": ["like", "alp%"]},
    )
    assert names(upper) == ["gamma"]
    assert names(prefix) == ["Alpha"]
    sql = str(widgets.filter(build_q(Widget, {"widget_name": ["like", "%beta%"]}, user=alice)).query).upper()
    assert "UPPER(" in sql or "ILIKE" in sql


@pytest.mark.parametrize(
    "filters,expected",
    [
        ({"status": "Open"}, ["Alpha", "BETA"]),
        ({"status": ["!=", "Open"]}, ["", "gamma"]),
        ({"quantity": [">", 15]}, ["BETA", "gamma"]),
        ({"quantity": ["<", 20]}, ["Alpha"]),
        ({"quantity": [">=", 20]}, ["BETA", "gamma"]),
        ({"quantity": ["<=", 20]}, ["Alpha", "BETA"]),
        ({"status": ["in", "Open, Lost"]}, ["", "Alpha", "BETA"]),
        ({"status": ["not in", ["Open"]]}, ["", "gamma"]),
        ({"quantity": ["between", [15, 30]]}, ["BETA", "gamma"]),
        ({"widget_name": ["like", "%beta%"]}, ["BETA"]),
        ({"widget_name": ["not like", "%beta%"]}, ["", "Alpha", "gamma"]),
        ({"widget_name": ["is", "set"]}, ["Alpha", "BETA", "gamma"]),
        ({"widget_name": ["is", "not set"]}, [""]),
        ({"quantity": ["is", "not set"]}, [""]),
    ],
)
def test_filter_operators(widgets, alice, filters, expected):
    rows = fetch_rows(widgets, user=alice, fields=["widget_name"], filters=filters, limit_page_length=0)
    assert names(rows) == sorted(expected)


def test_in_requires_a_sequence(alice):
    with pytest.raises(FilterError, match="Operator 'in' expects a list, got int"):
        build_q(Widget, {"status": ["in", 3]}, user=alice)


def test_between_requires_exactly_two_values(alice):
    with pytest.raises(FilterError, match="Operator 'between' expects exactly two values"):
        build_q(Widget, {"quantity": ["between", [1]]}, user=alice)


def test_is_rejects_an_unknown_token(alice):
    with pytest.raises(FilterError, match="Operator 'is' expects 'set' or 'not set', got 'maybe'"):
        build_q(Widget, {"notes": ["is", "maybe"]}, user=alice)


def test_filters_and_or_filters_are_anded(widgets, alice):
    rows = fetch_rows(
        widgets,
        user=alice,
        fields=["widget_name"],
        filters={"status": "Open"},
        or_filters={"quantity": 10, "widget_name": "no"},
    )
    assert names(rows) == ["Alpha"]


def test_or_filters_are_combined_with_or(widgets, alice):
    rows = fetch_rows(
        widgets, user=alice, fields=["widget_name"],
        or_filters={"status": "Closed", "quantity": 10},
    )
    assert names(rows) == ["Alpha", "gamma"]


def test_foreign_key_filter_uses_raw_key(widgets, alice):
    rows = fetch_rows(widgets, user=alice, fields=["widget_name"], filters={"widget_owner": "@me"})
    assert names(rows) == ["Alpha", "gamma"]


def test_like_on_json_list_is_case_insensitive(alice):
    Widget.objects.create_for_user(user=alice, widget_name="Assigned", _assign=["Alice@Example.com"])
    rows = fetch_rows(
        Widget.objects.all(), user=alice, fields=["widget_name"],
        filters={"_assign": ["like", "%alice@example.com%"]},
    )
    assert names(rows) == ["Assigned"]


def test_not_like_on_json_list_excludes_and_uses_case_insensitive_sql(alice):
    Widget.objects.create_for_user(user=alice, widget_name="Assigned", _assign=[alice.name])
    Widget.objects.create_for_user(user=alice, widget_name="Unassigned", _assign=[])
    condition = build_q(Widget, {"_assign": ["like", f"%{alice.name}%"]}, user=alice)
    sql = str(Widget.objects.filter(condition).query).upper()
    assert "UPPER(" in sql and "::TEXT" in sql
    rows = fetch_rows(
        Widget.objects.all(), user=alice, fields=["widget_name"],
        filters={"_assign": ["not like", f"%{alice.name}%"]},
    )
    assert names(rows) == ["Unassigned"]


def test_dates_accept_between_values(alice):
    Widget.objects.create_for_user(user=alice, widget_name="early", due_date=datetime.date(2026, 1, 1))
    Widget.objects.create_for_user(user=alice, widget_name="late", due_date=datetime.date(2026, 12, 1))
    rows = fetch_rows(
        Widget.objects.all(), user=alice, fields=["widget_name"],
        filters={"due_date": ["between", ["2026-01-01", "2026-06-01"]]},
    )
    assert names(rows) == ["early"]


@pytest.mark.parametrize("value,expected", [("$ 500,000.00", 500000), ("abc", 0), (700000, 700000)])
def test_numeric_filter_values_are_coerced(alice, value, expected):
    Widget.objects.create_for_user(user=alice, widget_name="match", amount=expected)
    rows = fetch_rows(Widget.objects.all(), user=alice, fields=["widget_name"], filters={"amount": value})
    assert names(rows) == ["match"]


def test_numeric_lists_and_comparisons_are_coerced(alice):
    for label, amount in (("five", 500000), ("seven", 700000)):
        Widget.objects.create_for_user(user=alice, widget_name=label, amount=amount)
    assert names(fetch_rows(Widget.objects.all(), user=alice, fields=["widget_name"], filters={"amount": [">", "$ 600,000"]})) == ["seven"]
    assert names(fetch_rows(Widget.objects.all(), user=alice, fields=["widget_name"], filters={"amount": ["in", ["$ 500,000", "$ 700,000"]]})) == ["five", "seven"]


def test_like_on_numeric_and_text_columns_is_not_numeric_coerced(alice):
    Widget.objects.create_for_user(user=alice, widget_name="seven", amount=700000, status="Qualification")
    numeric = fetch_rows(
        Widget.objects.all(), user=alice, fields=["widget_name"],
        filters={"amount": ["like", "%7000%"]},
    )
    text = fetch_rows(
        Widget.objects.all(), user=alice, fields=["widget_name"],
        filters={"status": "Qualification"},
    )
    assert names(numeric) == ["seven"]
    assert names(text) == ["seven"]


@pytest.mark.parametrize("operator,value", [("=", "x"), ("like", "S%"), ("in", ["x"]), ("!=", "x"), ("is", "set")])
def test_hidden_field_is_unfilterable_through_every_operator(alice, operator, value):
    with pytest.raises(FilterError, match="Cannot filter on 'secret'"):
        build_q(SecuredDocument, [["secret", operator, value]], user=alice)


def test_filter_allowlist_refusal_does_not_reveal_column(alice):
    with pytest.raises(FilterError, match="Cannot filter on 'status'"):
        build_q(Widget, {"status": "Open"}, user=alice, filterable={"widget_name"})
