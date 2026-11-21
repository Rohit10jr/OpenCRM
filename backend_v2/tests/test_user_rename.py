"""User and CRM Invitation rename (specs/ACCOUNTS.md §10.10, PE-32, PE-24).

New: `backend/tests` has no User rename case to port (checked 21 Nov 2026), and the old
backend never renames a User.
"""

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import CRMInvitation, CRMSalesHierarchy, User
from accounts.services import issue_tokens
from core.security import LoginAttemptTracker
from tests_support.models import Widget

pytestmark = pytest.mark.django_db
USERS = "/api/v1/users/"


def rename(client, name, new_name):
    return client.post(f"{USERS}{name}/rename/", {"new_name": new_name}, format="json")


def whoami(api, access):
    return api.get("/api/v1/auth/me/", HTTP_AUTHORIZATION=f"Bearer {access}")


def refresh(api, token):
    return api.post("/api/v1/auth/token/refresh/", {"refresh": token}, format="json")


@pytest.fixture
def boss(make_user):
    return make_user("boss@example.com", roles=["System Manager"])


@pytest.fixture
def carol(make_user):
    return make_user("carol@example.com", roles=["Sales User"], email="carol@example.com")


# --- who -------------------------------------------------------------------------------------


def test_a_sales_user_cannot_rename_their_own_account(carol, api_as):
    response = rename(api_as(carol), carol.name, "carol2@example.com")
    assert response.status_code == 417
    assert response.json()["message"] == f"You need write permission on User {carol.name} to rename"


def test_a_sales_manager_cannot_rename(make_user, carol, api_as):
    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    assert rename(api_as(manager), carol.name, "carol2@example.com").status_code == 417


def test_a_system_manager_renames_a_user(boss, carol, api_as):
    response = rename(api_as(boss), carol.name, "carol2@example.com")
    assert response.status_code == 200, response.content[:300]
    assert response.json() == {"message": "carol2@example.com"}
    renamed = User.objects.get(pk="carol2@example.com")
    assert renamed.email == "carol2@example.com"
    assert not User.objects.filter(pk=carol.name).exists()


def test_a_system_manager_renames_their_own_account_and_is_signed_out(boss, api, api_as):
    tokens = issue_tokens(boss)
    response = rename(api_as(boss), boss.name, "boss2@example.com")
    assert response.status_code == 200, response.content[:300]
    assert whoami(api, tokens["access"]).status_code == 401
    assert refresh(api, tokens["refresh"]).status_code == 401


# --- refusals, in upstream's order -------------------------------------------------------------


@pytest.mark.parametrize("caller", ["boss", "administrator"])
@pytest.mark.parametrize("builtin", ["Administrator", "Guest"])
def test_a_builtin_cannot_be_renamed(request, api_as, caller, builtin):
    response = rename(api_as(request.getfixturevalue(caller)), builtin, "x@example.com")
    assert response.status_code == 417
    assert response.json()["message"] == f"User {builtin} cannot be renamed"


@pytest.mark.parametrize(
    "new_name,shown",
    [
        ("not-an-address", "not-an-address"),
        ("a@x.com, b@x.com", "a@x.com, b@x.com"),
        # Printed as typed, as upstream's validate_email_address (A-76 finding 3).
        ("Bob <b@x.com>", "Bob &lt;b@x.com&gt;"),
    ],
)
def test_the_new_name_is_one_plain_address(boss, carol, api_as, new_name, shown):
    response = rename(api_as(boss), carol.name, new_name)
    assert response.status_code == 417
    assert response.json()["message"] == f"{shown} is not a valid Email Address"


def test_a_new_name_over_140_characters_is_417_not_500(boss, carol, api_as):
    """A-76 finding 4: Django's address check allows 320 characters; the column 140."""
    long_name = "a" * 130 + "@example.com"
    response = rename(api_as(boss), carol.name, long_name)
    assert response.status_code == 417
    assert response.json()["message"] == (
        f"User {carol.name}: '<strong>Email</strong>' ({long_name}) will get truncated, "
        "as max characters allowed is 140"
    )
    assert User.objects.filter(pk=carol.name).exists()


def test_the_same_name_after_normalising_is_no_change(boss, carol, api_as):
    response = rename(api_as(boss), carol.name, "  CAROL@example.com ")
    assert response.status_code == 417
    assert response.json()["message"] == "No changes made because old and new name are the same."


def test_another_accounts_name_differing_only_by_case_is_taken(boss, carol, make_user, api_as):
    make_user("dave@example.com")
    response = rename(api_as(boss), carol.name, "DAVE@example.com")
    assert response.status_code == 417
    assert response.json()["message"] == "Another User with name dave@example.com exists, select another name"


