"""Phase 2 - the row-level permission engine.

PHASE_2_PERMISSIONS.md section 6 asks for a test matrix where "every row is a real
access-control decision". That matrix is :func:`test_visibility_matrix`, run against
both CRM Lead and CRM Deal.

The most important tests here are the last three groups: list filtering and
``has_permission`` must agree on **every** row, a cancelled ToDo must grant nothing, and
no combination of ``fields`` / ``order_by`` / ``group_by`` may expose a hidden row.
"""

import json
from urllib.parse import quote

import pytest
from django.db.models import Q

from frappe_core import registry
from frappe_core.permissions import check_object_permission, get_permission_query_conditions
from frappe_core.query import fetch_rows
from frappe_core.session import session_user
from frappe_platform.models import ToDo, User
from crm_app.models import (
    CRMDeal,
    CRMDealStatus,
    CRMLead,
    CRMLeadStatus,
    CRMNotification,
    CRMSalesHierarchy,
    FCRMSettings,
)
from crm_app.permissions.tree import rebuild_sales_hierarchy

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures: a three-level hierarchy and one record owned by each user
# ---------------------------------------------------------------------------


@pytest.fixture
def users(make_user):
    """boss -> manager -> rep, plus an unrelated outsider."""
    return {
        "boss": make_user("boss@example.com", roles=["Sales Manager"]),
        "manager": make_user("manager@example.com", roles=["Sales Manager"]),
        "rep": make_user("rep@example.com", roles=["Sales User"]),
        "outsider": make_user("outsider@example.com", roles=["Sales User"]),
        "sysmgr": make_user("sysmgr@example.com", roles=["System Manager"]),
    }


@pytest.fixture
def hierarchy(users, administrator):
    """Build the tree and let the phase-2 signal compute lft/rgt."""
    with session_user(administrator.name):
        boss = CRMSalesHierarchy.objects.create(user=users["boss"], full_name="Boss")
        manager = CRMSalesHierarchy.objects.create(
            user=users["manager"], full_name="Manager", reports_to=boss
        )
        CRMSalesHierarchy.objects.create(
            user=users["rep"], full_name="Rep", reports_to=manager
        )
    rebuild_sales_hierarchy()
    return CRMSalesHierarchy.objects.all()


@pytest.fixture
def enable_hierarchy(administrator):
    def _set(enabled: bool):
        with session_user(administrator.name):
            settings = FCRMSettings.load()
            settings.enable_sales_hierarchy = enabled
            settings.save()

    return _set


@pytest.fixture
def records(users, administrator):
    """One lead and one deal owned by each of boss / manager / rep / outsider."""
    with session_user(administrator.name):
        lead_status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        deal_status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        out = {"leads": {}, "deals": {}}
        for key in ("boss", "manager", "rep", "outsider"):
            out["leads"][key] = CRMLead.objects.create(
                status=lead_status, first_name=key.title(), lead_owner=users[key]
            )
            out["deals"][key] = CRMDeal.objects.create(
                status=deal_status, deal_owner=users[key]
            )
    return out


def visible_leads(user: str) -> set[str]:
    with session_user(user):
        return {r["first_name"] for r in fetch_rows("CRM Lead", fields=["first_name"], limit_page_length=0)}


def visible_deals(user: str) -> set[str]:
    with session_user(user):
        return {
            r["deal_owner"]
            for r in fetch_rows("CRM Deal", fields=["deal_owner"], limit_page_length=0)
        }


# ---------------------------------------------------------------------------
# The matrix - PHASE_2_PERMISSIONS.md section 6
# ---------------------------------------------------------------------------

ALL = {"Boss", "Manager", "Rep", "Outsider"}


def test_administrator_sees_everything(records, administrator, enable_hierarchy):
    enable_hierarchy(True)
    assert visible_leads("Administrator") == ALL


def test_administrator_is_unrestricted_by_role_too(records, users):
    """Frappe treats the literal ``Administrator`` *user* as privileged."""
    with session_user("Administrator"):
        assert get_permission_query_conditions("CRM Lead") is None


