"""The three list-view bulk endpoints: ``assign_to.add_multiple``,
``assign_to.remove_multiple`` and ``bulk_update.submit_cancel_or_update_docs``.

All three are framework endpoints the CRM frontend calls directly - the assignment modal
in bulk mode (``AssignmentModal.vue:157-170``), "Clear Assignment"
(``ListBulkActions.vue:145-156``) and the bulk edit dialog
(``EditValueModal.vue:109-125``).

Two assertions here are about deliberate divergence rather than fidelity, and both are
load-bearing:

* the assign paths are **one transaction**, so a denied document unassigns the ones
  already done in that call - upstream leaves the batch half-applied;
* ``submit`` and ``cancel`` fail every document, because nothing in this port is
  submittable.
"""

import json

import pytest

from crm_app.models import CRMLead, CRMLeadStatus
from frappe_core import assignment
from frappe_core.session import session_user
from frappe_platform.models import ToDo

pytestmark = pytest.mark.django_db

ADD_MULTIPLE = "frappe.desk.form.assign_to.add_multiple"
REMOVE_MULTIPLE = "frappe.desk.form.assign_to.remove_multiple"
BULK_UPDATE = "frappe.desk.doctype.bulk_update.bulk_update.submit_cancel_or_update_docs"

MISSING = "CRM-LEAD-9999-00000"


def call(client, path, payload=None):
    return client.post(f"/api/method/{path}", payload or {}, format="json")


@pytest.fixture(autouse=True)
def lead_status(administrator):
    with session_user(administrator.name):
        CRMLeadStatus.objects.get_or_create(
            lead_status="New", defaults={"type": "Open"}
        )


def make_leads(owner, count, prefix="ZZ Bulk"):
    with session_user(owner.name):
        return [
            CRMLead.objects.create(first_name=f"{prefix} {i}", lead_owner=owner)
            for i in range(count)
        ]


@pytest.fixture
def mine(alice):
    """Two leads alice owns, so she can write them."""
    return make_leads(alice, 2)


@pytest.fixture
def carol(make_user):
    """A third Sales User who owns nothing, so an assignment to her is always new."""
    return make_user("carol@example.com", first_name="Carol", roles=["Sales User"])


@pytest.fixture
def theirs(bob):
    """A lead alice can neither see nor write (org_hierarchy: owner or assignee)."""
    return make_leads(bob, 1, prefix="ZZ Bobs")[0]


def open_todos(lead, user):
    return ToDo.objects.filter(
        reference_type="CRM Lead", reference_name=lead.name, allocated_to=user, status="Open"
    )


# --- add_multiple ------------------------------------------------------------------


def test_add_multiple_assigns_every_document_in_the_list(auth_api, alice, bob, mine):
    """``assign_to.py:148-156`` - ``add`` per name, so a ToDo per (document, user) pair.

    ``name`` is the *list*, JSON-encoded, and ``bulk_assign`` / ``re_assign`` ride along
    from ``AssignmentModal.vue``. Upstream's ``add`` reads neither, so neither may change
    the outcome here.
    """
    response = call(
        auth_api,
        ADD_MULTIPLE,
        {
            "doctype": "CRM Lead",
            "name": json.dumps([lead.name for lead in mine]),
            "assign_to": [bob.name],
            "bulk_assign": True,
            "re_assign": True,
        },
    )
    assert response.status_code == 200
    # Upstream's add_multiple has no return statement; only single-document `add` answers.
    assert response.json()["message"] is None

    for lead in mine:
        assert open_todos(lead, bob.name).count() == 1
        lead.refresh_from_db()
        # alice is in there too: a lead is assigned to its own owner on insert (C1a,
        # `OwnerAssignmentMixin`). ``add`` adds an assignee, it does not replace the set.
        assert sorted(lead._assign) == sorted([alice.name, bob.name])


def test_add_multiple_accepts_a_real_list_as_well_as_a_json_string(auth_api, bob, mine):
    """Upstream is ``json.loads(args["name"])`` and would fail on a list. The port's own
    ``parse_json_param`` convention takes both, and a native list is what a JSON body
    naturally carries."""
    response = call(
        auth_api,
        ADD_MULTIPLE,
        {"doctype": "CRM Lead", "name": [lead.name for lead in mine], "assign_to": bob.name},
    )
    assert response.status_code == 200
    assert all(open_todos(lead, bob.name).exists() for lead in mine)


