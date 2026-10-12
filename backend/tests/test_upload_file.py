"""``upload_file`` and the ``/files/`` routes: docs/FINDINGS.md 49.

Every attachment in the product - a picture in a note, a file on a lead, an email's
attachment - comes in through ``POST /api/method/upload_file`` and goes out through
``/files/<name>`` or ``/private/files/<name>``. The port had neither. Shapes follow
``frappe/handler.py:upload_file`` and ``frappe/core/doctype/file/file.py``.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from frappe_core.session import session_user
from frappe_platform.models import Comment, File

pytestmark = pytest.mark.django_db

UPLOAD = "/api/method/upload_file"
PNG = b"\x89PNG\r\n\x1a\n" + b"not really a picture, but bytes are bytes" * 3


@pytest.fixture
def media(settings, tmp_path):
    """A throwaway ``MEDIA_ROOT``; nothing lands in the repository's ``media/``."""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def upload(client, name="pic.png", content=PNG, content_type="image/png", **fields):
    data = {"file": SimpleUploadedFile(name, content, content_type=content_type)}
    data.update(fields)
    return client.post(UPLOAD, data, format="multipart")


def body(response) -> bytes:
    return b"".join(response.streaming_content)


def bearer(user) -> str:
    return str(RefreshToken.for_user(user).access_token)


# --------------------------------------------------------------------------- the upload


def test_a_private_upload_is_stored_under_media_and_answered_with_the_row(auth_api, alice, media):
    """The editor's image button: ``is_private=1``, ``folder=Home``, nothing attached."""
    response = upload(auth_api, is_private="1", folder="Home")
    assert response.status_code == 200, response.content[:300]
    message = response.json()["message"]

    assert message["file_url"] == "/private/files/pic.png"
    assert message["file_name"] == "pic.png"
    assert message["is_private"] is True
    assert (media / "private" / "files" / "pic.png").read_bytes() == PNG

    row = File.objects.get(pk=message["name"])
    assert row.owner_id == alice.name
    assert row.file_size == len(PNG)
    assert row.content_hash and row.folder == "Home"
    assert row.attached_to_doctype == "" and row.attached_to_name == ""


def test_a_public_upload_goes_under_files_and_is_served_without_a_session(auth_api, api, media):
    message = upload(auth_api, is_private="0").json()["message"]
    assert message["file_url"] == "/files/pic.png"
    assert (media / "files" / "pic.png").exists()

    served = api.get("/files/pic.png")
    assert served.status_code == 200
    assert served["Content-Type"] == "image/png"
    assert body(served) == PNG


def test_anonymous_callers_cannot_upload(api, media):
    assert upload(api).status_code == 401


def test_the_form_fields_arrive_one_value_each(auth_api, media):
    """A multipart body is a QueryDict; ``is_private`` must read as ``"0"``, not ``["0"]``."""
    message = upload(auth_api, is_private="0", folder="Home").json()["message"]
    assert message["is_private"] is False
    assert message["folder"] == "Home"


# --------------------------------------------------------------------------- serving


def test_a_private_file_needs_a_session_and_the_file_rule(auth_api, api, api_as, alice, bob, administrator, media):
    """``download_private_file``: guests are refused, then ``File.has_permission`` decides.
    A private file attached to nothing is its owner's alone (FINDINGS.md 22)."""
    upload(auth_api)
    url = "/private/files/pic.png"

    refused = api.get(url)
    assert refused.status_code == 403
    assert b"You don't have permission to access this file" in refused.content

    assert body(auth_api.get(url)) == PNG
    assert api_as(bob).get(url).status_code == 403
    assert api_as(administrator).get(url).status_code == 200


