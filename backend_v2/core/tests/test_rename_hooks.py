"""The rename hooks of `RenameMixin` and `rename_document` (ACCOUNTS §10.1-10.3, §10.6),
on `tests_support` Widgets. New: no old test; the old backend has no hooks.
"""

import pytest

from core.mixins.rename import RenameMixin
from core.rename import rename_document, repoint_json_name_lists
from tests_support.models import Widget
from tests_support.views import WidgetViewSet

pytestmark = pytest.mark.django_db
WIDGETS = "/api/v1/test-widgets/"


def widget(user, name, **values):
    row = Widget(name=name, widget_name=name, widget_owner=user, **values)
    row.save(user=user)
    return row


def rename(client, url_name, new_name):
    return client.post(f"{WIDGETS}{url_name}/rename/", {"new_name": new_name}, format="json")


def test_the_defaults_change_nothing():
    assert RenameMixin.before_rename(None, None, "a", "b") == "b"
    assert RenameMixin.on_renamed(None, "a", "b") is None


def test_before_rename_replaces_the_name_every_later_step_uses(auth_api, alice, monkeypatch):
    widget(alice, "W-1")
    monkeypatch.setattr(WidgetViewSet, "before_rename", lambda self, inst, old, new: new.upper(), raising=False)
    response = rename(auth_api, "W-1", "w-2")
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": "W-2"}
    assert Widget.objects.filter(pk="W-2").exists()


def test_before_rename_makes_the_same_name_check_see_the_normalised_name(auth_api, alice, monkeypatch):
    widget(alice, "W-1")
    monkeypatch.setattr(WidgetViewSet, "before_rename", lambda self, inst, old, new: new.upper(), raising=False)
    response = rename(auth_api, "W-1", "w-1")
    assert response.status_code == 417
    assert response.json()["message"] == "No changes made because old and new name are the same."


def test_name_taken_can_answer_its_own_way(auth_api, alice, monkeypatch):
    widget(alice, "W-1")
    monkeypatch.setattr(WidgetViewSet, "name_taken", lambda self, new, old: True, raising=False)
    response = rename(auth_api, "W-1", "W-2")
    assert response.status_code == 417
    assert response.json()["message"].startswith("Another ")


def test_rename_rule_replaces_the_write_rule(auth_api, alice, monkeypatch):
    widget(alice, "W-1")
    monkeypatch.setattr(WidgetViewSet, "rename_rule", lambda self, user, inst: False, raising=False)
    response = rename(auth_api, "W-1", "W-2")
    assert response.status_code == 417
    assert response.json()["message"].startswith("You need write permission on")


def test_on_renamed_runs_after_the_copy_and_before_the_delete(alice):
    widget(alice, "W-1")
    seen = {}

    def hook(old, new):
        seen["both"] = set(Widget.objects.filter(pk__in=[old, new]).values_list("pk", flat=True))

    rename_document(Widget, "W-1", "W-2", on_renamed=hook)
    assert seen["both"] == {"W-1", "W-2"}
    assert not Widget.objects.filter(pk="W-1").exists()


def test_a_failing_on_renamed_leaves_everything_as_it_was(alice):
    widget(alice, "W-1")

    def hook(old, new):
        raise RuntimeError("forced")

    with pytest.raises(RuntimeError):
        rename_document(Widget, "W-1", "W-2", on_renamed=hook)
    assert Widget.objects.filter(pk="W-1").exists()
    assert not Widget.objects.filter(pk="W-2").exists()


def test_json_name_lists_rewrite_exact_matches_only(alice):
    row = widget(alice, "W-1")
    Widget.objects.filter(pk=row.pk).update(
        _assign=["a@x.com", "xa@x.com", "a@x.com"], _liked_by=["b@x.com"]
    )
    modified = Widget.objects.get(pk=row.pk).modified

    assert repoint_json_name_lists("a@x.com", "c@x.com") >= 1

    row = Widget.objects.get(pk=row.pk)
    assert row._assign == ["c@x.com", "xa@x.com", "c@x.com"]
    assert row._liked_by == ["b@x.com"]
    assert row.modified == modified
