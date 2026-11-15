"""Prove every test resource write passes the authenticated caller to save()."""

import pytest

from tests_support.models import SingletonDocument


pytestmark = pytest.mark.django_db

DOCUMENT_RESOURCES = (
    ("/api/v1/test-widgets/", {"widget_name": "Created"}, {"widget_name": "Patched"}),
    ("/api/v1/test-fields/", {"title": "Guard Field"}, {"title": "Guard Field"}),
    ("/api/v1/test-secured/", {}, {"audit_value": "ignored"}),
    ("/api/v1/test-prompts/", {"name": "Guard Prompt"}, {"label": "Patched"}),
    ("/api/v1/test-auto-increments/", {"label": "Created"}, {"label": "Patched"}),
)


@pytest.mark.parametrize(("url", "create_payload", "patch_payload"), DOCUMENT_RESOURCES)
def test_document_resource_create_and_patch_stamp_the_caller(
    auth_api, alice, url, create_payload, patch_payload
):
    created = auth_api.post(url, create_payload, format="json")
    assert created.status_code == 200
    document = created.json()["message"]
    assert document["owner"] == alice.name
    assert document["modified_by"] == alice.name

    patched = auth_api.patch(
        f"{url}{document['name']}/", patch_payload, format="json"
    )
    assert patched.status_code == 200
    assert patched.json()["message"]["owner"] == alice.name
    assert patched.json()["message"]["modified_by"] == alice.name


def test_singleton_resource_patch_stamps_the_caller(auth_api, alice):
    document = SingletonDocument.load(user=alice)
    response = auth_api.patch(
        "/api/v1/test-singleton/", {"value": "Patched"}, format="json"
    )
    assert response.status_code == 200
    document.refresh_from_db()
    assert document.owner_id == alice.name
    assert document.modified_by_id == alice.name
