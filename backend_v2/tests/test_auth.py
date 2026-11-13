import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
LOGOUT = "/api/v1/auth/logout/"
REFRESH = "/api/v1/auth/token/refresh/"
ME = "/api/v1/auth/me/"


def login(api, usr, pwd):
    return api.post(LOGIN, {"usr": usr, "pwd": pwd}, format="json")


def test_login_returns_a_token_pair_in_a_message_envelope(api, alice):
    response = login(api, alice.name, "secret123")
    assert response.status_code == 200
    assert set(response.json()) == {"message"}
    assert {"access", "refresh"} <= set(response.json()["message"])


def test_login_is_reachable_without_authentication(api, alice):
    assert login(api, alice.name, "secret123").status_code == 200


def test_login_reports_the_user(api, alice):
    assert login(api, alice.name, "secret123").json()["message"]["user"] == alice.name


def test_login_with_a_bad_password_is_an_authentication_error(api, alice):
    response = login(api, alice.name, "wrong")
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"
    assert response.json()["messages"] == ["Invalid login credentials"]


def test_login_with_an_unknown_user_is_an_authentication_error(api):
    response = login(api, "nobody@example.com", "secret123")
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"


def test_login_without_credentials_is_a_validation_error(api):
    response = api.post(LOGIN, {}, format="json")
    assert response.status_code == 417
    assert response.json()["exc_type"] == "ValidationError"


def test_disabled_user_cannot_log_in(api, make_user):
    make_user("disabled@example.com", enabled=False)
    assert login(api, "disabled@example.com", "secret123").status_code == 401


def test_login_is_case_insensitive_on_the_email(api, alice):
    response = login(api, "ALICE@Example.com", "secret123")
    assert response.status_code == 200
    assert response.json()["message"]["user"] == alice.name


def test_administrator_logs_in_under_its_capitalised_name(api, administrator):
    administrator.set_password("secret123")
    administrator.save()
    response = login(api, "administrator", "secret123")
    assert response.status_code == 200
    assert response.json()["message"]["user"] == "Administrator"


def test_disabled_user_is_reported_disabled_whatever_the_casing(api, make_user):
    make_user("disabled@example.com", enabled=False)
    response = login(api, "Disabled@Example.com", "secret123")
    assert response.status_code == 401
    assert response.json()["messages"] == ["User disabled or missing"]


def test_a_wrong_password_on_a_disabled_account_reads_like_any_wrong_password(api, make_user):
    make_user("disabled@example.com", enabled=False)
    response = login(api, "disabled@example.com", "wrong")
    assert response.status_code == 401
    assert response.json()["messages"] == ["Invalid login credentials"]


def test_an_exact_name_wins_over_a_case_insensitive_match(api, administrator, make_user):
    administrator.set_password("admin-secret")
    administrator.save()
    make_user("administrator", password="shadow-secret")
    assert login(api, "Administrator", "admin-secret").json()["message"]["user"] == "Administrator"
    assert login(api, "administrator", "shadow-secret").json()["message"]["user"] == "administrator"
    assert login(api, "administrator", "admin-secret").status_code == 401


def test_token_from_login_reaches_an_authenticated_endpoint(api, alice):
    token = login(api, alice.name, "secret123").json()["message"]["access"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert api.get(ME).status_code == 200


def test_the_same_endpoint_is_401_without_the_header(api, alice):
    assert api.get(ME).status_code == 401


def test_a_garbage_token_is_rejected(api):
    api.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
    assert api.get(ME).status_code == 401


def test_a_garbage_token_is_an_authentication_error(api):
    api.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
    body = api.get(ME).json()
    assert body["exc_type"] == "AuthenticationError"
    assert body["messages"] == ["Given token not valid for any token type"]


def test_token_identifies_the_right_user(api, alice, bob):
    token = login(api, bob.name, "secret123").json()["message"]["access"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert api.get(ME).json() == {"message": bob.name}


def test_get_logged_user_returns_the_email(api, alice):
    token = login(api, alice.name, "secret123").json()["message"]["access"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = api.get(ME)
    assert response.status_code == 200
    assert response.json() == {"message": alice.name}


def test_refresh_returns_a_new_access_token(api, alice):
    refresh = login(api, alice.name, "secret123").json()["message"]["refresh"]
    response = api.post(REFRESH, {"refresh": refresh}, format="json")
    assert response.status_code == 200
    assert "access" in response.json()["message"]


def test_refreshed_token_authenticates(api, alice):
    refresh = login(api, alice.name, "secret123").json()["message"]["refresh"]
    access = api.post(REFRESH, {"refresh": refresh}, format="json").json()["message"]["access"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    assert api.get(ME).status_code == 200


def test_refresh_rejects_a_bad_token(api):
    response = api.post(REFRESH, {"refresh": "nonsense"}, format="json")
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"


def test_refresh_requires_a_token(api):
    assert api.post(REFRESH, {}, format="json").status_code == 417


def test_logout_succeeds(auth_api):
    response = auth_api.post(LOGOUT, {}, format="json")
    assert response.status_code == 200
    assert response.json() == {"message": {"message": "Logged Out"}}


def test_logout_blacklists_the_refresh_token_it_is_given(api, alice):
    pair = login(api, alice.name, "secret123").json()["message"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {pair['access']}")
    assert api.post(LOGOUT, {"refresh": pair["refresh"]}, format="json").status_code == 200
    api.credentials()
    response = api.post(REFRESH, {"refresh": pair["refresh"]}, format="json")
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"


def test_logout_without_a_refresh_token_revokes_nothing(api, alice):
    pair = login(api, alice.name, "secret123").json()["message"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {pair['access']}")
    assert api.post(LOGOUT, {}, format="json").status_code == 200
    api.credentials()
    assert api.post(REFRESH, {"refresh": pair["refresh"]}, format="json").status_code == 200


def test_user_primary_key_is_the_email(alice):
    assert alice.pk == "alice@example.com"
    assert get_user_model()._meta.pk.name == "name"


def test_administrator_is_seeded_with_its_roles(administrator):
    assert {"Administrator", "System Manager"} <= administrator.get_roles()


def test_the_four_roles_are_seeded(db):
    assert {"Administrator", "System Manager", "Sales Manager", "Sales User"} <= set(Group.objects.values_list("name", flat=True))


def test_guest_is_seeded(db):
    assert get_user_model().objects.filter(name="Guest").exists()


def test_administrator_carries_its_role_even_without_a_group(db):
    admin = get_user_model().objects.get(name="Administrator")
    admin.groups.clear()
    assert "Administrator" in admin.get_roles()


def test_roles_come_from_django_groups(alice):
    assert alice.has_role("Sales User")
    assert not alice.has_role("System Manager")


@pytest.mark.parametrize("route", [LOGIN, LOGOUT, REFRESH, ME])
def test_auth_routes_accept_no_trailing_slash(api, route, alice):
    bare = route.rstrip("/")
    if route == LOGIN:
        response = api.post(bare, {"usr": alice.name, "pwd": "secret123"}, format="json")
    elif route == REFRESH:
        token = login(api, alice.name, "secret123").json()["message"]["refresh"]
        response = api.post(bare, {"refresh": token}, format="json")
    else:
        token = login(api, alice.name, "secret123").json()["message"]["access"]
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = api.get(bare) if route == ME else api.post(bare, {}, format="json")
    assert response.status_code == 200
