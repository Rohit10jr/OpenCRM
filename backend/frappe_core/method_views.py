"""``/api/method/<dotted.path>`` dispatch.

PORT_PLAN.md section 3. Payload comes from the query string on ``GET`` and the body on
``POST``; both are merged, matching Frappe, which does not care which one a parameter
arrives in.

Responses are wrapped in ``{"message": ...}``.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny

from frappe_core.exceptions import AuthenticationError, DoesNotExistError, PermissionError as FrappePermissionError
from frappe_core.query import parse_json_param
from frappe_core.views import FrappeAPIView
from frappe_core.whitelist import MethodNotFound, bind_arguments, get_method


class MethodView(FrappeAPIView):
    """Call a whitelisted method by its dotted path."""

    envelope_key = "message"
    # Guest access is decided per method, below, not by a blanket class permission.
    permission_classes = [AllowAny]

    def get(self, request, method_path: str):
        return self._dispatch(request, method_path, "GET")

    def post(self, request, method_path: str):
        return self._dispatch(request, method_path, "POST")

    def put(self, request, method_path: str):
        return self._dispatch(request, method_path, "PUT")

    def _dispatch(self, request, method_path: str, http_method: str):
        try:
            func = get_method(method_path)
        except MethodNotFound:
            raise DoesNotExistError(f"Method {method_path} not found") from None

        allowed = getattr(func, "__frappe_methods__", ("GET", "POST"))
        if http_method not in allowed:
            raise FrappePermissionError(
                f"Method {method_path} does not accept {http_method}"
            )

        if not getattr(func, "__frappe_allow_guest__", False):
            user = getattr(request, "user", None)
            if user is None or not getattr(user, "is_authenticated", False):
                raise AuthenticationError("Not permitted")

        payload = self._build_payload(request)
        result = func(**bind_arguments(func, payload))
        return self.envelope(result, status.HTTP_200_OK)

    @staticmethod
    def _build_payload(request) -> dict:
        payload: dict = {}
        for key, value in request.query_params.items():
            payload[key] = parse_json_param(value, value)
        data = getattr(request, "data", None)
        if isinstance(data, dict):
            payload.update(data)
        # `cmd` is Frappe's legacy method selector; it is never a real parameter.
        payload.pop("cmd", None)
        return payload