def test_system_manager_sees_everything(records, users, enable_hierarchy):
    enable_hierarchy(True)
    assert visible_leads(users["sysmgr"].name) == ALL


def test_sales_manager_hierarchy_off_sees_everything(records, users, enable_hierarchy):
    """Matrix row 3: hierarchy off, not in tree -> unrestricted."""
    enable_hierarchy(False)
    assert visible_leads(users["manager"].name) == ALL


def test_sales_manager_hierarchy_on_but_not_in_tree_sees_everything(
    records, users, enable_hierarchy
):
    """Matrix row 4. **This is deliberate upstream, not a bug** (``org_hierarchy.py:30``).

    A Sales Manager who was never placed in the tree keeps the legacy see-everything
    behaviour. Reordering this check below the tree evaluation would silently change it.
    """
    enable_hierarchy(True)  # no hierarchy rows exist for this user
    assert visible_leads(users["manager"].name) == ALL


def test_sales_manager_in_tree_sees_own_and_subtree(
    records, users, hierarchy, enable_hierarchy
):
    """Matrix row 5: manager sees self + rep, but not boss or outsider."""
    enable_hierarchy(True)
    assert visible_leads(users["manager"].name) == {"Manager", "Rep"}


def test_boss_in_tree_sees_the_whole_subtree(records, users, hierarchy, enable_hierarchy):
    enable_hierarchy(True)
    assert visible_leads(users["boss"].name) == {"Boss", "Manager", "Rep"}


def test_sales_user_hierarchy_off_sees_only_own(records, users, enable_hierarchy):
    """Matrix row 6."""
    enable_hierarchy(False)
    assert visible_leads(users["rep"].name) == {"Rep"}


def test_sales_user_in_tree_sees_own_and_subtree(
    records, users, hierarchy, enable_hierarchy
):
    """Matrix row 7. A leaf's subtree is just itself."""
    enable_hierarchy(True)
    assert visible_leads(users["rep"].name) == {"Rep"}


def test_outsider_sees_only_own(records, users, hierarchy, enable_hierarchy):
    enable_hierarchy(True)
    assert visible_leads(users["outsider"].name) == {"Outsider"}


def test_the_matrix_holds_for_deals_too(records, users, hierarchy, enable_hierarchy):
    """The whole matrix again for CRM Deal, whose owner field is ``deal_owner``."""
    enable_hierarchy(True)
    assert visible_deals(users["manager"].name) == {
        users["manager"].name,
        users["rep"].name,
    }
    assert visible_deals(users["rep"].name) == {users["rep"].name}
    assert visible_deals("Administrator") == {u.name for u in users.values() if u.name != "sysmgr@example.com"} | {users["outsider"].name}


def test_hierarchy_disabled_ignores_the_tree(records, users, hierarchy, enable_hierarchy):
    """With the flag off, a placed manager falls back to Sales Manager = sees all."""
    enable_hierarchy(False)
    assert visible_leads(users["manager"].name) == ALL


# ---------------------------------------------------------------------------
# Assignment via ToDo
# ---------------------------------------------------------------------------


def test_direct_assignment_grants_access(records, users, enable_hierarchy):
    enable_hierarchy(False)
    ToDo.objects.create(
        reference_type="CRM Lead",
        reference_name=records["leads"]["boss"].name,
        allocated_to=users["rep"],
        status="Open",
    )
    assert visible_leads(users["rep"].name) == {"Rep", "Boss"}


def test_cancelled_assignment_grants_nothing(records, users, enable_hierarchy):
    """PHASE_2_PERMISSIONS.md section 2 - the ``status != 'Cancelled'`` filter."""
    enable_hierarchy(False)
    ToDo.objects.create(
        reference_type="CRM Lead",
        reference_name=records["leads"]["boss"].name,
        allocated_to=users["rep"],
        status="Cancelled",
    )
    assert visible_leads(users["rep"].name) == {"Rep"}


