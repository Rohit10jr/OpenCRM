"""User's list definition (specs/CONFIGURATION.md 4.8, section 8; temp A-40).

The old `User.default_list_data` (`backend/frappe_platform/models.py:309-318`), verbatim.
A definition only: User has no list-view route, as no screen lists users (flagged to
the owner).
"""

from configuration.list_views import ListView


class UserListView(ListView):
    columns = (
        {"label": "Name", "type": "Data", "key": "full_name", "width": "17rem"},
        {"label": "Email", "type": "Data", "key": "name", "width": "12rem"},
        {"label": "Enabled", "type": "Check", "key": "enabled", "width": "6rem"},
    )
    rows = ("name", "full_name", "first_name", "user_image", "enabled")
