"""Restrict Django admin to enabling and disabling accounts.

Admin bypasses the application permission layer, so every other user field is read-only.
Bulk actions are disabled because they use ``QuerySet.update``, skipping ``User.save``
and therefore token revocation.
"""

from django.contrib import admin

from .models import User


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
        if obj is not None and obj.name in User.BUILTIN_NAMES:
            return (*self.readonly_fields, "enabled")
        return self.readonly_fields