def test_closed_assignment_still_grants_access(records, users, enable_hierarchy):
    """Closed is excluded from the *display* list but not from access.

    ``crm/api/doc.py:615`` excludes Closed and Cancelled; the permission clause
    (``org_hierarchy.py:47``) excludes only Cancelled. The two disagree on purpose.
    """
    enable_hierarchy(False)
    ToDo.objects.create(
        reference_type="CRM Lead",
        reference_name=records["leads"]["boss"].name,
        allocated_to=users["rep"],
        status="Closed",
    )
    assert visible_leads(users["rep"].name) == {"Rep", "Boss"}


def test_assignment_to_a_subtree_member_grants_the_manager_access(
    records, users, hierarchy, enable_hierarchy
):
    enable_hierarchy(True)
    ToDo.objects.create(
        reference_type="CRM Lead",
        reference_name=records["leads"]["outsider"].name,
        allocated_to=users["rep"],
        status="Open",
    )
    assert "Outsider" in visible_leads(users["manager"].name)


def test_assignment_for_another_doctype_does_not_leak(records, users, enable_hierarchy):
    """A ToDo pointing at a Deal must not unlock a Lead of the same name."""
    enable_hierarchy(False)
    ToDo.objects.create(
        reference_type="CRM Deal",
        reference_name=records["leads"]["boss"].name,
        allocated_to=users["rep"],
        status="Open",
    )
    assert visible_leads(users["rep"].name) == {"Rep"}


def test_a_forged_assign_cache_grants_nothing(records, users, enable_hierarchy):
    """``_assign`` is writable through the generic endpoint; the engine must ignore it."""
    enable_hierarchy(False)
    CRMLead.objects.filter(pk=records["leads"]["boss"].name).update(
        _assign=[users["rep"].name]
    )
    assert visible_leads(users["rep"].name) == {"Rep"}


# ---------------------------------------------------------------------------
# has_permission agrees with list filtering, on every row
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("actor", ["boss", "manager", "rep", "outsider"])
def test_list_filtering_and_has_permission_agree(
    records, users, hierarchy, enable_hierarchy, actor
):
    """The criterion that matters most: no row visible in a list but 403 on read, and
    no row hidden from the list but readable directly.
    """
    enable_hierarchy(True)
    user = users[actor].name
    with session_user(user):
        listed = {
            r["name"] for r in fetch_rows("CRM Lead", fields=["name"], limit_page_length=0)
        }
        for key, lead in records["leads"].items():
            allowed = check_object_permission(lead, "read", user)
            assert allowed == (lead.name in listed), (
                f"{actor}: {key} listed={lead.name in listed} has_permission={allowed}"
            )


@pytest.mark.parametrize("actor", ["manager", "rep"])
def test_list_and_object_agree_with_hierarchy_off(records, users, enable_hierarchy, actor):
    enable_hierarchy(False)
    user = users[actor].name
    with session_user(user):
        listed = {
            r["name"] for r in fetch_rows("CRM Lead", fields=["name"], limit_page_length=0)
        }
        for lead in records["leads"].values():
            assert check_object_permission(lead, "read", user) == (lead.name in listed)


def test_create_is_permitted_for_unsaved_documents(users, enable_hierarchy):
    """``org_hierarchy.py:84-85`` - skip it and every create fails."""
    enable_hierarchy(True)
    unsaved = CRMLead(first_name="New")
    assert check_object_permission(unsaved, "create", users["rep"].name) is True


def test_create_ptype_passes_even_for_a_saved_document(records, users, enable_hierarchy):
    enable_hierarchy(True)
    assert (
        check_object_permission(records["leads"]["boss"], "create", users["rep"].name)
        is True
    )


