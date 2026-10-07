"""The kanban defaults of CRM Lead, CRM Deal and CRM Task: docs/FINDINGS.md 53.

Upstream declares ``default_kanban_settings`` on the three (``crm_task.py:112``,
``crm_lead.py:487``, ``crm_deal.py:350``); the port did not, so every card showed the
record's ``name`` and nothing else.
"""

import importlib
import json

import pytest
from django.apps import apps

from crm_app.models import CRMTask
from crm_app.models.metadata import CRMViewSettings
from frappe_core import registry
from frappe_core.api.doc import get_data
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


def test_the_three_doctypes_declare_upstreams_kanban_defaults():
    expected = {
        "CRM Task": ("status", "title", ["description", "priority", "creation"]),
        "CRM Lead": ("status", "lead_name", ["organization", "email", "mobile_no", "_assign", "modified"]),
        "CRM Deal": ("status", "organization", ["annual_revenue", "email", "mobile_no", "_assign", "modified"]),
    }
    for doctype, (column_field, title_field, fields) in expected.items():
        settings = registry.get_entry(doctype).default_kanban_settings()
        assert settings["column_field"] == column_field, doctype
        assert settings["title_field"] == title_field, doctype
        assert json.loads(settings["kanban_fields"]) == fields, doctype


def test_a_task_card_carries_its_description_priority_and_age(administrator):
    """``Tasks.vue`` renders each name in ``kanban_fields`` off the card's row, so the
    row must carry them; the title is the task's title, not its number."""
    with session_user(administrator.name):
        CRMTask.objects.create(title="ZZ Kanban", description="<p>call back</p>", priority="High", status="Todo")
        result = get_data(
            "CRM Task", filters={}, column_field="status", view={"view_type": "kanban"}
        )

    assert result["title_field"] == "title"
    assert result["kanban_fields"] == ["description", "priority", "creation"]
    todo = next(entry for entry in result["data"] if entry["column"]["name"] == "Todo")
    card = next(row for row in todo["data"] if row["title"] == "ZZ Kanban")
    assert card["description"] == "<p>call back</p>" and card["priority"] == "High"
    assert card["creation"] and card["reference_docname"] == ""


def test_the_migration_repairs_a_saved_view_the_fallback_wrote(administrator):
    with session_user(administrator.name):
        saved = CRMViewSettings.objects.create(
            dt="CRM Task",
            type="kanban",
            label="Kanban",
            user=administrator,
            is_standard=True,
            kanban_fields=json.dumps(["name"]),
            title_field="name",
        )
        chosen = CRMViewSettings.objects.create(
            dt="CRM Task",
            type="kanban",
            label="Mine",
            user=administrator,
            kanban_fields=json.dumps(["priority"]),
            title_field="title",
        )

    migration = importlib.import_module("crm_app.migrations.0011_kanban_fields_reset")
    migration.forwards(apps, None)

    saved.refresh_from_db()
    chosen.refresh_from_db()
    assert json.loads(saved.kanban_fields) == ["description", "priority", "creation"]
    assert saved.title_field == "title"
    assert json.loads(chosen.kanban_fields) == ["priority"], "a person's own choice is kept"