def test_add_multiple_refuses_the_whole_batch_when_one_document_is_denied(
    auth_api, alice, carol, mine, theirs
):
    """**The divergence.** Upstream loops with no transaction: the first document is
    assigned, the second throws, and the caller is left with half a batch and no way to
    tell which half. The port wraps the loop in ``transaction.atomic`` the way
    ``delete_bulk_docs`` does, so a refusal anywhere unassigns everything in the call.

    carol rather than bob as the assignee: bob owns ``theirs`` and is therefore already
    assigned to it (C1a), which would make "no assignment was created" unreadable.
    """
    first = mine[0]
    response = call(
        auth_api,
        ADD_MULTIPLE,
        {
            "doctype": "CRM Lead",
            "name": json.dumps([first.name, theirs.name]),
            "assign_to": [carol.name],
        },
    )
    assert response.status_code == 403
    assert response.json()["exc_type"] == "PermissionError"

    assert not open_todos(first, carol.name).exists(), "the earlier document was rolled back"
    assert not open_todos(theirs, carol.name).exists()
    first.refresh_from_db()
    # crm/api/todo.py's after_insert would have made carol the owner; that went back too.
    assert first.lead_owner_id == alice.name


def test_add_multiple_404s_on_a_name_that_does_not_exist(auth_api, bob, mine):
    first = mine[0]
    response = call(
        auth_api,
        ADD_MULTIPLE,
        {"doctype": "CRM Lead", "name": json.dumps([first.name, MISSING]), "assign_to": [bob.name]},
    )
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"
    assert not open_todos(first, bob.name).exists(), "same transaction rule"


# --- remove_multiple ---------------------------------------------------------------