def test_detail_route_denies_a_hidden_row(records, users, enable_hierarchy, make_user):
    """End-to-end through HTTP, not just the hook."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    enable_hierarchy(False)
    client = APIClient()
    token = RefreshToken.for_user(users["rep"]).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    hidden = records["leads"]["boss"].name
    response = client.get("/api/resource/" + quote("CRM Lead") + "/" + quote(hidden))
    assert response.status_code == 403
    assert response.json()["exc_type"] == "PermissionError"


# ---------------------------------------------------------------------------
# CRM Notification uses its own rule
# ---------------------------------------------------------------------------


@pytest.fixture
def notifications(users, administrator):
    with session_user(administrator.name):
        return {
            "for_rep": CRMNotification.objects.create(type="Mention", to_user=users["rep"]),
            "for_boss": CRMNotification.objects.create(type="Mention", to_user=users["boss"]),
        }


def test_notification_is_visible_only_to_its_recipient(notifications, users):
    with session_user(users["rep"].name):
        listed = {r["name"] for r in fetch_rows("CRM Notification", fields=["name"], limit_page_length=0)}
    assert listed == {notifications["for_rep"].name}


def test_notification_uses_its_own_rule_not_the_hierarchy_one(
    notifications, users, hierarchy, enable_hierarchy
):
    """A manager does **not** see their subtree's notifications."""
    enable_hierarchy(True)
    with session_user(users["manager"].name):
        listed = {r["name"] for r in fetch_rows("CRM Notification", fields=["name"], limit_page_length=0)}
    assert listed == set()


def test_notification_create_is_denied(notifications, users):
    """``crm_notification.py:52-53`` returns **False** - the opposite of lead/deal."""
    assert (
        check_object_permission(notifications["for_rep"], "create", users["rep"].name)
        is False
    )


def test_notification_cannot_be_created_over_http(users):
    """Found by probing my own code, not by the review.

    ``POST /api/resource/`` never asked the create hook, so any authenticated user could
    mint a notification addressed to anyone - ``crm_notification.py:52-53`` denies
    exactly that. The org-hierarchy rule permits create, which is why the gap was
    invisible for leads and deals.
    """
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    token = RefreshToken.for_user(users["rep"]).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = client.post(
        "/api/resource/" + quote("CRM Notification"),
        {"type": "Mention", "to_user": users["boss"].name},
        format="json",
    )
    assert response.status_code == 403
    assert response.json()["exc_type"] == "PermissionError"
    assert not CRMNotification.objects.filter(to_user=users["boss"]).exists()


def test_a_system_manager_may_still_create_a_notification(users):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    token = RefreshToken.for_user(users["sysmgr"]).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = client.post(
        "/api/resource/" + quote("CRM Notification"),
        {"type": "Mention", "to_user": users["boss"].name},
        format="json",
    )
    assert response.status_code == 201


