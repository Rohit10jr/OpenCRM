"""Port the shared Link search contract from the old method endpoints.

The saved FCRM Note / CRM Lead reference-pair case in
backend/tests/test_reference_doctype_search.py:56-82 belongs to
ACTIVITIES/SALES because it needs those production resources.
"""

import json
from datetime import timedelta

import pytest
from django.utils import timezone

from tests_support.models import Widget


pytestmark = pytest.mark.django_db
SEARCH = "/api/v1/test-widgets/search/"


def save_widget(user, name, title="", **values):
    document = Widget(
        name=name,
        widget_name=title,
        widget_owner=values.pop("widget_owner", user),
        **values,
    )
    document.save(user=user)
    return document


def search(client, method="post", **inputs):
    request = getattr(client, method)
    if method == "get":
        inputs = {
            key: json.dumps(value) if isinstance(value, (dict, list)) else value
            for key, value in inputs.items()
        }
        response = request(SEARCH, inputs)
    else:
        response = request(SEARCH, inputs, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_search_uses_the_list_rule_and_ignores_ignore_user_permissions(
    auth_api, alice, bob
):
    mine = save_widget(alice, "Mine")
    save_widget(bob, "Theirs")

    rows = search(auth_api, ignore_user_permissions=1)

    assert [row["value"] for row in rows] == [mine.name]


def test_hidden_search_field_never_matches_or_appears(auth_api, alice, monkeypatch):
    save_widget(alice, "Visible Name", title="ordinary", notes="needle-secret")
    monkeypatch.setattr(Widget, "SEARCH_FIELD", "notes")
    monkeypatch.setattr(Widget, "SENSITIVE_FIELDS", ("notes",), raising=False)

    rows = search(auth_api, txt="needle-secret")

    assert rows == []


def test_disabled_rows_are_hidden_unless_the_filter_flag_includes_them(auth_api, alice):
    enabled = save_widget(alice, "Enabled", title="Enabled")
    disabled = save_widget(alice, "Disabled", title="Disabled", disabled=True)

    assert [row["value"] for row in search(auth_api)] == [enabled.name]
    assert [
        row["value"] for row in search(auth_api, filters={"include_disabled": 1})
    ] == [disabled.name, enabled.name]


def test_txt_matches_name_and_search_field_case_insensitively(auth_api, alice):
    by_name = save_widget(alice, "Needle Name", title="other")
    by_title = save_widget(alice, "Other Name", title="nEeDlE title")
    save_widget(alice, "No Match", title="other")

    values = {row["value"] for row in search(auth_api, txt="NEEDLE")}

    assert values == {by_name.name, by_title.name}


def test_rows_are_modified_desc_and_page_length_is_applied(auth_api, alice):
    older = save_widget(alice, "Older", title="older")
    newer = save_widget(alice, "Newer", title="newer")
    now = timezone.now()
    Widget.objects.filter(pk=older.pk).update(modified=now - timedelta(days=1))
    Widget.objects.filter(pk=newer.pk).update(modified=now)

    rows = search(auth_api, method="get", page_length=1)

    assert rows == [{"value": newer.name, "description": "newer"}]


def test_plain_and_show_title_answer_shapes(auth_api, alice, monkeypatch):
    titled = save_widget(alice, "Named Value", title="Shown Title")

    assert search(auth_api, txt="Shown") == [
        {"value": titled.name, "description": "Shown Title"}
    ]

    monkeypatch.setattr(Widget, "SHOW_TITLE_FIELD_IN_LINK", True)
    assert search(auth_api, txt="Shown") == [
        {
            "value": titled.name,
            "label": "Shown Title",
            "description": titled.name,
        }
    ]


def test_empty_title_uses_the_name_as_the_label(auth_api, alice, monkeypatch):
    untitled = save_widget(alice, "Untitled")
    monkeypatch.setattr(Widget, "SHOW_TITLE_FIELD_IN_LINK", True)

    assert search(auth_api, txt="Untitled") == [
        {
            "value": untitled.name,
            "label": untitled.name,
            "description": untitled.name,
        }
    ]


def test_query_reference_doctype_and_surplus_inputs_are_accepted(auth_api, alice):
    found = save_widget(alice, "Accepted Inputs", title="Accepted")

    rows = search(
        auth_api,
        txt="Accepted",
        query="custom.query",
        reference_doctype="Foundation Pointing",
        filters={"ignore_user_type": 1},
        surplus="ignored",
    )

    assert rows == [{"value": found.name, "description": "Accepted"}]


def test_get_without_txt_returns_the_newest_visible_rows(auth_api, alice, bob):
    mine = save_widget(alice, "Mine", title="Mine")
    save_widget(bob, "Hidden", title="Hidden")

    assert search(auth_api, method="get") == [
        {"value": mine.name, "description": "Mine"}
    ]


DOCTYPE_SEARCH = "/api/v1/doctypes/search/"


def search_doctypes(client, method="post", **inputs):
    request = getattr(client, method)
    if method == "get":
        inputs = {
            key: json.dumps(value) if isinstance(value, (dict, list)) else value
            for key, value in inputs.items()
        }
        response = request(DOCTYPE_SEARCH, inputs)
    else:
        response = request(DOCTYPE_SEARCH, inputs, format="json")
    assert response.status_code == 200, response.content[:300]
    return response.json()["message"]


def test_sales_user_can_search_every_declared_doctype(auth_api):
    from core.doctypes import declared_doctypes

    rows = search_doctypes(auth_api, page_length=500)

    assert [row["value"] for row in rows] == sorted(declared_doctypes())
    assert all(row["description"] == "" for row in rows)


def test_doctype_prefix_matches_come_first(auth_api, monkeypatch):
    monkeypatch.setattr(
        "core.views.declared_doctypes",
        lambda: {
            "Alpha CRM": object,
            "CRM Lead": object,
            "ERPNext CRM Settings": object,
        },
    )

    rows = search_doctypes(auth_api, txt="crm", page_length=200)

    assert [row["value"] for row in rows] == [
        "CRM Lead",
        "Alpha CRM",
        "ERPNext CRM Settings",
    ]


def test_doctype_search_pages_ten_by_default(auth_api):
    assert len(search_doctypes(auth_api)) == 10
    assert len(search_doctypes(auth_api, page_length=3)) == 3


@pytest.mark.parametrize(
    "filters",
    [
        {"name": ["in", ["Foundation Widget", "Foundation Widget Row"]]},
        [["DocType", "name", "in", ["Foundation Widget", "Foundation Widget Row"]]],
    ],
)
def test_doctype_name_filters_are_honoured(auth_api, filters):
    rows = search_doctypes(auth_api, filters=filters)

    assert [row["value"] for row in rows] == [
        "Foundation Widget",
        "Foundation Widget Row",
    ]


def test_doctype_scalar_name_filter_and_get_are_supported(auth_api):
    rows = search_doctypes(
        auth_api,
        method="get",
        filters={"name": "Foundation Widget"},
        query="ignored",
        reference_doctype="ignored",
        ignore_user_permissions=1,
        surplus="ignored",
    )

    assert rows == [{"value": "Foundation Widget", "description": ""}]


def test_doctype_search_requires_authentication(api):
    assert api.get(DOCTYPE_SEARCH).status_code == 401
    assert api.post(DOCTYPE_SEARCH, {}, format="json").status_code == 401
