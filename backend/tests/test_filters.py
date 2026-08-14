"""Acceptance criteria 4 and 5 - the filter grammar, ``@me``, and ILIKE.

PHASE_0_FOUNDATION.md section 5.
"""

import datetime

import pytest

from frappe_core.filters import (
    FilterError,
    _like_to_lookup,
    build_q,
    normalize_filters,
    resolve_me_tokens,
)
from frappe_core.query import fetch_rows
from frappe_core.session import session_user
from tests_support.models import Widget

pytestmark = pytest.mark.django_db


@pytest.fixture
def widgets(alice, bob):
    with session_user(alice.name):
        Widget.objects.create(
            widget_name="Alpha", status="Open", quantity=10, widget_owner=alice
        )
        Widget.objects.create(
            widget_name="BETA", status="Open", quantity=20, widget_owner=bob
        )
        Widget.objects.create(
            widget_name="gamma", status="Closed", quantity=30, widget_owner=alice
        )
        Widget.objects.create(
            widget_name="", status="Lost", quantity=None, widget_owner=None
        )
    return Widget.objects.all()


def names(rows):
    return sorted(r["widget_name"] for r in rows)


# --- input shapes -------------------------------------------------------------


def test_dict_shape_means_equals():
    assert normalize_filters({"status": "Open"}) == [("status", "=", "Open")]


def test_dict_operator_shape():
    assert normalize_filters({"status": ["in", ["Open", "Lost"]]}) == [
        ("status", "in", ["Open", "Lost"])
    ]


def test_four_tuple_shape_drops_the_doctype():
    assert normalize_filters([["CRM Lead", "status", "=", "Open"]]) == [
        ("status", "=", "Open")
    ]


def test_three_tuple_shape():
    assert normalize_filters([["status", "=", "Open"]]) == [("status", "=", "Open")]


def test_two_element_shape_means_equals():
    assert normalize_filters([["status", "Open"]]) == [("status", "=", "Open")]


def test_a_two_element_value_that_is_not_an_operator_stays_a_value():
    """``{"tags": ["a", "b"]}`` is an equality against a list, not an operator form."""
    assert normalize_filters({"tags": ["a", "b"]}) == [("tags", "=", ["a", "b"])]


def test_unknown_operator_is_rejected():
    with pytest.raises(FilterError, match="Unsupported filter operator"):
        build_q(Widget, [["status", "~=", "Open"]])


# --- criterion 4: @me in all three forms --------------------------------------


def test_me_resolves_in_dict_form(widgets, alice):
    with session_user(alice.name):
        rows = fetch_rows("Phase Zero Widget", fields=["widget_name"], filters={"widget_owner": "@me"})
    assert names(rows) == ["Alpha", "gamma"]


def test_me_resolves_in_operator_form(widgets, alice):
    with session_user(alice.name):
        rows = fetch_rows(
            "Phase Zero Widget",
            fields=["widget_name"],
            filters={"widget_owner": ["=", "@me"]},
        )
    assert names(rows) == ["Alpha", "gamma"]


def test_me_resolves_in_tuple_form(widgets, alice):
    with session_user(alice.name):
        rows = fetch_rows(
            "Phase Zero Widget",
            fields=["widget_name"],
            filters=[["Phase Zero Widget", "widget_owner", "=", "@me"]],
        )
    assert names(rows) == ["Alpha", "gamma"]


def test_me_resolves_inside_a_list_value(alice):
    with session_user(alice.name):
        assert resolve_me_tokens(["@me", "other@example.com"]) == [
            alice.name,
            "other@example.com",
        ]


def test_me_like_token_is_wrapped_in_percents(alice):
    with session_user(alice.name):
        assert resolve_me_tokens("%@me%") == f"%{alice.name}%"


def test_me_like_token_resolves_inside_a_list(alice):
    with session_user(alice.name):
        assert resolve_me_tokens(["%@me%"]) == [f"%{alice.name}%"]


def test_me_resolves_at_depth(alice):
    with session_user(alice.name):
        assert resolve_me_tokens(["in", ["@me", "x"]]) == ["in", [alice.name, "x"]]


def test_non_me_values_are_untouched(alice):
    with session_user(alice.name):
        assert resolve_me_tokens(["a", 1, None, True]) == ["a", 1, None, True]


# --- criterion 5: like is case-insensitive ------------------------------------


