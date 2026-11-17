from django.urls import re_path

from accounts.views import (
    ChangePasswordView,
    LoggedUserView,
    LoginView,
    LogoutView,
    OAuthProvidersView,
    RefreshTokenView,
    ResetPasswordView,
    UpdatePasswordView,
    UserViewSet,
    CRMSalesHierarchyViewSet,
)
from core.routers import DocumentRouter


router = DocumentRouter()
router.register("users", UserViewSet, basename="user")
router.register(
    "sales-hierarchies", CRMSalesHierarchyViewSet, basename="sales-hierarchy"
)

urlpatterns = [
    re_path(r"^auth/login/?$", LoginView.as_view(), name="auth-login"),
    re_path(
        r"^auth/token/refresh/?$",
        RefreshTokenView.as_view(),
        name="auth-token-refresh",
    ),
    re_path(r"^auth/logout/?$", LogoutView.as_view(), name="auth-logout"),
    re_path(r"^auth/me/?$", LoggedUserView.as_view(), name="auth-me"),
    re_path(
        r"^auth/change-password/?$",
        ChangePasswordView.as_view(),
        name="auth-change-password",
    ),
    re_path(
        r"^auth/oauth-providers/?$",
        OAuthProvidersView.as_view(),
        name="auth-oauth-providers",
    ),
    re_path(
        r"^auth/reset-password/?$",
        ResetPasswordView.as_view(),
        name="auth-reset-password",
    ),
    re_path(
        r"^auth/update-password/?$",
        UpdatePasswordView.as_view(),
        name="auth-update-password",
    ),
    *router.urls,
]
