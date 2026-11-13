from django.urls import re_path

from accounts.views import LoggedUserView, LoginView, LogoutView, RefreshTokenView


urlpatterns = [
    re_path(r"^auth/login/?$", LoginView.as_view(), name="auth-login"),
    re_path(
        r"^auth/token/refresh/?$",
        RefreshTokenView.as_view(),
        name="auth-token-refresh",
    ),
    re_path(r"^auth/logout/?$", LogoutView.as_view(), name="auth-logout"),
    re_path(r"^auth/me/?$", LoggedUserView.as_view(), name="auth-me"),
]
