import json
from datetime import date, datetime
from decimal import Decimal

import pytest

from crm_app.conditions import (
    ConditionError,
    document_values,
    evaluate,
    evaluate_safely,
    is_empty,
)
from crm_app.models import CRMLead, CRMLeadStatus
from frappe_core.session import session_user


OPERATOR_MAP = {
    "equals": "==",
    "=": "==",
    "==": "==",
    "!=": "!=",
    "not equals": "!=",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
    "in": "in",
    "not in": "not in",
    "like": "like",
    "not like": "not like",
    "is": "is",
    "is not": "is not",
    "between": "between",
}


def _js_string(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, list):
        return ",".join(_js_string(item) for item in value)
    return str(value)


def upstream_expression(conditions):
    """Test-only port of ``convertToConditions``, including its quoting defects."""

    def process(condition):
        if isinstance(condition, str):
            return condition.lower()
        if isinstance(condition, list):
            if condition and isinstance(condition[0], list):
                return f"({upstream_expression(condition)})"

            field, operator, value = condition
            op = OPERATOR_MAP.get(operator.lower(), operator)
            text = _js_string(value)
            if op in {"==", "!="} and text.lower() in {"yes", "no"}:
                check = text.lower() == "yes"
                if op == "!=":
                    check = not check
                return field if check else f"not {field}"
            if op == "is" and text.lower() == "set":
                return field
            if (op == "is" and text.lower() == "not set") or (
                op == "is not" and text.lower() == "set"
            ):
                return f"not {field}"
            if op == "like":
                return f'({field} and "{text}" in {field})'
            if op == "not like":
                return f'({field} and "{text}" not in {field})'
            if op == "between" and isinstance(value, str) and "," in value:
                start, end = (part.strip() for part in value.split(",")[:2])
                return f'({field} >= "{start}" and {field} <= "{end}")'
            if op in {"in", "not in"}:
                source = value if isinstance(value, list) else text.split(",")
                items = ", ".join(f'"{_js_string(item).strip()}"' for item in source)
                return f"({field} and {field} {op} [{items}])"
            if isinstance(value, str):
                value_string = f'"{value.replace(chr(34), chr(92) + chr(34))}"'
            elif isinstance(value, (int, float, bool)) and value is not None:
                value_string = text
            elif value is None:
                return f"not {field}" if op in {"==", "is"} else field
            else:
                escaped = text.replace('"', '\\"')
                value_string = f'"{escaped}"'
            return f"{field} {op} {value_string}"
        return ""

    return " ".join(process(condition) for condition in conditions)


def upstream_answer(conditions, doc):
    expression = upstream_expression(conditions)
    return bool(eval(expression, {"__builtins__": {}}, doc))  # noqa: S307 - test oracle only


@pytest.mark.parametrize(
    ("condition", "doc"),
    [
        (["text", "equals", "alpha"], {"text": "alpha"}),
        (["number", "=", 4], {"number": 4}),
        (["number", "==", 4], {"number": 3}),
        (["text", "!=", "alpha"], {"text": "beta"}),
        (["text", "not equals", "alpha"], {"text": "alpha"}),
        (["number", "<", 4], {"number": 3}),
        (["number", "<=", 4], {"number": 4}),
        (["number", ">", 4], {"number": 5}),
        (["number", ">=", 4], {"number": 4}),
        (["text", "in", " alpha, beta "], {"text": "beta"}),
        (["text", "in", ["alpha", 2]], {"text": "2"}),
        (["text", "not in", "alpha,beta"], {"text": "gamma"}),
        (["text", "in", "alpha,beta"], {"text": ""}),
        (["text", "like", "pha"], {"text": "alpha"}),
        (["text", "not like", "z"], {"text": "alpha"}),
        (["text", "not like", "z"], {"text": ""}),
        (["flag", "is", "set"], {"flag": "value"}),
        (["flag", "is", "not set"], {"flag": ""}),
        (["flag", "is not", "set"], {"flag": ""}),
        (["flag", "==", "YeS"], {"flag": 1}),
        (["flag", "==", "NO"], {"flag": 0}),
        (["flag", "!=", "yes"], {"flag": 0}),
        (["flag", "!=", "no"], {"flag": 1}),
        (["flag", "==", None], {"flag": ""}),
        (["flag", "is", None], {"flag": None}),
        (["flag", "!=", None], {"flag": "value"}),
        (["flag", "between", None], {"flag": "value"}),
        (["text", "between", " a, c "], {"text": "b"}),
        (["text", "EQUALS", "alpha"], {"text": "alpha"}),
    ],
)
def test_each_editor_operator_matches_the_upstream_expression(condition, doc):
    conditions = [condition]
    assert evaluate(conditions, doc) is upstream_answer(conditions, doc)


def test_json_text_is_accepted():
    conditions = [["status", "equals", "New"]]
    assert evaluate(json.dumps(conditions), {"status": "New"}) is True


def test_and_binds_more_tightly_than_or():
    conditions = [
        ["a", "==", 1],
        "OR",
        ["b", "==", 1],
        "AnD",
        ["c", "==", 1],
    ]
    doc = {"a": 1, "b": 0, "c": 0}
    assert evaluate(conditions, doc) is True
    assert evaluate(conditions, doc) is upstream_answer(conditions, doc)


