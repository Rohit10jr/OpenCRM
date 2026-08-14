import pytest
from django.contrib.auth.models import Group
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from frappe_platform.models import User


@pytest.fixture(autouse=True)
def builtin_users(request):
    """Guarantee Frappe's two built-in User rows exist.

    They are seeded by ``frappe_platform/migrations/0002``, but a
    ``transaction=True`` test flushes every table at teardown *without* re-running data
    migrations - so the next test starts without them. ``BaseDocument.save`` stamps
    ``owner``/``modified_by`` with the ambient user, which is ``Guest`` outside a
    request, so their absence breaks every create.

    This restores the invariant the migration establishes in production rather than
    weakening the model to tolerate a dangling FK.
    """
    marker = request.node.get_closest_marker("django_db")
    wants_db = (
        marker is not None
        or "db" in request.fixturenames
        or "transactional_db" in request.fixturenames
    )
    if not wants_db:
        return
    # Force the database fixture to finish setting up before we touch the ORM; an
    # autouse fixture is otherwise free to run first.
    transactional = bool(marker and marker.kwargs.get("transaction"))
    request.getfixturevalue("transactional_db" if transactional else "db")

    for name, first_name, user_type in (
        ("Administrator", "Administrator", "System User"),
        ("Guest", "Guest", "Website User"),
    ):
        User.objects.get_or_create(
            name=name,
            defaults={
                "email": f"{name.lower()}@example.com",
                "first_name": first_name,
                "full_name": first_name,
                "enabled": True,
                "user_type": user_type,
            },
        )


@pytest.fixture
def make_user(db):
    def _make(name, password="secret123", roles=(), **extra):
        user = User.objects.create_user(name=name, password=password, **extra)
        for role in roles:
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)
        return user

    return _make


@pytest.fixture
def alice(make_user):
    return make_user("alice@example.com", first_name="Alice", roles=["Sales User"])


@pytest.fixture
def bob(make_user):
    return make_user("bob@example.com", first_name="Bob", roles=["Sales User"])


@pytest.fixture
def administrator(db):
    return User.objects.get(name="Administrator")


@pytest.fixture
def api():
    """Unauthenticated DRF client."""
    return APIClient()


@pytest.fixture
def auth_api(alice):
    """Client carrying a real ``Authorization: Bearer`` header for ``alice``.

    Deliberately a genuine JWT rather than ``force_authenticate`` - the point is to
    prove the token path the patched frappe-ui uses actually reaches the endpoint.
    """
    client = APIClient()
    token = RefreshToken.for_user(alice).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def as_user():
    """Run a block with the ambient session user set, like ``frappe.set_user``."""
    from frappe_core.session import session_user

    return session_user
