import json

import pytest

from tests_support.models import SecuredDocument


pytestmark = pytest.mark.django_db
SECRET = "Sw0rdfish!"
SECURED = "/api/v1/test-secured/"


@pytest.fixture
def secured(administrator):
    document = SecuredDocument(secret=SECRET, audit_value="ordinary")
    document.save(user=administrator)
    return document


@pytest.mark.parametrize(
    ("parameter", "value", "status", "message"),
    [
        ("fields", ["name", "secret"], 417, "Field 'secret' is not readable"),
        ("filters", [["secret", "like", "Sw%"]], 400, "Cannot filter on 'secret'"),
        ("or_filters", [["secret", "=", SECRET]], 400, "Cannot filter on 'secret'"),
        ("order_by", "secret desc", 417, "Cannot order by 'secret'"),
        ("group_by", "secret", 417, "Cannot group by 'secret'"),
    ],
)
def test_a_request_naming_a_secret_is_rejected(
    auth_api, secured, parameter, value, status, message
):
    response = auth_api.get(
        SECURED,
        {parameter: json.dumps(value) if not isinstance(value, str) else value},
    )
    assert response.status_code == status
    assert response.json()["message"] == message


def test_a_secret_cannot_be_recovered_by_probing(auth_api, secured):
    for prefix in ("S%", "s%", "Sw%", "%fish%", SECRET):
        response = auth_api.get(
            SECURED,
            {"filters": json.dumps([["secret", "like", prefix]])},
        )
        assert response.status_code == 400, f"{prefix!r} was answered, not refused"


def test_a_secret_is_not_returned(auth_api, secured):
    response = auth_api.get(f"{SECURED}{secured.pk}/")
    assert response.status_code == 200
    assert "secret" not in response.json()["message"]


def test_an_ordinary_filter_still_works(auth_api, secured):
    response = auth_api.get(
        SECURED,
        {"filters": json.dumps([["audit_value", "=", "ordinary"]])},
    )
    assert response.status_code == 200
    assert [row["name"] for row in response.json()["message"]] == [secured.pk]
