"""``/files/<name>`` and ``/private/files/<name>``: the bytes behind a ``File`` row.

Upstream's web server hands ``/files/`` out straight from disk and routes
``/private/files/`` through ``frappe.utils.response.download_private_file`` (296-308),
which refuses guests and anyone the File rule refuses. Both live here, outside ``/api/``,
because the URL is what ``File.file_url`` holds and what the frontend's ``<img>`` and
``<a>`` tags fetch.

**Who may fetch a private file** is the File rule, ``file_has_permission``
(``crm_app/permissions/attachments.py``), asked through ``find_file_by_url``: the owner,
anyone who may read a document the file hangs off, Administrator. ``KNOWN_ISSUES.md`` 3
required exactly this - a permission check at the serving layer, not only on the row -
before any route served bytes.

**How the caller is identified.** The bearer header, as on every API call, or the
``access_token`` cookie that ``frontend/src/auth/tokens.js`` keeps beside the tokens. A
browser cannot put a header on an image a note embeds, so the frontend carries the same
access token in a cookie scoped to ``/private/files`` alone, the way the WebSocket client
carries it in the query string (``frontend/JWT_PATCH.md``). The cookie is read here and
nowhere else, and only on a GET, so it can neither reach an API endpoint nor change
anything; ``SameSite=Lax`` keeps it off requests a cross-site page makes for the URL.
"""

from __future__ import annotations

from pathlib import Path

from django.http import FileResponse, Http404, HttpResponseForbidden
from django.views.decorators.http import require_GET

from frappe_core.session import session_user
from frappe_platform import files as file_store

#: The cookie the frontend keeps a copy of the access token in, for this route only.
ACCESS_COOKIE = "access_token"

#: ``response.py:301`` and ``305``, verbatim.
FORBIDDEN = "You don't have permission to access this file"


def authenticated_user(request) -> str | None:
    """The user the request's bearer header names, else the one its cookie names."""
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken, TokenError

    auth = JWTAuthentication()
    try:
        pair = auth.authenticate(request)
    except (InvalidToken, TokenError, AuthenticationFailed):
        pair = None
    if pair is not None:
        return pair[0].pk
    raw = request.COOKIES.get(ACCESS_COOKIE)
    if not raw:
        return None
    try:
        return auth.get_user(auth.get_validated_token(raw)).pk
    except (InvalidToken, TokenError, AuthenticationFailed):
        return None


def _serve(path: Path, file_name: str, private: bool) -> FileResponse:
    """``response.py:329-360``: inline, except the types a browser would execute."""
    as_attachment = path.suffix.lower() in file_store.FORCE_DOWNLOAD_EXTENSIONS
    response = FileResponse(open(path, "rb"), as_attachment=as_attachment, filename=file_name)
    if private:
        response["Cache-Control"] = "private"
    return response


@require_GET
def public_file(request, path: str):
    """``/files/<path>``: public, as upstream's web server serves it, no session needed."""
    disk = file_store.path_for_url(file_store.PUBLIC_URL + path)
    if disk is None or not disk.is_file():
        raise Http404
    return _serve(disk, disk.name, private=False)


@require_GET
def private_file(request, path: str):
    """``response.py:download_private_file``: a signed-in caller the File rule admits."""
    user = authenticated_user(request)
    if user is None:
        return HttpResponseForbidden(FORBIDDEN)
    url = file_store.PRIVATE_URL + path
    disk = file_store.path_for_url(url)
    if disk is None:
        return HttpResponseForbidden(FORBIDDEN)
    with session_user(user):
        row = file_store.find_file_by_url(url, name=request.GET.get("fid"))
    if row is None:
        return HttpResponseForbidden(FORBIDDEN)
    if not disk.is_file():
        raise Http404
    return _serve(disk, row.file_name or disk.name, private=True)