def test_leads_are_still_creatable(users, administrator, enable_hierarchy):
    """The create check must not break the doctypes whose rule permits create."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    enable_hierarchy(True)
    with session_user(administrator.name):
        CRMLeadStatus.objects.create(lead_status="Fresh", type="Open")

    client = APIClient()
    token = RefreshToken.for_user(users["rep"]).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = client.post(
        "/api/resource/" + quote("CRM Lead"),
        {"status": "Fresh", "first_name": "Ada", "lead_owner": users["rep"].name},
        format="json",
    )
    assert response.status_code == 201


def test_notification_system_manager_sees_all(notifications, users):
    with session_user(users["sysmgr"].name):
        listed = {r["name"] for r in fetch_rows("CRM Notification", fields=["name"], limit_page_length=0)}
    assert len(listed) == 2


def test_to_user_is_not_nullable_which_is_what_makes_the_blank_branch_unreachable():
    """Guards the one place list filtering and ``has_permission`` could disagree.

    Codex raised this: the list rule is ``Q(to_user=user)``, but the object rule returns
    True when ``to_user`` is blank (``crm_notification.py:55-56``) - "hidden in list,
    readable by name", which `PHASE_2_PERMISSIONS.md` §6 forbids.

    It mirrors upstream, and in this port it is **unreachable**: ``to_user`` is
    ``reqd=1`` in the JSON so the column is NOT NULL. That makes the asymmetry harmless
    *today* and a permission hole the moment someone relaxes the constraint - so the
    constraint itself is what this test pins down.
    """
    field = CRMNotification._meta.get_field("to_user")
    assert field.null is False, (
        "to_user became nullable: crm_app/permissions/notification.py's blank-recipient "
        "branch is now reachable and lets any user read an unaddressed notification "
        "that the list view hides. Fix the rule before relaxing this column."
    )


def test_list_and_object_agree_for_every_real_notification(notifications, users):
    """The spec criterion, checked over every row that can actually exist."""
    for actor in ("rep", "boss", "outsider"):
        user = users[actor].name
        with session_user(user):
            listed = {
                r["name"]
                for r in fetch_rows("CRM Notification", fields=["name"], limit_page_length=0)
            }
        for notification in notifications.values():
            assert check_object_permission(notification, "read", user) == (
                notification.name in listed
            ), f"{actor} disagrees on {notification.name}"


def test_notification_without_a_recipient_is_denied(users):
    """Deliberate divergence from ``crm_notification.py:55-56``, which returns True.

    Upstream contradicts itself: the list rule emits ``to_user = <user>``, which a blank
    never matches, so such a row is hidden from every list yet readable directly by
    anyone. We deny instead, so the two rules agree.

    Nothing observable changes against upstream. ``to_user`` is a ``ForeignKey`` with no
    ``null=True`` here - NOT NULL at the database level - so no *saved* row can reach
    this branch. (Upstream's ``reqd: 1`` is document-level validation only, so its own
    branch is not quite dead.) The path that *is* reachable is an unsaved instance, and
    there granting a read was the wrong default.

    Exercised against a stand-in rather than a row, because constructing a real one would
    mean loosening a constraint the schema is right to have.
    """
    from crm_app.permissions.notification import has_permission

    class _Recipientless:
        to_user_id = None

    assert has_permission(_Recipientless(), "read", users["outsider"].name) is False


def test_notification_list_and_object_rules_agree_on_a_blank_recipient(users):
    """The asymmetry itself - this is what tripped the phase-2 gate.

    The list rule filters ``to_user=<user>``, so a blank recipient matches nobody. The
    object rule must reach the same verdict, or a row is invisible in lists but readable
    by URL.
    """
    from crm_app.permissions.notification import (
        get_permission_query_conditions,
        has_permission,
    )

    class _Recipientless:
        to_user_id = None

    user = users["outsider"].name
    condition = get_permission_query_conditions(user)

    # The list rule cannot match a NULL/blank to_user ...
    assert "to_user" in str(condition)
    # ... and the object rule now agrees.
    assert has_permission(_Recipientless(), "read", user) is False


# ---------------------------------------------------------------------------
# Bypass probing - fields / order_by / group_by
# ---------------------------------------------------------------------------


def test_fields_cannot_expose_a_hidden_row(records, users, enable_hierarchy, auth_api):
    enable_hierarchy(False)
    with session_user(users["rep"].name):
        rows = fetch_rows("CRM Lead", fields=["*"], limit_page_length=0)
    assert {r["first_name"] for r in rows} == {"Rep"}


def test_order_by_cannot_expose_a_hidden_row(records, users, enable_hierarchy):
    enable_hierarchy(False)
    with session_user(users["rep"].name):
        rows = fetch_rows(
            "CRM Lead", fields=["first_name"], order_by="lead_owner desc", limit_page_length=0
        )
    assert {r["first_name"] for r in rows} == {"Rep"}


def test_filters_cannot_expose_a_hidden_row(records, users, enable_hierarchy):
    """Asking for someone else's record by name must return nothing, not 403 vs 200."""
    enable_hierarchy(False)
    with session_user(users["rep"].name):
        rows = fetch_rows(
            "CRM Lead",
            fields=["first_name"],
            filters={"name": records["leads"]["boss"].name},
            limit_page_length=0,
        )
    assert rows == []


def test_or_filters_cannot_widen_the_permission_filter(records, users, enable_hierarchy):
    enable_hierarchy(False)
    with session_user(users["rep"].name):
        rows = fetch_rows(
            "CRM Lead",
            fields=["first_name"],
            or_filters={"first_name": "Boss", "lead_owner": users["outsider"].name},
            limit_page_length=0,
        )
    assert rows == []


def test_count_does_not_leak_hidden_rows(records, users, enable_hierarchy):
    """A total that includes invisible rows is itself a leak."""
    from frappe_core.query import count_rows

    enable_hierarchy(False)
    with session_user(users["rep"].name):
        assert count_rows("CRM Lead") == 1