def test_the_cookie_carries_the_token_where_a_header_cannot(auth_api, alice, media):
    """A note's ``<img src="/private/files/...">`` has no header; the frontend's
    ``access_token`` cookie stands in for it, on this route only."""
    upload(auth_api)
    browser = APIClient()
    browser.cookies["access_token"] = bearer(alice)
    assert browser.get("/private/files/pic.png").status_code == 200

    browser.cookies["access_token"] = "not-a-token"
    assert browser.get("/private/files/pic.png").status_code == 403

    # The cookie is read by the file route alone; the API still wants its header.
    browser.cookies["access_token"] = bearer(alice)
    assert browser.get("/api/method/frappe.auth.get_logged_user").status_code == 401


def test_a_file_the_rule_admits_through_its_document_is_served(auth_api, api_as, alice, bob, media):
    """Attached to bob's own User row, which everyone may read: bob gets the bytes."""
    upload(auth_api, doctype="User", docname=alice.name)
    assert api_as(bob).get("/private/files/pic.png").status_code == 200


def test_a_missing_private_file_is_refused_not_revealed(auth_api, media):
    """``find_file_by_url`` returns nothing -> Forbidden, as upstream answers."""
    assert auth_api.get("/private/files/nothing.png").status_code == 403


def test_a_url_that_escapes_the_folder_is_not_served(auth_api, api, media):
    (media / "secret.txt").write_bytes(b"outside")
    assert api.get("/files/../secret.txt").status_code in (403, 404)
    assert auth_api.get("/private/files/..%2F..%2Fsecret.txt").status_code in (403, 404)


def test_markup_types_are_sent_as_downloads(auth_api, api, media):
    """``FORCE_DOWNLOAD_EXTENSIONS``: an SVG is a script host, so never inline."""
    upload(auth_api, name="logo.svg", content=b"<svg/>", content_type="image/svg+xml", is_private="0")
    served = api.get("/files/logo.svg")
    assert served.status_code == 200
    assert served["Content-Disposition"].startswith("attachment")


# --------------------------------------------------------------------------- attaching


def test_attaching_to_a_record_checks_write_on_it(auth_api, alice, bob, media):
    """``check_write_permission``: a User row is written only by its owner."""
    refused = upload(auth_api, doctype="User", docname=bob.name)
    assert refused.status_code == 403

    allowed = upload(auth_api, doctype="User", docname=alice.name, fieldname="user_image")
    assert allowed.status_code == 200, allowed.content[:300]
    row = File.objects.get(pk=allowed.json()["message"]["name"])
    assert (row.attached_to_doctype, row.attached_to_name, row.attached_to_field) == (
        "User",
        alice.name,
        "user_image",
    )
    # `handler.py:158`: upload_file writes `folder or "Home"` before the File's own
    # `set_folder_name` could pick the attachments folder, so an upload lands in Home
    # even when attached.
    assert row.folder == "Home"


def test_an_attachment_is_noted_on_the_documents_timeline(auth_api, alice, media):
    """``create_attachment_record``: a Comment of type Attachment linking the file."""
    message = upload(auth_api, doctype="User", docname=alice.name).json()["message"]
    comment = Comment.objects.get(
        comment_type="Attachment", reference_doctype="User", reference_name=alice.name
    )
    assert message["file_url"] in comment.content
    assert "fa-lock" in comment.content  # private, so the lock icon


def test_a_record_that_does_not_exist_yet_falls_back_to_the_doctype_check(auth_api, media):
    """The lead dialog attaches to ``new-crm-lead-1`` before the lead is saved."""
    response = upload(auth_api, doctype="User", docname="new-user-1")
    # Creating a User is admin-only, so the doctype-level write check refuses alice.
    assert response.status_code == 403


def test_attaching_to_an_unknown_doctype_is_a_404(auth_api, media):
    assert upload(auth_api, doctype="Nonsense", docname="x").status_code == 404


# --------------------------------------------------------------------------- naming


def test_the_same_bytes_twice_are_stored_once(auth_api, media):
    first = upload(auth_api, name="one.png").json()["message"]
    second = upload(auth_api, name="two.png").json()["message"]
    assert second["file_url"] == first["file_url"]
    assert sorted(p.name for p in (media / "private" / "files").iterdir()) == ["one.png"]