def test_a_legacy_mixed_case_row_takes_its_own_lowercase_form(boss, api_as):
    User.objects.bulk_create([User(name="Legacy@Example.com", email="Legacy@Example.com")])
    response = rename(api_as(boss), "Legacy@Example.com", "legacy@example.com")
    assert response.status_code == 200, response.content[:300]
    assert User.objects.filter(pk="legacy@example.com").exists()


def test_a_leading_space_never_reaches_the_database(boss, carol, api_as):
    response = rename(api_as(boss), carol.name, " new.carol@example.com")
    assert response.status_code == 200, response.content[:300]
    assert User.objects.filter(pk="new.carol@example.com").exists()


# --- what follows the rename -------------------------------------------------------------------


def test_owner_modified_by_groups_permissions_and_hierarchy_follow(boss, carol, administrator, api_as):
    row = Widget(name="W-1", widget_name="W-1", widget_owner=carol)
    row.save(user=carol)
    carol.user_permissions.add(Permission.objects.first())
    CRMSalesHierarchy(user=carol).save(user=administrator)

    assert rename(api_as(boss), carol.name, "carol2@example.com").status_code == 200

    renamed = User.objects.get(pk="carol2@example.com")
    widget = Widget.objects.get(pk="W-1")
    assert widget.owner_id == renamed.pk and widget.modified_by_id == renamed.pk
    assert set(renamed.groups.values_list("name", flat=True)) == {"Sales User"}
    assert renamed.user_permissions.count() == 1
    assert CRMSalesHierarchy.objects.filter(user=renamed).count() == 1


def test_the_caches_are_rewritten_exactly(boss, carol, api_as):
    row = Widget(name="W-1", widget_name="W-1", widget_owner=carol)
    row.save(user=carol)
    Widget.objects.filter(pk="W-1").update(
        _assign=[carol.name, "x" + carol.name], _liked_by=[carol.name]
    )
    modified = Widget.objects.get(pk="W-1").modified

    rename(api_as(boss), carol.name, "carol2@example.com")

    widget = Widget.objects.get(pk="W-1")
    assert widget._assign == ["carol2@example.com", "x" + carol.name]
    assert widget._liked_by == ["carol2@example.com"]
    assert widget.modified == modified


def test_the_reset_key_is_cleared(boss, carol, api_as):
    from django.utils import timezone

    User.objects.filter(pk=carol.pk).update(
        reset_password_key="abc", last_reset_password_key_generated_on=timezone.now()
    )
    rename(api_as(boss), carol.name, "carol2@example.com")
    renamed = User.objects.get(pk="carol2@example.com")
    assert renamed.reset_password_key == ""
    assert renamed.last_reset_password_key_generated_on is None


# --- tokens ------------------------------------------------------------------------------------


def test_every_outstanding_refresh_token_is_blacklisted(boss, carol, api, api_as):
    first, second = issue_tokens(carol), issue_tokens(carol)
    old_version = User.objects.get(pk=carol.pk).token_version

    rename(api_as(boss), carol.name, "carol2@example.com")

    renamed = User.objects.get(pk="carol2@example.com")
    assert renamed.token_version != old_version
    # verify=False: a blacklisted token cannot be parsed the normal way any more.
    jtis = {RefreshToken(t["refresh"], verify=False)["jti"] for t in (first, second)}
    outstanding = OutstandingToken.objects.filter(jti__in=jtis)
    assert {t.user_id for t in outstanding} == {renamed.pk}
    assert BlacklistedToken.objects.filter(token__jti__in=jtis).count() == 2
    for tokens in (first, second):
        assert whoami(api, tokens["access"]).status_code == 401
        assert refresh(api, tokens["refresh"]).status_code == 401


def test_a_fresh_login_works_after_the_rename(boss, carol, api, api_as):
    carol.set_password("Ren4med!pass")
    carol.save()
    rename(api_as(boss), carol.name, "carol2@example.com")
    response = api.post("/api/v1/auth/login/", {"usr": "carol2@example.com", "pwd": "Ren4med!pass"}, format="json")
    assert response.status_code == 200, response.content[:300]


def test_a_new_account_under_the_old_name_refuses_the_old_tokens(boss, carol, api, api_as):
    old = issue_tokens(carol)
    rename(api_as(boss), carol.name, "carol2@example.com")

    response = api_as(boss).post(USERS, {"name": "carol@example.com", "email": "carol@example.com"}, format="json")
    assert response.status_code == 200, response.content[:300]

    assert whoami(api, old["access"]).status_code == 401
    assert refresh(api, old["refresh"]).status_code == 401


