"""User's list definition (specs/CONFIGURATION.md 4.8, section 8; temp A-40).

The old `User.default_list_data` (`backend/frappe_platform/models.py:309-318`) moves to
`accounts/list_views.py`. A definition only: User serves no list-view route.
"""

from accounts.list_views import UserListView
from accounts.serializers import UserSerializer
from configuration.list_views import list_definition_for


def test_the_user_definition_is_the_old_default_list_data():
    assert UserListView.default_columns() == [
        {"label": "Name", "type": "Data", "key": "full_name", "width": "17rem"},
        {"label": "Email", "type": "Data", "key": "name", "width": "12rem"},
        {"label": "Enabled", "type": "Check", "key": "enabled", "width": "6rem"},
    ]
    assert UserListView.default_rows() == ["name", "full_name", "first_name", "user_image", "enabled"]


def test_the_saved_view_calls_get_users_definition():
    assert list_definition_for("User") is UserListView


def test_the_definition_names_readable_fields_only():
    readable = set(UserSerializer.Meta.fields)
    keys = {column["key"] for column in UserListView.default_columns()}
    assert keys | set(UserListView.default_rows()) <= readable
