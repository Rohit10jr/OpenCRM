"""Role management (specs/ACCOUNTS.md section 4.2).

The first case is ported from ``backend/tests/test_phase3_endpoints.py:542``;
`crm.api.user.*` becomes `POST /api/v1/users/add-existing/` and
`POST /api/v1/users/<name>/update-role/` / `remove-crm-roles/`. The rest are new: no old
test covers them, and each pins a refusal or order the `.http` blocks check.
"""

import pytest
from django.contrib.auth.models import Group

from accounts.models import CRMSalesHierarchy

pytestmark = pytest.mark.django_db
USERS = "/api/v1/users/"


def roles(user):
    user.refresh_from_db()
    return user.get_roles()


def update_role(client, name, new_role):
    return client.post(f"{USERS}{name}/update-role/", {"new_role": new_role}, format="json")


@pytest.fixture
def grace(make_user):
    return make_user("grace@example.com", roles=["Sales Manager", "Sales User"])


@pytest.fixture
def boss(make_user):
    return make_user("boss@example.com", roles=["System Manager"])


def test_remove_self_is_refused_with_the_upstream_message(auth_api, alice):
    group, _ = Group.objects.get_or_create(name="Sales Manager")
    alice.groups.add(group)
    response = auth_api.post(f"{USERS}{alice.name}/remove-crm-roles/", {}, format="json")
    assert response.json()["messages"] == ["You cannot remove yourself."]


def test_a_sales_user_is_not_permitted(auth_api, bob):
    response = update_role(auth_api, bob.name, "Sales User")
    assert response.status_code == 403
    assert response.json()["messages"] == ["Not permitted"]


def test_a_sales_manager_changes_another_users_role_without_the_object_rule(
    grace, bob, api_as
):
    """`09` 3.2: User's write rule would refuse this; the old action never applies it."""
    bob.groups.clear()
    response = update_role(api_as(grace), bob.name, "Sales User")
    assert response.status_code == 200
    assert response.json() == {"message": None}
    assert roles(bob) == {"Sales User"}


def test_the_role_value_is_checked_before_the_user(grace, api_as):
    response = update_role(api_as(grace), "missing@example.com", "Guest")
    assert response.status_code == 417
    assert response.json()["messages"] == ["Cannot assign this role"]


def test_a_missing_user_is_417_not_404(grace, api_as):
    response = update_role(api_as(grace), "missing@example.com", "Sales User")
    assert response.status_code == 417
    assert response.json()["messages"] == ["User missing@example.com not found"]


@pytest.mark.parametrize(
    "new_role,message",
    [
        ("System Manager", "Only System Managers can assign the System Manager role"),
        ("Sales Manager", "Only System Managers can assign the Sales Manager role"),
    ],
)
def test_a_sales_manager_cannot_promote(grace, bob, api_as, new_role, message):
    response = update_role(api_as(grace), bob.name, new_role)
    assert response.status_code == 403
    assert response.json()["messages"] == [message]


def test_a_sales_manager_cannot_modify_a_system_manager(grace, boss, api_as):
    response = update_role(api_as(grace), boss.name, "Sales User")
    assert response.status_code == 403
    assert response.json()["messages"] == [
        "Only System Managers can modify other System Managers"
    ]


def test_role_sets_follow_the_new_role(boss, bob, api_as):
    client = api_as(boss)
    update_role(client, bob.name, "System Manager")
    assert roles(bob) == {"System Manager", "Sales Manager", "Sales User"}
    update_role(client, bob.name, "Sales Manager")
    assert roles(bob) == {"Sales Manager", "Sales User"}


def test_demoting_a_tree_root_or_a_manager_with_reports_is_refused(
    boss, bob, alice, administrator, api_as
):
    top = CRMSalesHierarchy(user=bob)
    top.save(user=administrator)
    CRMSalesHierarchy(user=alice, reports_to=top).save(user=administrator)

    response = update_role(api_as(boss), bob.name, "Sales User")

    assert response.status_code == 417
    assert response.json()["messages"] == [
        "Remove this user from the sales hierarchy before changing their role to Sales User"
    ]


