"""SLA policy validation and selection (FINDINGS.md 91, brief 05)."""

import ast
import importlib
import json
from datetime import time, timedelta
from pathlib import Path

import pytest
from django.apps import apps
from django.utils import timezone

from config.settings import base as base_settings
from crm_app.models import (
    CRMCommunicationStatus,
    CRMDeal,
    CRMDealStatus,
    CRMLead,
    CRMLeadStatus,
    CRMServiceLevelAgreement,
    CRMServiceLevelPriority,
    CRMServiceDay,
)
from frappe_core.exceptions import ValidationError

pytestmark = pytest.mark.django_db


@pytest.fixture
def statuses():
    return {
        "lead": CRMLeadStatus.objects.create(lead_status="New", type="Open"),
        "deal": CRMDealStatus.objects.create(deal_status="Qualification", type="Open"),
        "open": CRMCommunicationStatus.objects.create(status="Open"),
        "replied": CRMCommunicationStatus.objects.create(status="Replied"),
    }


def _sla(name, *, priority=None, **values):
    values.setdefault("apply_on", "CRM Lead")
    values.setdefault("enabled", True)
    sla = CRMServiceLevelAgreement.objects.create(sla_name=name, **values)
    if priority:
        CRMServiceLevelPriority.objects.create(
            parent_sla=sla,
            priority=priority,
            first_response_time=3600,
        )
        for index, workday in enumerate(
            ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
            start=1,
        ):
            CRMServiceDay.objects.create(
                parent_sla=sla,
                workday=workday,
                start_time=time.min,
                end_time=time(23, 59, 59),
                idx=index,
            )
    return sla


def test_time_zone_setting_is_read_through_the_environment_code_path():
    source = Path(base_settings.__file__).read_text(encoding="utf-8")
    assignment = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "TIME_ZONE"
            for target in node.targets
        )
    )
    calls = []

    def fake_env(name, *, default):
        calls.append((name, default))
        return "Asia/Kolkata"

    namespace = {"env": fake_env}
    code = compile(
        ast.Module(body=[assignment], type_ignores=[]), base_settings.__file__, "exec"
    )
    exec(code, namespace)
    assert namespace["TIME_ZONE"] == "Asia/Kolkata"
    assert calls == [("TIME_ZONE", "UTC")]


def test_new_sales_documents_default_communication_status_to_open(statuses):
    lead = CRMLead.objects.create(status=statuses["lead"], first_name="Lead")
    deal = CRMDeal.objects.create(status=statuses["deal"], first_name="Deal")
    assert lead.communication_status_id == "Open"
    assert deal.communication_status_id == "Open"


def test_data_migration_only_sets_open_when_the_status_exists():
    lead_status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    deal_status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
    lead = CRMLead.objects.create(status=lead_status, first_name="Old Lead")
    deal = CRMDeal.objects.create(status=deal_status, first_name="Old Deal")
    migration = importlib.import_module(
        "crm_app.migrations.0012_default_open_communication_status"
    )

    migration.forwards(apps, None)
    lead.refresh_from_db()
    deal.refresh_from_db()
    assert lead.communication_status_id is None
    assert deal.communication_status_id is None

    CRMCommunicationStatus.objects.create(status="Open")
    migration.forwards(apps, None)
    lead.refresh_from_db()
    deal.refresh_from_db()
    assert lead.communication_status_id == "Open"
    assert deal.communication_status_id == "Open"


def test_selection_filters_candidates_and_considers_default_last(statuses):
    today = timezone.localdate()
    _sla("Disabled", priority=statuses["open"], enabled=False)
    _sla("Wrong doctype", priority=statuses["open"], apply_on="CRM Deal")
    _sla("Not started", priority=statuses["open"], start_date=today + timedelta(days=1))
    _sla("Expired", priority=statuses["open"], end_date=today - timedelta(days=1))
    _sla("Wrong priority", priority=statuses["replied"])
    default = _sla("Default", priority=statuses["open"], default=True)
    matching = _sla("Matching", priority=statuses["open"])

    lead = CRMLead.objects.create(status=statuses["lead"], first_name="Ada")
    assert lead.sla == matching
    assert lead.sla != default


def test_editor_condition_decides_and_existing_sla_is_kept(statuses):
    _sla(
        "Wrong condition",
        priority=statuses["open"],
        condition='doc.organization == "Other"',
        condition_json=json.dumps([["organization", "equals", "Other"]]),
    )
    matching = _sla(
        "Editor condition",
        priority=statuses["open"],
        condition='doc.organization == "Acme"',
        condition_json=json.dumps([["organization", "equals", "Acme"]]),
    )
    explicit = _sla("Explicit but disabled", enabled=False)

    lead = CRMLead.objects.create(
        status=statuses["lead"], first_name="Ada", organization="Acme"
    )
    assert lead.sla == matching

    lead.sla = explicit
    lead.organization = "Other"
    lead.save()
    assert lead.sla == explicit


def test_no_match_clears_first_response_fields(statuses):
    stamp = timezone.now()
    lead = CRMLead(
        status=statuses["lead"],
        first_name="Ada",
        first_responded_on=stamp,
        first_response_time=10,
    )
    lead.save()
    assert lead.sla_id is None
    assert lead.first_responded_on is None
    assert lead.first_response_time is None


def test_partial_save_does_not_select_an_sla(statuses):
    lead = CRMLead.objects.create(status=statuses["lead"], first_name="Ada")
    _sla("Later", priority=statuses["open"])
    lead.first_name = "Augusta"
    lead.save(update_fields=["first_name"])
    assert lead.sla_id is None


def test_only_one_default_sla_is_allowed_per_doctype():
    _sla("First", default=True)
    with pytest.raises(ValidationError) as caught:
        _sla("Second", default=True)
    assert caught.value.message == (
        "Default Service Level Agreement already exists for CRM Lead"
    )


def test_code_only_and_invalid_json_conditions_are_refused():
    with pytest.raises(ValidationError) as caught:
        _sla("Code only", condition='doc.status == "New"')
    assert caught.value.message == (
        "This condition was written as code. Build it with the condition editor in "
        "Settings → SLA Policies; conditions written as code are not evaluated here."
    )

    with pytest.raises(ValidationError) as caught:
        _sla("Bad JSON", condition='doc.status == "New"', condition_json="not json")
    assert caught.value.message == (
        "The Condition 'doc.status == \"New\"' is invalid: Condition is not valid JSON: "
        "Expecting value"
    )


def test_sla_screen_save_payload_is_accepted():
    sla = _sla(
        "From screen",
        condition='doc.status == "New"',
        condition_json=json.dumps([["status", "equals", "New"]]),
    )
    assert sla.pk == "From screen"


def test_a_stale_stored_condition_warns_and_does_not_block_selection(statuses, caplog):
    stale = _sla("Stale", priority=statuses["open"])
    CRMServiceLevelAgreement.objects.filter(pk=stale.pk).update(condition_json="not json")
    fallback = _sla("Fallback", priority=statuses["open"], default=True)

    lead = CRMLead.objects.create(status=statuses["lead"], first_name="Ada")
    assert lead.sla == fallback
    assert "SLA Stale condition could not be evaluated" in caplog.text