def test_remove_multiple_cancels_every_open_assignment(api_as, administrator, alice, bob, mine):
    """``assign_to.py:191-201`` - ``get()`` then ``remove()`` per assignee, which is
    ``set_status(status="Cancelled")``. Cancelled, never deleted: the audit trail stays
    and a cancelled ToDo grants no access (PHASE_2_PERMISSIONS.md section 2).

    Run as Administrator because assigning a lead hands ownership to the assignee
    (``crm/api/todo.py`` after_insert), so alice can no longer write what she just gave
    away - which is the product's behaviour, not an artefact of the test.
    """
    with session_user(alice.name):
        for lead in mine:
            assignment.assign_to_user("CRM Lead", lead.name, bob.name)
            assignment.assign_to_user("CRM Lead", lead.name, alice.name)

    response = call(
        api_as(administrator),
        REMOVE_MULTIPLE,
        {
            "doctype": "CRM Lead",
            "names": json.dumps([lead.name for lead in mine]),
            "ignore_permissions": True,  # ListBulkActions.vue sends it; upstream drops it
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] is None

    for lead in mine:
        assert assignment.get_assigned_users("CRM Lead", lead.name) == []
        statuses = set(
            ToDo.objects.filter(
                reference_type="CRM Lead", reference_name=lead.name
            ).values_list("status", flat=True)
        )
        assert statuses == {"Cancelled"}, "cancelled, not deleted"
        lead.refresh_from_db()
        assert lead._assign == []


def test_remove_multiple_needs_write_permission_on_every_document(auth_api, bob, theirs):
    """``ignore_permissions: true`` from the frontend must not buy anything: upstream's
    ``remove_multiple`` does not accept the argument at all, so the framework drops it
    before the function runs."""
    with session_user(bob.name):
        assignment.assign_to_user("CRM Lead", theirs.name, bob.name)

    response = call(
        auth_api,
        REMOVE_MULTIPLE,
        {
            "doctype": "CRM Lead",
            "names": json.dumps([theirs.name]),
            "ignore_permissions": True,
        },
    )
    assert response.status_code == 403
    assert assignment.get_assigned_users("CRM Lead", theirs.name) == [bob.name]


# --- submit_cancel_or_update_docs --------------------------------------------------


def test_bulk_update_applies_the_field_to_every_document(auth_api, alice):
    """Under 20 names runs inline and returns ``failed`` - empty when all of them went
    through (``bulk_update.py:67-68``)."""
    leads = make_leads(alice, 3)
    response = call(
        auth_api,
        BULK_UPDATE,
        {
            "doctype": "CRM Lead",
            "docnames": [lead.name for lead in leads],
            "action": "update",
            "data": {"job_title": "ZZ Engineer"},
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] == []

    for lead in leads:
        lead.refresh_from_db()
        assert lead.job_title == "ZZ Engineer"


def test_bulk_update_fails_per_document_and_carries_on(auth_api, alice, mine, theirs):
    """Upstream catches per document, logs and rolls that one back
    (``bulk_update.py:120-123``); the rest of the batch still applies. A missing name and
    a denied one both land in ``failed`` - the first because ``frappe.get_doc`` raises, the
    second because ``doc.save()`` does.
    """
    ok = mine[0]
    response = call(
        auth_api,
        BULK_UPDATE,
        {
            "doctype": "CRM Lead",
            "docnames": [MISSING, theirs.name, ok.name],
            "action": "update",
            "data": {"job_title": "ZZ Partial"},
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] == [MISSING, theirs.name]

    ok.refresh_from_db()
    assert ok.job_title == "ZZ Partial"
    theirs.refresh_from_db()
    assert theirs.job_title == ""


def test_submit_fails_every_document_because_nothing_here_is_submittable(auth_api, mine):
    """No doctype in this port has a ``docstatus``, so there is nothing ``submit`` can
    apply to. Upstream reaches the same answer by a longer road: ``doc.submit()`` on a
    non-submittable doctype raises, the per-document handler catches it, and the name
    lands in ``failed``.
    """
    names = [lead.name for lead in mine]
    response = call(
        auth_api,
        BULK_UPDATE,
        {"doctype": "CRM Lead", "docnames": names, "action": "submit"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == names


def test_more_than_500_documents_is_refused(auth_api):
    """``bulk_update.py:78-79``, verbatim - message and title both."""
    response = call(
        auth_api,
        BULK_UPDATE,
        {
            "doctype": "CRM Lead",
            "docnames": [f"CRM-LEAD-{i}" for i in range(501)],
            "action": "update",
            "data": {"job_title": "ZZ Too Many"},
        },
    )
    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "ValidationError"
    assert body["message"] == "Bulk operations only support up to 500 documents."
    server_message = json.loads(json.loads(body["_server_messages"])[0])
    assert server_message["title"] == "Too Many Documents"


def test_twenty_documents_go_to_the_background_and_still_apply(auth_api, alice):
    """The enqueue band (``bulk_update.py:69-77``): 20 or more, up to 500, returns nothing.

    Upstream also ``msgprint``s "Bulk operation is enqueued in background." - this port
    has no message channel on a *success* response, so the alert is not delivered and not
    faked. Celery is eager under test, so the work itself still lands, which is also what
    proves the worker re-runs the permission check as alice rather than as Guest.
    """
    leads = make_leads(alice, 20)
    response = call(
        auth_api,
        BULK_UPDATE,
        {
            "doctype": "CRM Lead",
            "docnames": [lead.name for lead in leads],
            "action": "update",
            "data": {"job_title": "ZZ Enqueued"},
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] is None

    for lead in leads:
        lead.refresh_from_db()
        assert lead.job_title == "ZZ Enqueued"


def test_an_unknown_doctype_is_a_404_not_a_batch_of_failures(auth_api):
    """Resolved once, before the loop: "there is no such doctype" rather than a ``failed``
    list as long as the input."""
    response = call(
        auth_api,
        BULK_UPDATE,
        {"doctype": "No Such Doctype", "docnames": ["x"], "action": "update", "data": {}},
    )
    assert response.status_code == 404
    # `DocTypeNotFound` pins its own `exc_type` to the base name (`registry.py:41`), so
    # the frontend sees the branch it switches on (`src/data/document.js:40`).
    assert response.json()["exc_type"] == "DoesNotExistError"


# --- method surface ----------------------------------------------------------------


@pytest.mark.parametrize("path", [ADD_MULTIPLE, REMOVE_MULTIPLE, BULK_UPDATE])
def test_the_bulk_paths_are_post_only(auth_api, path):
    """All three write. Upstream whitelists ``submit_cancel_or_update_docs`` POST-only
    outright; the assign pair are GET-callable upstream, which the port does not copy - a
    state change must not be reachable by a link or a prefetch.

    ``frappe_core/method_views.py:45-49`` answers a wrong method with a ``PermissionError``
    naming the method, not a 405: the port has one error envelope.
    """
    response = auth_api.get(f"/api/method/{path}")
    assert response.status_code == 403
    assert response.json()["exc_type"] == "PermissionError"
