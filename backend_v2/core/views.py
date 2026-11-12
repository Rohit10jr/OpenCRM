"""Base API view for endpoints that are not document resources."""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import build_error_body
from core.inputs import build_payload
from core.renderers import Envelope, WithResponseKeys


@csrf_exempt
def frappe_not_found(request, *args, **kwargs):
    """Return the settled Frappe body for a URL with no route."""

    return JsonResponse(
        build_error_body(
            "DoesNotExistError",
            ["Not found."],
            "Not Found",
        ),
        status=404,
    )


class FrappeAPIView(APIView):
    """Use Frappe inputs and the method-path ``message`` success envelope."""

    envelope_key = "message"

    def get_inputs(self, request) -> dict:
        return build_payload(request)

    def envelope(self, payload, status_code=status.HTTP_200_OK) -> Response:
        extra = None
        if isinstance(payload, WithResponseKeys):
            extra = payload.keys
            payload = payload.message
        return Response(
            Envelope(payload, self.envelope_key, extra=extra),
            status=status_code,
        )

    def finalize_response(self, request, response, *args, **kwargs):
        if (
            isinstance(response, Response)
            and response.status_code < 400
            and not isinstance(response.data, Envelope)
        ):
            payload = response.data
            extra = None
            if isinstance(payload, WithResponseKeys):
                extra = payload.keys
                payload = payload.message
            response.data = Envelope(payload, self.envelope_key, extra=extra)
        return super().finalize_response(request, response, *args, **kwargs)
