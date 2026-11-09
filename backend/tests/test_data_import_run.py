"""Running CSV Data Imports through the real method endpoints and worker."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.utils import timezone

from crm_app.data_import.run import start_data_import_task
from crm_app.models import CRMLead, CRMLeadStatus
from frappe_platform import files as file_store
from frappe_platform.models import (
    ASSIGNMENT_DAYS,
    AssignmentRule,
    AssignmentRuleDay,
    AssignmentRuleUser,
    Contact,
    DataImport,
    DataImportLog,
    ToDo,
)


pytestmark = pytest.mark.django_db
METHOD = "/api/method/"
START = METHOD + "frappe.core.doctype.data_import.data_import.form_start_import"
LOGS = METHOD + "frappe.core.doctype.data_import.data_import.get_import_logs"


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def system_manager(make_user):
    return make_user("sysmgr-run@example.com", first_name="System", roles=["System Manager"])


@pytest.fixture
def sales_manager(make_user):
    return make_user("salesmgr-run@example.com", roles=["Sales Manager"])


def _upload(client, content: bytes, name="import.csv"):
    response = client.post(
        METHOD + "upload_file",
        {"file": SimpleUploadedFile(name, content, content_type="text/csv"), "is_private": 1},
        format="multipart",
    )
    assert response.status_code == 200, response.content[:500]
    return response.json()["message"]["file_url"]


def _import(client, content: bytes, doctype="Contact"):
    file_url = _upload(client, content)
    response = client.post(
        METHOD + "frappe.client.insert",
        {
            "doc": {
                "doctype": "Data Import",
                "reference_doctype": doctype,
                "import_type": "Insert New Records",
                "mute_emails": True,
                "status": "Pending",
                "google_sheets_url": "",
                "import_file": file_url,
            }
        },
        format="json",
    )
    assert response.status_code == 200, response.content[:500]
    return response.json()["message"]["name"]


def _start(client, name):
    return client.post(START, {"data_import": name}, format="json")


def _assignment_rule(name, user):
    rule = AssignmentRule.objects.create(
        name=name,
        document_type="CRM Lead",
        rule="Round Robin",
        assign_condition="editor condition",
        assign_condition_json=json.dumps([["first_name", "equals", "Assigned"]]),
    )
    for idx, day in enumerate(ASSIGNMENT_DAYS, 1):
        AssignmentRuleDay.objects.create(
            parent=rule.pk,
            parenttype="Assignment Rule",
            parentfield="assignment_days",
            idx=idx,
            day=day,
        )
    AssignmentRuleUser.objects.create(
        parent=rule.pk,
        parenttype="Assignment Rule",
        parentfield="users",
        idx=1,
        user=user,
    )
    return rule


def test_clean_contact_import_and_log_wire_shape(api_as, system_manager, media):
    client = api_as(system_manager)
    name = _import(
        client,
        b"First Name,email_ids.email_id,phone_nos.phone\n"
        b"Ada,ada-import@example.com,+1 555 0100\n",
    )

    response = _start(client, name)
    assert response.status_code == 200, response.content[:500]
    assert response.json()["message"] is True
    assert DataImport.objects.get(pk=name).status == "Success", DataImportLog.objects.get(
        data_import=name
    ).exception
    contact = Contact.objects.get(first_name="Ada")
    assert contact.email_id == "ada-import@example.com"
    assert contact.phone == "+1 555 0100"

    response = client.post(LOGS, {"data_import": name}, format="json")
    assert response.status_code == 200
    assert response.json()["message"] == [
        {
            "success": True,
            "docname": contact.name,
            "messages": None,
            "exception": "",
            "row_indexes": "[2]",
        }
    ]


@pytest.mark.parametrize(
    ("doctype", "content", "model"),
    [
        ("Contact", b"First Name\nManager Contact\n", Contact),
        ("CRM Lead", b"First Name\nManager Lead\n", CRMLead),
    ],
)
def test_system_manager_alone_can_import_target_doctypes(
    api_as, system_manager, media, doctype, content, model
):
    if doctype == "CRM Lead":
        CRMLeadStatus.objects.create(lead_status="New", type="Open")
    name = _import(api_as(system_manager), content, doctype)
    assert _start(api_as(system_manager), name).status_code == 200
    assert DataImport.objects.get(pk=name).status == "Success"
    assert model.objects.count() == 1


def test_blank_lead_owner_stays_blank(api_as, system_manager, media):
    CRMLeadStatus.objects.create(lead_status="New", type="Open")
    client = api_as(system_manager)
    name = _import(client, b"First Name\nUnassigned\n", "CRM Lead")
    _start(client, name)
    assert CRMLead.objects.get(first_name="Unassigned").lead_owner_id is None


def test_matching_assignment_rule_still_assigns_imported_lead(
    api_as, system_manager, make_user, media
):
    CRMLeadStatus.objects.create(lead_status="New", type="Open")
    assignee = make_user("import-assignee@example.com", roles=["Sales User"])
    _assignment_rule("Imported leads", assignee)

    client = api_as(system_manager)
    name = _import(client, b"First Name\nAssigned\n", "CRM Lead")
    _start(client, name)

    lead = CRMLead.objects.get(first_name="Assigned")
    assert lead.lead_owner_id == assignee.pk
    assert ToDo.objects.get(
        reference_type="CRM Lead", reference_name=lead.pk, status="Open"
    ).allocated_to_id == assignee.pk


def test_one_bad_row_retries_only_the_failure(api_as, system_manager, media):
    client = api_as(system_manager)
    name = _import(
        client,
        b"First Name,email_ids.email_id\nGood,good@example.com\nBad,not-an-email\n",
    )
    _start(client, name)
    document = DataImport.objects.get(pk=name)
    assert document.status == "Partial Success"
    failed = DataImportLog.objects.get(data_import=name, success=False)
    assert "valid email" in json.loads(failed.messages)[0]["message"].lower()

    path = file_store.path_for_url(document.import_file)
    path.write_bytes(
        b"First Name,email_ids.email_id\n"
        b"Good,good@example.com\nFixed,fixed@example.com\n"
    )
    _start(client, name)
    document.refresh_from_db()
    assert document.status == "Success"
    assert Contact.objects.filter(first_name="Good").count() == 1
    assert Contact.objects.filter(first_name="Fixed").count() == 1
    assert DataImportLog.objects.filter(data_import=name, success=False).count() == 0


def test_all_failures_and_child_only_payload_are_logged(api_as, system_manager, media):
    client = api_as(system_manager)
    name = _import(client, b"First Name,email_ids.email_id\nBad,not-an-email\n")
    _start(client, name)
    assert DataImport.objects.get(pk=name).status == "Error"

    child_only = _import(client, b"email_ids.email_id\nchild-only@example.com\n")
    _start(client, child_only)
    assert DataImport.objects.get(pk=child_only).status == "Error"
    log = DataImportLog.objects.get(data_import=child_only)
    assert not log.success
    assert log.row_indexes == "[2]"


def test_blocking_warnings_stop_without_changing_status(api_as, system_manager, media):
    client = api_as(system_manager)
    name = _import(client, b"First Name,Last Name\nShort\n")
    _start(client, name)
    document = DataImport.objects.get(pk=name)
    assert document.status == "Pending"
    assert json.loads(document.template_warnings)
    assert not DataImportLog.objects.filter(data_import=name).exists()
    assert not Contact.objects.exists()


def test_claim_lifecycle_stale_claim_and_queue_failure(api_as, system_manager, media):
    client = api_as(system_manager)
    name = _import(client, b"First Name\nQueued\n")
    with patch("crm_app.api.data_import.start_data_import_task.delay") as delay:
        assert _start(client, name).json()["message"] is True
        assert _start(client, name).json()["message"] is False
        DataImport.objects.filter(pk=name).update(job_claimed_at=timezone.now() - timedelta(hours=4))
        assert _start(client, name).json()["message"] is True
        delay.side_effect = RuntimeError("queue down")
        DataImport.objects.filter(pk=name).update(job_claimed_at=None)
        with pytest.raises(RuntimeError, match="queue down"):
            _start(client, name)
    assert DataImport.objects.get(pk=name).job_claimed_at is None

    assert _start(client, name).json()["message"] is True
    assert DataImport.objects.get(pk=name).status == "Success"


def test_redelivery_and_busy_lock_do_nothing(api_as, system_manager, media):
    client = api_as(system_manager)
    name = _import(client, b"First Name\nOnce\n")
    _start(client, name)
    start_data_import_task.run(name, system_manager.name)
    assert Contact.objects.filter(first_name="Once").count() == 1

    DataImport.objects.filter(pk=name).update(job_claimed_at=timezone.now())
    other_connection = connection.copy()
    try:
        with other_connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtext(%s))", [name])
        start_data_import_task.run(name, system_manager.name)
    finally:
        with other_connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [name])
        other_connection.close()
    assert DataImport.objects.get(pk=name).job_claimed_at is not None
    assert Contact.objects.filter(first_name="Once").count() == 1


def test_crash_between_rows_resumes_without_duplicates(api_as, system_manager, media):
    client = api_as(system_manager)
    name = _import(client, b"First Name\nFirst\nSecond\nThird\n")
    DataImport.objects.filter(pk=name).update(job_claimed_at=timezone.now())

    from crm_app.data_import import run

    real_insert = run.client_insert
    calls = 0

    def crash_on_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt("worker stopped")
        return real_insert(*args, **kwargs)

    with patch("crm_app.data_import.run.client_insert", side_effect=crash_on_second):
        with pytest.raises(KeyboardInterrupt, match="worker stopped"):
            start_data_import_task.run(name, system_manager.name)

    assert Contact.objects.filter(first_name="First").count() == 1
    assert DataImport.objects.get(pk=name).status == "Partial Success"

    assert _start(client, name).json()["message"] is True
    assert DataImport.objects.get(pk=name).status == "Success"
    for first_name in ("First", "Second", "Third"):
        assert Contact.objects.filter(first_name=first_name).count() == 1


def test_timeout_during_row_is_terminal_and_later_run_resumes(
    api_as, system_manager, media
):
    client = api_as(system_manager)
    name = _import(client, b"First Name\nBefore Timeout\nTimed Out Row\n")

    from crm_app.data_import import run

    real_insert = run.client_insert
    calls = 0

    def timeout_on_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise SoftTimeLimitExceeded()
        return real_insert(*args, **kwargs)

    with (
        patch("crm_app.data_import.run.client_insert", side_effect=timeout_on_second),
        patch("crm_app.data_import.run.publish") as publish,
    ):
        assert _start(client, name).json()["message"] is True

    document = DataImport.objects.get(pk=name)
    assert document.status == "Timed Out"
    assert document.job_claimed_at is None
    assert Contact.objects.filter(first_name="Before Timeout").count() == 1
    assert not Contact.objects.filter(first_name="Timed Out Row").exists()
    assert list(
        DataImportLog.objects.filter(data_import=name).values_list(
            "success", "row_indexes"
        )
    ) == [(True, "[2]")]
    publish.assert_called_once_with("data_import_refresh", {"data_import": name})

    assert _start(client, name).json()["message"] is True
    document.refresh_from_db()
    assert document.status == "Success"
    for first_name in ("Before Timeout", "Timed Out Row"):
        assert Contact.objects.filter(first_name=first_name).count() == 1


def test_run_status_write_advances_stored_modified(api_as, system_manager, media):
    client = api_as(system_manager)
    name = _import(client, b"First Name\nNewer Import\n")
    old_modified = timezone.now() - timedelta(days=1)
    DataImport.objects.filter(pk=name).update(modified=old_modified)

    assert _start(client, name).json()["message"] is True

    document = DataImport.objects.get(pk=name)
    assert document.status == "Success"
    assert document.modified > old_modified
    assert document.modified_by_id == system_manager.pk


def test_sales_manager_is_refused_both_methods(
    api_as, system_manager, sales_manager, media
):
    name = _import(api_as(system_manager), b"First Name\nPrivate\n")
    sales = api_as(sales_manager)
    assert _start(sales, name).status_code == 403
    assert sales.post(LOGS, {"data_import": name}, format="json").status_code == 403


def test_worker_rechecks_roles_and_publishes_failure(
    api_as, system_manager, media
):
    client = api_as(system_manager)
    name = _import(client, b"First Name\nForbidden Later\n")
    with patch("crm_app.api.data_import.start_data_import_task.delay"):
        assert _start(client, name).json()["message"] is True
    system_manager.groups.remove(Group.objects.get(name="System Manager"))

    with patch("crm_app.data_import.run.publish") as publish:
        start_data_import_task.run(name, system_manager.name)
    document = DataImport.objects.get(pk=name)
    assert document.status == "Error"
    assert document.job_claimed_at is None
    assert not Contact.objects.filter(first_name="Forbidden Later").exists()
    publish.assert_called_once_with("data_import_refresh", {"data_import": name})


def test_success_publishes_refresh(api_as, system_manager, media):
    client = api_as(system_manager)
    name = _import(client, b"First Name\nRefresh\n")
    with patch("crm_app.data_import.run.publish") as publish:
        assert _start(client, name).json()["message"] is True
    publish.assert_called_once_with("data_import_refresh", {"data_import": name})