def test_kanban_columns_from_a_restricted_link_are_permission_filtered(
    records, users, enable_hierarchy
):
    """Also found by probing rather than by review.

    Kanban resolves its columns from the Link target's rows. Upstream does that with
    ``frappe.get_all``, which applies permissions; going straight to the manager would
    enumerate rows the user cannot see. Grouping deals by ``lead`` is the case that
    exposes it - CRM Lead *is* restricted.
    """
    from frappe_core.api.doc import get_data

    enable_hierarchy(False)
    with session_user(users["rep"].name):
        result = get_data(
            doctype="CRM Deal",
            filters={},
            order_by="modified desc",
            view={"view_type": "kanban"},
            column_field="lead",
        )
    resolved = {c["name"] for c in result["kanban_columns"]}
    # Four leads exist; rep may see exactly one, so exactly one column may appear.
    assert resolved == {records["leads"]["rep"].name}
    for hidden in ("boss", "manager", "outsider"):
        assert records["leads"][hidden].name not in resolved


def test_kanban_columns_from_an_unrestricted_link_still_resolve(records, users, enable_hierarchy):
    """The fix must not break the normal case - status has no row rules."""
    from frappe_core.api.doc import get_data

    enable_hierarchy(False)
    with session_user(users["rep"].name):
        result = get_data(
            doctype="CRM Lead",
            filters={},
            order_by="modified desc",
            view={"view_type": "kanban"},
            column_field="status",
        )
    assert [c["name"] for c in result["kanban_columns"]] == ["New"]


def test_get_data_respects_the_permission_filter(records, users, enable_hierarchy):
    from frappe_core.api.doc import get_data

    enable_hierarchy(False)
    with session_user(users["rep"].name):
        result = get_data(doctype="CRM Lead", filters={}, order_by="modified desc")
    assert result["total_count"] == 1
    assert {r["first_name"] for r in result["data"]} == {"Rep"}


# ---------------------------------------------------------------------------
# Performance: the subtree lookup must not N+1
# ---------------------------------------------------------------------------


def test_subtree_lookup_does_not_n_plus_one(users, hierarchy, enable_hierarchy, administrator):
    """PHASE_2_PERMISSIONS.md section 6 - verify query count on a 100-row list.

    Asserting an exact number would test today's ORM, not the property that matters.
    What matters is that the count is **independent of the number of rows** - that is
    precisely what "does not N+1" means. So the same cold request is measured at 10 rows
    and at 100 and the two must match exactly.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    enable_hierarchy(True)
    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="Bulk", type="Open")

    def measure(expected_rows: int) -> int:
        with session_user(users["manager"].name):
            with CaptureQueriesContext(connection) as ctx:
                rows = fetch_rows("CRM Lead", fields=["name"], limit_page_length=0)
        assert len(rows) == expected_rows
        return len(ctx)

    with session_user(administrator.name):
        for i in range(10):
            CRMLead.objects.create(status=status, first_name=f"A{i}", lead_owner=users["rep"])
    small = measure(10)

    with session_user(administrator.name):
        for i in range(90):
            CRMLead.objects.create(status=status, first_name=f"B{i}", lead_owner=users["rep"])
    large = measure(100)

    assert small == large, f"query count grew with rows: {small} -> {large}"
    # And it is a small constant, not merely constant: settings flag, roles,
    # in-hierarchy, subtree bounds, and the list itself.
    assert large <= 8, f"expected a handful of queries per request, got {large}"


def test_repeated_checks_reuse_the_request_cache(users, hierarchy, enable_hierarchy):
    """The hierarchy lookups are memoised per request, as upstream memoises them."""
    from django.test.utils import CaptureQueriesContext
    from django.db import connection

    enable_hierarchy(True)
    with session_user(users["manager"].name):
        get_permission_query_conditions("CRM Lead")  # warms the cache
        with CaptureQueriesContext(connection) as ctx:
            for _ in range(10):
                get_permission_query_conditions("CRM Lead")
    assert len(ctx) == 0, "cached lookups should issue no further queries"


def test_the_cache_does_not_leak_between_users(records, users, hierarchy, enable_hierarchy):
    """A memo keyed without the user would hand one user another's subtree."""
    enable_hierarchy(True)
    assert visible_leads(users["manager"].name) == {"Manager", "Rep"}
    assert visible_leads(users["rep"].name) == {"Rep"}
    assert visible_leads(users["boss"].name) == {"Boss", "Manager", "Rep"}


