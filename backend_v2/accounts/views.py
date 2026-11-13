"""The four explicit authentication endpoints."""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts import services
from core.security import resolve_ip
from core.views import FrappeAPIView


class LoginView(FrappeAPIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        inputs = self.get_inputs(request)
        username = inputs.get("usr") or inputs.get("username") or inputs.get("email") or ""
        password = inputs.get("pwd") or inputs.get("password") or ""
        return Response(services.login(username, password, resolve_ip(request)))


class RefreshTokenView(FrappeAPIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        inputs = self.get_inputs(request)
        token = inputs.get("refresh") or inputs.get("refresh_token") or ""
        return Response(services.refresh_token(token))


class LogoutView(FrappeAPIView):
    def post(self, request):
        inputs = self.get_inputs(request)
        token = inputs.get("refresh") or inputs.get("refresh_token") or ""
        return Response(services.logout(token))


class LoggedUserView(FrappeAPIView):
    def get(self, request):
        return Response(request.user.name)
