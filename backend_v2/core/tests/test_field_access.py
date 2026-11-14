import pytest
from django.contrib.auth.models import Group

from core.field_access import (
    encrypted_fields,
    hidden_from,
    is_hidden,
    is_sensitive,
    privileged_roles,
    privileged_write_fields,
    privileged_write_roles,
    readonly_fields,
    restricted_fields,
    sensitive_fields,
    unwritable_by,
)
from tests_support.models import SecuredDocument, Widget


pytestmark = pytest.mark.django_db


def test_global_sensitive_fields_apply_without_a_model_declaration():
    assert sensitive_fields(Widget) == {"password", "last_login"}
    assert is_sensitive(Widget, "password")
    assert is_sensitive(Widget, "last_login")


def test_model_declarations_are_read_without_mutating_them():
    assert sensitive_fields(SecuredDocument) == {
        "password",
        "last_login",
        "secret",
        "encrypted_secret",
    }
    assert restricted_fields(SecuredDocument) == {"manager_note"}
    assert readonly_fields(SecuredDocument) == {"audit_value"}
    assert privileged_write_fields(SecuredDocument) == {"manager_value"}
    assert privileged_roles(SecuredDocument) == {"System Manager", "Sales Manager"}
    assert privileged_write_roles(SecuredDocument) == {
        "System Manager",
        "Sales Manager",
    }
    assert encrypted_fields(SecuredDocument) == {"encrypted_secret"}


def test_restricted_field_visibility_by_role(make_user, administrator):
    sales_user = make_user("sales@example.com", roles=["Sales User"])
    sales_manager = make_user("manager@example.com", roles=["Sales Manager"])
    system_manager = make_user("system@example.com", roles=["System Manager"])

    assert is_hidden(SecuredDocument, "manager_note", sales_user)
    assert is_hidden(SecuredDocument, "manager_note", None)
    assert not is_hidden(SecuredDocument, "manager_note", sales_manager)
    assert not is_hidden(SecuredDocument, "manager_note", system_manager)
    assert not is_hidden(SecuredDocument, "manager_note", administrator)
    assert "manager_note" in hidden_from(SecuredDocument, sales_user)
    assert "manager_note" not in hidden_from(SecuredDocument, sales_manager)


def test_sensitive_field_visibility_performs_no_query(alice, django_assert_num_queries):
    with django_assert_num_queries(0):
        assert is_hidden(SecuredDocument, "secret", alice)


def test_roles_are_cached_on_the_user_instance(alice, django_assert_num_queries):
    with django_assert_num_queries(1):
        for _ in range(20):
            assert is_hidden(SecuredDocument, "manager_note", alice)


def test_role_cache_can_be_cleared_and_refresh_clears_it(alice):
    manager_group = Group.objects.get(name="Sales Manager")
    assert "Sales Manager" not in alice.get_roles()
    alice.groups.add(manager_group)
    assert "Sales Manager" not in alice.get_roles()

    alice.clear_roles_cache()
    assert "Sales Manager" in alice.get_roles()
    alice.groups.remove(manager_group)
    assert "Sales Manager" in alice.get_roles()

    alice.refresh_from_db()
    assert "Sales Manager" not in alice.get_roles()


def test_readonly_and_privileged_write_fields_are_distinct(alice, make_user, administrator):
    manager = make_user("manager@example.com", roles=["Sales Manager"])

    assert readonly_fields(SecuredDocument) == {"audit_value"}
    assert unwritable_by(SecuredDocument, alice) == {"manager_value"}
    assert unwritable_by(SecuredDocument, None) == {"manager_value"}
    assert unwritable_by(SecuredDocument, manager) == set()
    assert unwritable_by(SecuredDocument, administrator) == set()