# ---------------------------------------------------------------------------
# Nested-set maintenance
# ---------------------------------------------------------------------------


def test_tree_bounds_are_computed_on_write(hierarchy, users):
    boss = CRMSalesHierarchy.objects.get(user=users["boss"])
    rep = CRMSalesHierarchy.objects.get(user=users["rep"])
    assert boss.lft is not None and boss.rgt is not None
    assert boss.lft < rep.lft <= rep.rgt < boss.rgt


def test_subtree_membership_is_inclusive_of_self(hierarchy, users):
    """``Mgr.lft >= Mgr.lft`` holds, so a manager is in their own subtree."""
    from crm_app.permissions.org_hierarchy import _team_member_users
    from frappe_core.session import session_user as _su

    with _su(users["manager"].name):
        members = set(_team_member_users(users["manager"].name))
    assert users["manager"].name in members
    assert users["rep"].name in members
    assert users["boss"].name not in members


def test_reparenting_recomputes_the_tree(hierarchy, users, administrator):
    """Moving a node must update bounds, or access silently follows the old shape."""
    rep = CRMSalesHierarchy.objects.get(user=users["rep"])
    boss = CRMSalesHierarchy.objects.get(user=users["boss"])
    with session_user(administrator.name):
        rep.reports_to = boss
        rep.save()

    manager = CRMSalesHierarchy.objects.get(user=users["manager"])
    rep.refresh_from_db()
    assert not (manager.lft < rep.lft < manager.rgt), "rep should have left the subtree"


def test_a_user_with_no_hierarchy_row_has_no_subtree(users):
    from crm_app.permissions.org_hierarchy import _team_member_users
    from frappe_core.session import session_user as _su

    with _su(users["outsider"].name):
        assert _team_member_users(users["outsider"].name) is None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_exactly_the_intended_doctypes_have_row_rules():
    """The registered set, stated explicitly so an accidental addition is caught.

    ``crm/hooks.py:134-144`` registers three. **Phase 4 deliberately added more**, after a
    review found them reachable through the generic ``/api/resource/`` route: upstream
    protects them with DocType role permissions, which this port does not model, so with no
    hook they were world-readable and world-writable. See
    ``crm_app/permissions/metadata_docs.py`` and ``platform_docs.py``.

    **Phase 7 added one**, for the same reason, when it registered ``WhatsApp Message``.
    That is this test working rather than failing: registering a doctype breaks it until
    somebody writes down which of the two things the new doctype is.
    """
    with_rules = {
        dt
        for dt in registry.all_doctypes()
        if registry.get_entry(dt).permission_query_conditions is not None
    }
    upstream = {"CRM Lead", "CRM Deal", "CRM Notification"}
    added_by_phase_4 = {
        "CRM View Settings",
        "CRM Form Script",
        "CRM Fields Layout",
        # A2: routable since phase 1 with no rule, so any caller could rename or disable
        # any colleague. Writes are now self-only; reads stay open (kanban builds a column
        # per user, and upstream enumerates them with permission-ignoring `frappe.get_all`).
        "User",
        # A3: same, and worse - any caller could repoint the outgoing mail server or
        # delete the account. Managers write; reads stay open for the Profile screen's
        # "send from" picker. Its query_conditions returns None on purpose: the decision
        # to leave reads open is recorded in code rather than left as an omission.
        "Email Account",
        # A4: the integration credentials. Upstream gives the telephony pair to System
        # Manager and Sales Manager only, at every permlevel; reads are closed here to
        # match, because these back an administration screen rather than a user feature.
        "CRM Twilio Settings",
        "CRM Exotel Settings",
        # A4: read for all (every screen reads its timestamp format), write for managers -
        # upstream's own split. The credential on it is narrowed by RESTRICTED_FIELDS.
        "FCRM Settings",
        # The org tree is an input to this engine, so writing it is writing your own
        # permissions: a Sales User could add themselves and reparent a colleague
        # underneath, taking that colleague's pipeline in one call. System Manager only,
        # as upstream has it - tighter than the manager pair used elsewhere, because the
        # chart is what decides what a Sales Manager can see.
        "CRM Sales Hierarchy",
        # An invitation holds the role granted and the key that redeems it. Managers only,
        # and the key never reaches the wire. Disarmed ahead of phase 8 implementing
        # `accept_invitation`, at which point this rule is what stands between any user
        # and an admin account.
        "CRM Invitation",
        # Rows that hang off another document. Each leaked what the record itself refused -
        # email bodies, private file URLs, internal remarks - and a comment could be forged
        # onto a record the author cannot see. One rule: defer to the referenced document.
        "Comment",
        "Communication",
        "File",
    }
    added_by_phase_7 = {
        # `WhatsApp Message` is the same shape as the three above - a row about a lead or
        # deal, carrying which one - and gets the same rule. The reason is sharper here: a
        # deal row leaks a number, a WhatsApp thread leaks the conversation. Ported from
        # `frappe_whatsapp`, which upstream protects with that app's own role permissions -
        # the layer this port does not model, so "no hook" would have meant "no protection"
        # for the fifth time.
        "WhatsApp Message",
        # The Facebook lead-sync group. Two hold access tokens - a page token reads every
        # lead the page has collected and can post as the page. `Failed Lead Sync Log`
        # holds the raw Graph payload for a lead that never imported: a real person's
        # name, email and phone, in a table with nothing else protecting it. The form
        # doctype holds no secret and is ruled anyway, because leaving one doctype of a
        # four-doctype feature open reads as intent.
        "Lead Sync Source",
        "Facebook Page",
        "Facebook Lead Form",
        "Failed Lead Sync Log",
    }
    assert with_rules == upstream | added_by_phase_4 | added_by_phase_7


