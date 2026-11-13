"""Default authentication gate for routes replacing Frappe method paths."""

from rest_framework.permissions import BasePermission

from core.exceptions import AuthenticationError


class IsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            raise AuthenticationError("Not permitted")
        return True