def test_a_name_clash_with_different_bytes_gets_a_suffix(auth_api, media):
    first = upload(auth_api, content=PNG).json()["message"]
    second = upload(auth_api, content=PNG + b"!").json()["message"]
    assert first["file_url"] == "/private/files/pic.png"
    assert second["file_url"].startswith("/private/files/pic") and second["file_url"] != first["file_url"]
    assert len(list((media / "private" / "files").iterdir())) == 2


def test_a_size_over_the_limit_is_refused(auth_api, settings, media):
    settings.MAX_FILE_SIZE = 1048576
    response = upload(auth_api, content=b"x" * 1048577)
    assert response.status_code == 417
    assert "File size exceeded the maximum allowed size of 1.0 MB" in response.json()["exception"]


def test_a_website_user_may_only_upload_documents_and_pictures(make_user, api_as, media):
    """``ALLOWED_MIMETYPES``, for a user without desk access."""
    portal = make_user("portal@example.com", first_name="Portal", user_type="Website User")
    refused = upload(api_as(portal), name="tool.exe", content=b"MZ", content_type="application/octet-stream")
    assert refused.status_code == 417
    assert (
        "You can only upload JPG, PNG, GIF, PDF, TXT, CSV or Microsoft documents."
        in refused.json()["exception"]
    )
    assert upload(api_as(portal), name="notes.txt", content=b"hi", content_type="text/plain").status_code == 200


# --------------------------------------------------------------------------- other ways in


def test_a_chunked_upload_is_assembled(auth_api, media):
    parts = [b"first half,", b" second half"]
    total = sum(len(p) for p in parts)
    common = {"total_chunk_count": "2", "total_file_size": str(total), "name": "big.txt", "content_type": "text/plain"}

    first = upload(auth_api, content=parts[0], chunk_index="0", chunk_byte_offset="0", **common)
    assert first.status_code == 200 and first.json()["message"] is None
    assert not (media / "private" / "files" / "big.txt").exists()

    second = upload(
        auth_api, content=parts[1], chunk_index="1", chunk_byte_offset=str(len(parts[0])), **common
    )
    assert second.json()["message"]["file_url"] == "/private/files/big.txt"
    assert (media / "private" / "files" / "big.txt").read_bytes() == b"".join(parts)
    assert not (media / "private" / "files" / ".temp-big.txt").exists()


def test_attach_by_url_records_an_existing_file_without_moving_bytes(auth_api, media):
    first = upload(auth_api).json()["message"]
    again = auth_api.post(UPLOAD, {"file_url": first["file_url"], "is_private": "1"}, format="multipart")
    assert again.status_code == 200, again.content[:300]
    row = File.objects.get(pk=again.json()["message"]["name"])
    assert row.file_url == first["file_url"]
    assert row.content_hash == File.objects.get(pk=first["name"]).content_hash
    assert len(list((media / "private" / "files").iterdir())) == 1


def test_a_remote_url_is_recorded_as_is(auth_api, media):
    response = auth_api.post(UPLOAD, {"file_url": "https://example.com/brochure.pdf"}, format="multipart")
    assert response.status_code == 200, response.content[:300]
    row = File.objects.get(pk=response.json()["message"]["name"])
    assert row.file_url == "https://example.com/brochure.pdf"
    assert row.file_name == "brochure.pdf"
    assert row.content_hash == "" and not (media / "private").exists()


def test_a_library_file_lends_its_bytes_to_a_new_row(auth_api, alice, media):
    first = upload(auth_api).json()["message"]
    copy = auth_api.post(
        UPLOAD, {"library_file_name": first["name"], "doctype": "User", "docname": alice.name}, format="multipart"
    )
    assert copy.status_code == 200, copy.content[:300]
    row = File.objects.get(pk=copy.json()["message"]["name"])
    assert row.file_url == first["file_url"] and row.attached_to_name == alice.name