def test_add_existing_users_defaults_to_sales_user(grace, make_user, api_as):
    newcomer = make_user("new@example.com")
    response = api_as(grace).post(
        f"{USERS}add-existing/", {"users": '["new@example.com"]'}, format="json"
    )
    assert response.status_code == 200
    assert roles(newcomer) == {"Sales User"}


def test_remove_crm_roles_drops_roles_and_the_hierarchy_node(
    grace, bob, administrator, api_as
):
    CRMSalesHierarchy(user=bob).save(user=administrator)

    response = api_as(grace).post(f"{USERS}{bob.name}/remove-crm-roles/", {}, format="json")

    assert response.json() == {"message": f"User {bob.name} has been removed from CRM roles."}
    assert roles(bob) == set()
    assert not CRMSalesHierarchy.objects.filter(user=bob).exists()


def test_an_empty_role_is_refused_not_defaulted(grace, make_user, api_as):
    """The default applies only when `role` is absent (old user.py:111, A-23)."""
    make_user("new@example.com")
    response = api_as(grace).post(
        f"{USERS}add-existing/", {"users": ["new@example.com"], "role": ""}, format="json"
    )
    assert response.status_code == 417
    assert response.json()["messages"] == ["Cannot assign this role"]


@pytest.mark.parametrize("target", ["Administrator", "Guest"])
def test_update_role_refuses_a_builtin_account(boss, api_as, target):
    """PE-28."""
    before = roles(boss._meta.model.objects.get(pk=target))
    response = update_role(api_as(boss), target, "Sales User")
    assert response.status_code == 403
    assert response.json()["messages"] == ["Not permitted"]
    assert roles(boss._meta.model.objects.get(pk=target)) == before


@pytest.mark.parametrize("target", ["Administrator", "Guest"])
def test_add_existing_users_refuses_a_builtin_account(boss, api_as, target):
    """PE-28: the per-name check is update_user_role's."""
    response = api_as(boss).post(
        f"{USERS}add-existing/", {"users": [target], "role": "Sales User"}, format="json"
    )
    assert response.status_code == 403
    assert response.json()["messages"] == ["Not permitted"]


@pytest.mark.parametrize("target", ["Administrator", "Guest"])
def test_remove_crm_roles_refuses_a_builtin_account(boss, api_as, target):
    """PE-28."""
    account = boss._meta.model.objects.get(pk=target)
    before = roles(account)
    response = api_as(boss).post(f"{USERS}{target}/remove-crm-roles/", {}, format="json")
    assert response.status_code == 403
    assert response.json()["messages"] == ["Not permitted"]
    assert roles(account) == before


@pytest.mark.parametrize("path", ["update-role", "remove-crm-roles"])
def test_a_sales_manager_on_administrator_keeps_the_upstream_refusal(grace, api_as, path):
    """PE-28 runs after the target-role checks: Administrator holds System Manager, so a
    Sales Manager gets upstream's sentence, not "Not permitted" (A-64 finding 5)."""
    response = api_as(grace).post(
        f"{USERS}Administrator/{path}/", {"new_role": "Sales User"}, format="json"
    )
    assert response.status_code == 403
    assert response.json()["messages"] == [
        "Only System Managers can modify other System Managers"
    ]


def test_administrator_removing_itself_still_gets_the_self_message(administrator, api_as):
    """The self check runs first, as upstream (user.py:190-191)."""
    response = api_as(administrator).post(
        f"{USERS}Administrator/remove-crm-roles/", {}, format="json"
    )
    assert response.status_code == 403
    assert response.json()["messages"] == ["You cannot remove yourself."]


def test_a_caller_who_demotes_themselves_is_refused_for_the_next_name(
    grace, bob, api_as
):
    """The old loop re-reads the caller's roles per name (user.py:21-25, A-23)."""
    bob.groups.clear()
    response = api_as(grace).post(
        f"{USERS}add-existing/",
        {"users": [grace.name, bob.name], "role": "Sales User"},
        format="json",
    )
    assert roles(grace) == {"Sales User"}
    assert response.status_code == 403
    assert response.json()["messages"] == ["Not permitted"]
    assert roles(bob) == set()
