import json

import pytest

from core.query import by_name
from tests_support.models import AutoIncrementDocumentFixture, FieldDocument


pytestmark = pytest.mark.django_db
AUTO = "/api/v1/test-auto-increments/"


def save(document, user):
    document.save(user=user)
    return document


def test_by_name_finds_nothing_for_a_name_the_key_cannot_hold(alice):
    document = save(AutoIncrementDocumentFixture(label="real"), alice)
    assert by_name(AutoIncrementDocumentFixture, document.pk).first() == document
    assert by_name(AutoIncrementDocumentFixture, "abc").first() is None
    assert by_name(AutoIncrementDocumentFixture, None).first() is None


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_resource_route_answers_404_for_invalid_key(auth_api, method):
    response = getattr(auth_api, method)(AUTO + "not-an-integer/", {}, format="json")
    assert response.status_code == 404
    assert response.json()["exc_type"] == "DoesNotExistError"


def test_duplicate_name_answers_upstream_sentence(auth_api, alice):
    save(FieldDocument(title="Twice"), alice)
    response = auth_api.post("/api/v1/test-fields/", {"title": "Twice"}, format="json")
    assert response.status_code == 409
    assert response.json()["message"] == "Foundation Field <strong>Twice</strong> already exists"
    assert json.loads(json.loads(response.json()["_server_messages"])[0])["title"] == "Duplicate Name"
