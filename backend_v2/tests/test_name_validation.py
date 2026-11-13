from urllib.parse import quote

import pytest

from tests_support.models import FieldDocument


pytestmark = pytest.mark.django_db
URL = "/api/v1/test-fields/"


def save_name(name, user):
    document = FieldDocument(title=name)
    document.save(user=user)
    return document


@pytest.mark.parametrize("name", ["R/GA", "Smith/Jones/Co"])
def test_a_name_containing_slashes_is_addressable(auth_api, alice, name):
    save_name(name, alice)
    response = auth_api.get(URL + quote(name) + "/")
    assert response.status_code == 200
    assert response.json()["message"]["name"] == name


def test_a_slashed_name_can_be_updated_and_deleted(auth_api, alice):
    name = "A/B Testing Inc"
    save_name(name, alice)
    url = URL + quote(name) + "/"
    assert auth_api.patch(url, {"title": name}, format="json").status_code == 200
    assert auth_api.delete(url).status_code == 200
    assert not FieldDocument.objects.filter(pk=name).exists()


def test_a_document_action_follows_a_slashed_name(auth_api, alice):
    save_name("R/GA", alice)
    response = auth_api.post(URL + "R/GA/convert/", {}, format="json")
    assert response.status_code == 200
    assert response.json() == {"message": "R/GA"}


def test_list_and_ordinary_name_routes_still_resolve(auth_api, alice):
    save_name("ScaleUp Labs", alice)
    assert auth_api.get(URL).status_code == 200
    assert auth_api.get(URL + "ScaleUp%20Labs/").status_code == 200