def test_nested_group_is_a_bracketed_subexpression():
    conditions = [
        [["a", "==", 1], "or", ["b", "==", 1]],
        "and",
        ["c", "==", 1],
    ]
    doc = {"a": 1, "b": 0, "c": 0}
    assert evaluate(conditions, doc) is False
    assert evaluate(conditions, doc) is upstream_answer(conditions, doc)


@pytest.mark.parametrize("empty", [None, "", "   ", [], "[]"])
def test_empty_condition_is_exposed_to_the_caller(empty):
    assert is_empty(empty) is True


def test_evaluate_does_not_choose_a_meaning_for_an_empty_condition():
    with pytest.raises(ConditionError, match="empty"):
        evaluate([], {})


def test_between_accepts_the_two_item_list_the_editor_stores():
    conditions = [["close_date", "between", ["2026-01-01", "2026-01-31"]]]
    assert evaluate(conditions, {"close_date": "2026-01-15"}) is True
    with pytest.raises(SyntaxError):
        upstream_answer(conditions, {"close_date": "2026-01-15"})


@pytest.mark.parametrize(
    ("actual", "operator", "expected", "answer"),
    [
        (date(2026, 10, 20), "==", "2026-10-20", True),
        (date(2026, 10, 20), ">", "2026-10-19", True),
        (datetime(2026, 10, 20, 12, 30), "==", "2026-10-20", True),
        (datetime(2026, 10, 20, 12, 30), "<", "2026-10-20T13:00:00", True),
    ],
)
def test_date_values_are_compared_as_dates(actual, operator, expected, answer):
    assert evaluate([["when", operator, expected]], {"when": actual}) is answer


@pytest.mark.parametrize(
    ("actual", "bounds"),
    [
        (date(2026, 1, 15), ["2026-01-01", "2026-01-31"]),
        (datetime(2026, 1, 15, 12), ["2026-01-01", "2026-01-31"]),
        (
            datetime(2026, 1, 15, 12),
            ["2026-01-15T11:00:00", "2026-01-15T13:00:00"],
        ),
    ],
)
def test_between_coerces_date_and_datetime_bounds(actual, bounds):
    assert evaluate([["when", "between", bounds]], {"when": actual}) is True


def test_a_stored_datetime_is_read_in_the_sites_time_zone(settings):
    """Stored datetimes are aware UTC; the editor's text is the site's local time.

    21:30 UTC on 20 Oct is 03:00 on 21 Oct in Kolkata (+05:30): the local date is the
    21st, and a local "02:00" bound is before it."""
    from zoneinfo import ZoneInfo

    settings.TIME_ZONE = "Asia/Kolkata"
    stored = datetime(2026, 10, 20, 21, 30, tzinfo=ZoneInfo("UTC"))
    doc = {"when": stored}
    assert evaluate([["when", "==", "2026-10-21"]], doc) is True
    assert evaluate([["when", ">", "2026-10-21 02:00:00"]], doc) is True
    assert evaluate([["when", "between", ["2026-10-21", "2026-10-21"]]], doc) is True


def test_quotes_are_data_instead_of_executable_expression_text():
    conditions = [["title", "like", '5" screen']]
    assert evaluate(conditions, {"title": 'New 5" screen'}) is True
    with pytest.raises(SyntaxError):
        upstream_answer(conditions, {"title": 'New 5" screen'})


@pytest.mark.parametrize(
    ("conditions", "doc", "message"),
    [
        ([["missing", "==", 1]], {}, "no field"),
        ([["value", "approximately", 1]], {"value": 1}, "Unknown"),
        ([["value", "=="]], {"value": 1}, "Malformed"),
        ([["value", "==", 1], "xor", ["value", "==", 1]], {"value": 1}, "conjunction"),
        ([["value", "between", [1]]], {"value": 1}, "two bounds"),
        ([["value", "<", 5]], {"value": "abc"}, "Cannot evaluate"),
        ([["when", ">", "not-a-date"]], {"when": date(2026, 1, 1)}, "Invalid date"),
    ],
)
def test_condition_failures_have_one_readable_exception(conditions, doc, message):
    with pytest.raises(ConditionError, match=message):
        evaluate(conditions, doc)


def test_malformed_json_is_a_condition_error():
    with pytest.raises(ConditionError, match="valid JSON"):
        evaluate("not json", {})


def test_safe_evaluation_returns_false_and_the_reason():
    answer, reason = evaluate_safely([["missing", "==", 1]], {})
    assert answer is False
    assert reason == "Document has no field 'missing'"
    assert evaluate_safely([["value", "==", 1]], {"value": 1}) == (True, None)


def test_non_condition_exceptions_are_not_swallowed():
    class Explodes:
        def __eq__(self, other):
            raise RuntimeError("comparison implementation failed")

    with pytest.raises(RuntimeError, match="implementation failed"):
        evaluate_safely([["value", "==", 1]], {"value": Explodes()})


@pytest.mark.django_db
def test_document_values_uses_field_names_fk_ids_and_float_decimals(administrator):
    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="Condition Test", type="Open")
        lead = CRMLead.objects.create(
            first_name="Ada",
            status=status,
            annual_revenue=Decimal("1234.500000"),
        )

    values = document_values(lead)
    assert values["name"] == lead.name
    assert values["status"] == "Condition Test"
    assert values["annual_revenue"] == 1234.5
    assert isinstance(values["annual_revenue"], float)


def test_document_values_uses_a_plain_dict_as_is():
    doc = {"amount": Decimal("1.50")}
    assert document_values(doc) is doc