def test_like_is_case_insensitive(widgets):
    """Upstream runs MariaDB where LIKE ignores case; Postgres LIKE does not.

    ``%beta%`` must find ``BETA`` (PORT_PLAN.md section 10).
    """
    rows = fetch_rows(
        "Phase Zero Widget", fields=["widget_name"], filters={"widget_name": ["like", "%beta%"]}
    )
    assert names(rows) == ["BETA"]


def test_like_uppercase_pattern_finds_lowercase_value(widgets):
    rows = fetch_rows(
        "Phase Zero Widget", fields=["widget_name"], filters={"widget_name": ["like", "%GAMMA%"]}
    )
    assert names(rows) == ["gamma"]


def test_like_generates_case_insensitive_sql(widgets):
    """Prove the case-folding happens in SQL, not by luck in the fixture data.

    Django renders ``icontains`` on Postgres as ``UPPER(col) LIKE UPPER(pattern)``
    rather than the ``ILIKE`` operator. Both are case-insensitive; asserting on the
    literal keyword would test Django's codegen, so this asserts the property that
    matters - a bare, case-sensitive ``LIKE`` must not reach the database.
    """
    from frappe_core.query import build_list_queryset

    sql = str(
        build_list_queryset(
            "Phase Zero Widget", filters={"widget_name": ["like", "%beta%"]}
        ).query
    ).upper()
    assert "ILIKE" in sql or "UPPER(" in sql, sql
    assert "WIDGET_NAME\"::TEXT) LIKE UPPER" in sql or "ILIKE" in sql, sql


def test_not_like_is_also_case_insensitive(widgets):
    rows = fetch_rows(
        "Phase Zero Widget",
        fields=["widget_name"],
        filters={"widget_name": ["not like", "%beta%"]},
    )
    assert "BETA" not in names(rows)


@pytest.mark.parametrize(
    "pattern,expected_lookup,expected_operand",
    [
        ("%foo%", "icontains", "foo"),
        ("foo%", "istartswith", "foo"),
        ("%foo", "iendswith", "foo"),
        ("foo", "iexact", "foo"),
    ],
)
def test_like_wildcards_map_to_anchored_lookups(pattern, expected_lookup, expected_operand):
    """A raw ``icontains`` on ``%foo%`` would search for a literal percent sign."""
    assert _like_to_lookup(pattern) == (expected_lookup, expected_operand)


def test_like_with_an_interior_wildcard_falls_back_to_regex():
    lookup, operand = _like_to_lookup("a%b")
    assert lookup == "iregex"
    assert operand == "^a.*b$"


def test_like_anchored_prefix_matches(widgets):
    rows = fetch_rows(
        "Phase Zero Widget", fields=["widget_name"], filters={"widget_name": ["like", "alp%"]}
    )
    assert names(rows) == ["Alpha"]


# --- remaining operators ------------------------------------------------------


def test_equals(widgets):
    rows = fetch_rows("Phase Zero Widget", fields=["widget_name"], filters={"status": "Open"})
    assert names(rows) == ["Alpha", "BETA"]


def test_not_equals(widgets):
    rows = fetch_rows("Phase Zero Widget", fields=["widget_name"], filters={"status": ["!=", "Open"]})
    assert names(rows) == ["", "gamma"]


def test_greater_than(widgets):
    rows = fetch_rows("Phase Zero Widget", fields=["widget_name"], filters={"quantity": [">", 15]})
    assert names(rows) == ["BETA", "gamma"]


def test_less_than_or_equal(widgets):
    rows = fetch_rows("Phase Zero Widget", fields=["widget_name"], filters={"quantity": ["<=", 20]})
    assert names(rows) == ["Alpha", "BETA"]


def test_in(widgets):
    rows = fetch_rows(
        "Phase Zero Widget", fields=["widget_name"], filters={"status": ["in", ["Open", "Lost"]]}
    )
    assert names(rows) == ["", "Alpha", "BETA"]


def test_not_in(widgets):
    rows = fetch_rows(
        "Phase Zero Widget", fields=["widget_name"], filters={"status": ["not in", ["Open"]]}
    )
    assert names(rows) == ["", "gamma"]


def test_between(widgets):
    rows = fetch_rows(
        "Phase Zero Widget", fields=["widget_name"], filters={"quantity": ["between", [15, 30]]}
    )
    assert names(rows) == ["BETA", "gamma"]


def test_between_requires_two_bounds():
    with pytest.raises(FilterError, match="exactly two"):
        build_q(Widget, {"quantity": ["between", [1]]})