def test_a_file_url_that_escapes_the_folder_is_refused_on_insert(auth_api, media):
    """``validate_file_path``: a row must not be able to name a path outside its folder."""
    response = auth_api.post(
        "/api/method/frappe.client.insert",
        {"doc": {"doctype": "File", "file_name": "x", "file_url": "/files/../settings.py"}},
        format="json",
    )
    assert response.status_code == 417
    assert "The File URL you've entered is incorrect" in response.json()["exception"]


# --------------------------------------------------------------------------- the row's life


def test_deleting_the_last_row_removes_the_bytes_but_a_shared_row_keeps_them(auth_api, media):
    first = upload(auth_api).json()["message"]
    second = auth_api.post(UPLOAD, {"library_file_name": first["name"]}, format="multipart").json()["message"]
    on_disk = media / "private" / "files" / "pic.png"

    delete = "/api/method/frappe.client.delete"
    assert auth_api.post(delete, {"doctype": "File", "name": first["name"]}, format="json").status_code == 200
    assert on_disk.exists()
    assert auth_api.post(delete, {"doctype": "File", "name": second["name"]}, format="json").status_code == 200
    assert not on_disk.exists()


def test_a_cascade_from_the_document_clears_the_bytes_too(auth_api, alice, media):
    """``frappe_core.children`` deletes a document's Files through the queryset; the
    ``pre_delete`` receiver still runs, so the bytes do not outlive the row."""
    from crm_app.models import FCRMNote

    with session_user(alice.name):
        note = FCRMNote.objects.create(title="Attach me")
    assert upload(auth_api, doctype="FCRM Note", docname=note.name).status_code == 200
    on_disk = media / "private" / "files" / "pic.png"
    assert on_disk.exists()

    with session_user(alice.name):
        note.delete()
    assert not File.objects.filter(attached_to_name=note.name).exists()
    assert not on_disk.exists()


def test_flipping_is_private_moves_the_file_and_rewrites_the_url(auth_api, api, media):
    """The attachments panel's "Make public": ``frappe.client.set_value`` on ``is_private``."""
    message = upload(auth_api).json()["message"]
    response = auth_api.post(
        "/api/method/frappe.client.set_value",
        {"doctype": "File", "name": message["name"], "fieldname": {"is_private": 0}},
        format="json",
    )
    assert response.status_code == 200, response.content[:300]
    row = File.objects.get(pk=message["name"])
    assert row.file_url == "/files/pic.png"
    assert not (media / "private" / "files" / "pic.png").exists()
    assert (media / "files" / "pic.png").read_bytes() == PNG
    assert api.get("/files/pic.png").status_code == 200


def test_a_removed_attachment_is_noted_on_the_timeline(auth_api, alice, media):
    message = upload(auth_api, doctype="User", docname=alice.name).json()["message"]
    auth_api.post("/api/method/frappe.client.delete", {"doctype": "File", "name": message["name"]}, format="json")
    removed = Comment.objects.filter(comment_type="Attachment Removed", reference_name=alice.name)
    assert removed.count() == 1 and removed.get().content == "pic.png"


def test_rows_without_bytes_are_still_accepted(administrator, media):
    """The copies ``add_comment`` and ``email.add_attachments`` make, and every
    attachment fixture: a URL and no file on disk is metadata, not an error."""
    with session_user(administrator.name):
        row = File.objects.create(
            file_name="signed.pdf", file_url="/private/files/signed.pdf", is_private=True
        )
    assert row.content_hash == "" and row.file_size == 0


def test_optimize_shrinks_a_large_picture(auth_api, media):
    pytest.importorskip("PIL")
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (2000, 1500), "red").save(buffer, format="PNG")
    big = buffer.getvalue()

    message = upload(auth_api, content=big, optimize="1").json()["message"]
    stored = (media / "private" / "files" / "pic.png").read_bytes()
    width, height = Image.open(io.BytesIO(stored)).size
    assert width <= 1024 and height <= 768
    assert message["file_url"] == "/private/files/pic.png"
