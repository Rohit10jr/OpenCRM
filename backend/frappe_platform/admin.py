"""Port only: Django admin's one job here is turning an account on or off.

Upstream does this from the Desk's User form, which this port does not have, and the CRM's
own Users screen has no such control. Admin bypasses the permission layer, so the page is
deliberately narrow: `enabled` is the only field that can change, and users cannot be added
or deleted here. Roles stay with `crm_app.api.user.update_user_role`.

Bulk actions are off because they would write with `QuerySet.update`, which skips
`User.save` and so skips revoking the user's tokens.
"""

from django.contrib import admin

from frappe_platform.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("name", "full_name", "enabled")
    list_filter = ("enabled",)
    search_fields = ("name", "email", "full_name")
    fields = ("name", "email", "full_name", "enabled")
    readonly_fields = ("name", "email", "full_name")
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        # Upstream: "User {0} cannot be disabled" for Administrator and Guest
        # (`frappe/core/doctype/user/user.py:268-270`).
        if obj is not None and obj.name in User.BUILTIN_NAMES:
            return (*self.readonly_fields, "enabled")
        return self.readonly_fields