def test_is_set_excludes_null_and_empty_string(widgets):
    """Frappe emits ``ifnull(field, '') != ''`` - an empty string counts as unset."""
    rows = fetch_rows("Phase Zero Widget", fields=["widget_name"], filters={"widget_name": ["is", "set"]})
    assert names(rows) == ["Alpha", "BETA", "gamma"]


def test_is_not_set_includes_the_empty_string(widgets):
    rows = fetch_rows(
        "Phase Zero Widget", fields=["widget_name"], filters={"widget_name": ["is", "not set"]}
    )
    assert names(rows) == [""]


def test_is_set_on_a_nullable_number_tests_null_only(widgets):
    rows = fetch_rows("Phase Zero Widget", fields=["widget_name"], filters={"quantity": ["is", "not set"]})
    assert names(rows) == [""]


def test_is_rejects_a_bad_token():
    with pytest.raises(FilterError, match="'set' or 'not set'"):
        build_q(Widget, {"widget_name": ["is", "maybe"]})


def test_or_filters_are_combined_with_or(widgets):
    rows = fetch_rows(
        "Phase Zero Widget",
        fields=["widget_name"],
        or_filters={"status": "Closed", "quantity": ["=", 10]},
    )
    assert names(rows) == ["Alpha", "gamma"]


def test_filters_and_or_filters_are_anded_together(widgets):
    rows = fetch_rows(
        "Phase Zero Widget",
        fields=["widget_name"],
        filters={"status": "Open"},
        or_filters={"quantity": ["=", 10]},
    )
    assert names(rows) == ["Alpha"]


def test_foreign_key_filter_uses_the_raw_key(widgets, alice):
    rows = fetch_rows(
        "Phase Zero Widget", fields=["widget_name"], filters={"widget_owner": alice.name}
    )
    assert names(rows) == ["Alpha", "gamma"]


def test_like_on_a_json_column_matches(alice):
    """``_assign`` is a JSON list here but a LIKE'd JSON *string* upstream."""
    with session_user(alice.name):
        Widget.objects.create(widget_name="Assigned", _assign=[alice.name])
        Widget.objects.create(widget_name="Unassigned", _assign=[])
    rows = fetch_rows(
        "Phase Zero Widget", fields=["widget_name"], filters={"_assign": ["like", f"%{alice.name}%"]}
    )
    assert names(rows) == ["Assigned"]


def test_like_on_a_json_column_is_case_insensitive(alice):
    """Codex phase-0 finding 3.

    JSON containment (``__contains=[x]``) is case-*sensitive* on Postgres, whereas
    upstream LIKEs a JSON string column on MariaDB, where LIKE is not. Django renders
    ``icontains`` on a JSONField as ``UPPER(col::text) LIKE UPPER(...)``, which is
    upstream's behaviour exactly.
    """
    with session_user(alice.name):
        Widget.objects.create(widget_name="Assigned", _assign=["Alice@Example.com"])
    rows = fetch_rows(
        "Phase Zero Widget",
        fields=["widget_name"],
        filters={"_assign": ["like", "%alice@example.com%"]},
    )
    assert names(rows) == ["Assigned"]


def test_like_on_a_json_column_generates_case_insensitive_sql(alice):
    from frappe_core.query import build_list_queryset

    sql = str(
        build_list_queryset(
            "Phase Zero Widget", filters={"_assign": ["like", "%x%"]}
        ).query
    ).upper()
    assert "UPPER(" in sql and "::TEXT" in sql, sql


def test_not_like_on_a_json_column_excludes(alice):
    with session_user(alice.name):
        Widget.objects.create(widget_name="Assigned", _assign=[alice.name])
        Widget.objects.create(widget_name="Unassigned", _assign=[])
    rows = fetch_rows(
        "Phase Zero Widget",
        fields=["widget_name"],
        filters={"_assign": ["not like", f"%{alice.name}%"]},
    )
    assert "Assigned" not in names(rows)


def test_date_between(alice):
    with session_user(alice.name):
        Widget.objects.create(widget_name="early", due_date=datetime.date(2026, 1, 1))
        Widget.objects.create(widget_name="late", due_date=datetime.date(2026, 12, 1))
    rows = fetch_rows(
        "Phase Zero Widget",
        fields=["widget_name"],
        filters={"due_date": ["between", ["2026-01-01", "2026-06-01"]]},
    )
    assert names(rows) == ["early"]


def test_descendants_of_without_a_registered_resolver_is_an_error():
    """Phase 2 registers tree resolvers; until then the operator must fail loudly."""
    with pytest.raises(FilterError, match="tree resolver"):
        build_q(Widget, {"widget_owner": ["descendants of", "someone"]})
