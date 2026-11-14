"""A singleton row is named for its document type and has no URL name."""

import pytest

from tests_support.models import SingletonDocument


pytestmark = pytest.mark.django_db
PATH = "/api/v1/test-singleton/"


def test_a_loaded_singleton_is_named_after_its_doctype(administrator):
    assert SingletonDocument.load(user=administrator).pk == "Foundation Singleton"


def test_a_created_singleton_takes_the_same_name(administrator):
    row = SingletonDocument(value="Acme")
    row.save(user=administrator)
    assert row.pk == "Foundation Singleton"


def test_the_frontend_can_fetch_and_patch_it_by_the_root_route(
    auth_api, administrator
):
    SingletonDocument.load(user=administrator)
    patched = auth_api.patch(PATH, {"value": "Acme"}, format="json")
    assert patched.status_code == 200
    response = auth_api.get(PATH)
    assert response.status_code == 200
    assert response.json()["message"]["name"] == "Foundation Singleton"
    assert response.json()["message"]["value"] == "Acme"


def test_post_put_and_delete_are_not_served(auth_api, administrator):
    SingletonDocument.load(user=administrator)
    assert auth_api.post(PATH, {"value": "Again"}, format="json").status_code == 405
    assert auth_api.put(PATH, {"value": "Again"}, format="json").status_code == 405
    assert auth_api.delete(PATH).status_code == 405