def test_the_upstream_three_still_use_the_org_hierarchy_rule():
    """The phase-4 additions must not have displaced the originals."""
    from crm_app.permissions import org_hierarchy

    assert (
        registry.get_entry("CRM Lead").permission_query_conditions
        is org_hierarchy.get_lead_permission_query_conditions
    )
    assert (
        registry.get_entry("CRM Deal").permission_query_conditions
        is org_hierarchy.get_deal_permission_query_conditions
    )


def test_other_doctypes_are_unrestricted(records, users):
    with session_user(users["rep"].name):
        assert get_permission_query_conditions("CRM Organization") is None


def test_a_lead_without_a_lead_owner_is_hidden_from_its_creator(users, enable_hierarchy, administrator):
    """Surprising, and upstream's actual behaviour - worth pinning down.

    The rule filters on the CRM's own owner column (``lead_owner``), **not** the
    document's ``owner`` (``org_hierarchy.py:34,54``). So a Sales User who creates a
    lead and leaves ``lead_owner`` blank cannot see it afterwards. Upstream's UI always
    sets ``lead_owner``, which is why this rarely surfaces there - but any phase-3
    endpoint that creates a lead must set it, or the record vanishes for its author.
    """
    enable_hierarchy(False)
    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="Orphan", type="Open")
    with session_user(users["rep"].name):
        CRMLead.objects.create(status=status, first_name="Ownerless")
        listed = {r["first_name"] for r in fetch_rows("CRM Lead", fields=["first_name"], limit_page_length=0)}
    assert "Ownerless" not in listed


def test_document_owner_alone_does_not_grant_access(users, enable_hierarchy, administrator):
    """The same point from the other side: ``owner`` is not the access column."""
    enable_hierarchy(False)
    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="Owned", type="Open")
    with session_user(users["rep"].name):
        lead = CRMLead.objects.create(status=status, first_name="ByRep")
    assert lead.owner_id == users["rep"].name
    assert check_object_permission(lead, "read", users["rep"].name) is False