def test_an_invited_account_under_the_old_name_refuses_the_old_tokens(
    boss, carol, administrator, api, api_as
):
    """A-76 finding 1: the invitation is made before the rename and accepted after;
    the accept creates a fresh account under the old address (ACCOUNTS §10.8)."""
    CRMInvitation(email=carol.name, role="Sales User", status="Pending", key="k-old").save(
        user=administrator
    )
    old = issue_tokens(carol)
    rename(api_as(boss), carol.name, "carol2@example.com")

    accepted = api.post("/api/v1/auth/accept-invitation/", {"key": "k-old"}, format="json")
    assert accepted.status_code == 200, accepted.content[:300]
    newcomer = User.objects.get(pk=carol.name)

    assert whoami(api, old["access"]).status_code == 401
    assert refresh(api, old["refresh"]).status_code == 401
    fresh = issue_tokens(newcomer)
    assert whoami(api, fresh["access"]).status_code == 200


def test_a_swap_leaves_neither_accounts_old_tokens_valid(boss, make_user, api, api_as):
    """A-76 finding 2: A to C, then B to A."""
    a = make_user("a@example.com")
    b = make_user("b@example.com")
    a_tokens, b_tokens = issue_tokens(a), issue_tokens(b)
    client = api_as(boss)
    assert rename(client, a.name, "c@example.com").status_code == 200
    assert rename(client, b.name, "a@example.com").status_code == 200

    for tokens in (a_tokens, b_tokens):
        assert whoami(api, tokens["access"]).status_code == 401
        assert refresh(api, tokens["refresh"]).status_code == 401


def test_a_deleted_and_recreated_account_refuses_the_first_accounts_tokens(administrator, make_user, api):
    first = make_user("again@example.com")
    old = issue_tokens(first)
    OutstandingToken.objects.filter(user=first).delete()
    first.delete()
    make_user("again@example.com")
    assert whoami(api, old["access"]).status_code == 401
    # A-76 finding 2: nothing blacklisted it; the version alone refuses it.
    assert refresh(api, old["refresh"]).status_code == 401


# --- atomic and lockout ------------------------------------------------------------------------


def test_a_failure_inside_the_rename_leaves_everything(boss, carol, api_as, monkeypatch):
    from accounts import rename as user_rename

    tokens = issue_tokens(carol)
    version = User.objects.get(pk=carol.pk).token_version

    def fail(user):
        raise RuntimeError("forced")

    monkeypatch.setattr(user_rename, "revoke_all_tokens", fail)
    with pytest.raises(RuntimeError):
        rename(api_as(boss), carol.name, "carol2@example.com")

    assert User.objects.get(pk=carol.pk).token_version == version
    assert not User.objects.filter(pk="carol2@example.com").exists()
    jti = RefreshToken(tokens["refresh"])["jti"]
    assert not BlacklistedToken.objects.filter(token__jti=jti).exists()


def test_the_old_lockout_key_is_gone_after_commit(boss, carol, api_as, django_capture_on_commit_callbacks):
    tracker = LoginAttemptTracker(carol.name)
    for _ in range(3):
        tracker.add_failure_attempt()
    assert cache.get(tracker._cache_key) is not None
    with django_capture_on_commit_callbacks(execute=True):
        assert rename(api_as(boss), carol.name, "carol2@example.com").status_code == 200
    assert cache.get(tracker._cache_key) is None


def test_a_legacy_mixed_case_names_lockout_key_is_found(boss, api_as, django_capture_on_commit_callbacks):
    """A-76 finding 5: login keys the tracker on the lowercased name."""
    User.objects.bulk_create([User(name="Legacy@Example.com", email="Legacy@Example.com")])
    tracker = LoginAttemptTracker("legacy@example.com")
    tracker.add_failure_attempt()
    with django_capture_on_commit_callbacks(execute=True):
        assert rename(api_as(boss), "Legacy@Example.com", "legacy2@example.com").status_code == 200
    assert cache.get(tracker._cache_key) is None


# --- CRM Invitation ----------------------------------------------------------------------------


def test_a_renamed_invitation_is_still_accepted_by_its_key(boss, administrator, api, api_as):
    invitation = CRMInvitation(email="joiner@example.com", role="Sales User", status="Pending", key="k-ren")
    invitation.save(user=administrator)
    response = api_as(boss).post(
        f"/api/v1/invitations/{invitation.pk}/rename/", {"new_name": "INV-RENAMED"}, format="json"
    )
    assert response.status_code == 200, response.content[:300]
    accept = api.post("/api/v1/auth/accept-invitation/", {"key": "k-ren"}, format="json")
    assert accept.status_code == 200, accept.content[:300]


def test_a_sales_manager_cannot_rename_an_invitation(make_user, administrator, api_as):
    invitation = CRMInvitation(email="j2@example.com", role="Sales User", status="Pending", key="k2")
    invitation.save(user=administrator)
    manager = make_user("mgr@example.com", roles=["Sales Manager"])
    response = api_as(manager).post(
        f"/api/v1/invitations/{invitation.pk}/rename/", {"new_name": "X"}, format="json"
    )
    assert response.status_code == 417
    assert Group.objects.exists()  # nothing else touched
    assert CRMInvitation.objects.filter(pk=invitation.pk).exists()
