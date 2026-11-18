"""The list view a resource opts in to (REBUILD_PLAN S24; specs/CONFIGURATION.md 4.8).

`GET` and `POST /api/v1/<resource>/list-view/` is the old `crm.api.doc.get_data` on
that resource alone: `doctype` leaves the input, and a resource that does not opt in
has no list view (PE-22). `POST` because the inputs (columns, kanban settings) are too
big for a URL (S25 (4)).
"""

from rest_framework.decorators import action
from rest_framework.response import Response

from configuration import list_engine
from core.inputs import build_payload
from core.renderers import Envelope


class ListViewMixin:
    @action(detail=False, methods=("get", "post"), url_path="list-view")
    def list_view(self, request):
        answer = list_engine.get_data(self, build_payload(request), user=request.user)
        return Response(Envelope(answer, "message"))
