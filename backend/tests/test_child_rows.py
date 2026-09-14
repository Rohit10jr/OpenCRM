"""Child rows written through the document route: FINDINGS.md 7, 8 and 9.

Upstream (frappe/model/document.py, base_document.py) validates a document together
with its child rows: a Link in a row is given by name and checked, a mandatory column
with no value is a MandatoryError, and the controller's validate() sees the rows. The
port wrote the rows after the parent, straight into ``create()``, so a Link by name was
a 500, a missing column a database error, and the derivations ran on the old rows.
"""

from urllib.parse import quote

import pytest

from crm_app.models import CRMContacts, CRMDeal, CRMDealStatus, CRMProduct, CRMProducts
from frappe_core.session import session_user
from frappe_platform.models import Contact

pytestmark = pytest.mark.django_db

DEALS = "/api/resource/" + quote("CRM Deal")


@pytest.fixture
def deal(alice, administrator):
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
    with session_user(alice.name):
        return CRMDeal.objects.create(deal_owner=alice, status=status)


@pytest.fixture
def product(administrator):
    with session_user(administrator.name):
        return CRMProduct.objects.create(product_code="ZZ-P1", product_name="ZZ P1")


@pytest.fixture
def contact(administrator):
    with session_user(administrator.name):
        return Contact.objects.create(
            first_name="Ada", last_name="Lovelace", email_id="ada@test.example", mobile_no="+1 111"
        )


def _put(client, deal, body):
    return client.put(f"{DEALS}/{quote(deal.name)}", body, format="json")


# --- 9: a Link in a row is given by name --------------------------------------------


def test_a_product_line_may_name_its_product_code(auth_api, deal, product):
    """``{"product_code": "ZZ-P1"}`` is what the product grid sends; it used to reach
    ``create()`` as a string and Django refused it with a 500."""
    response = _put(
        auth_api, deal, {"products": [{"product_code": "ZZ-P1", "product_name": "ZZ P1", "qty": 1, "rate": 75}]}
    )
    assert response.status_code == 200, response.content[:300]
    row = CRMProducts.objects.get(parenttype="CRM Deal", parent=deal.name)
    assert row.product_code_id == "ZZ-P1"
    assert response.json()["data"]["products"][0]["product_code"] == "ZZ-P1"


def test_a_contact_row_may_name_its_contact(auth_api, deal, contact):
    response = _put(auth_api, deal, {"contacts": [{"contact": "Ada Lovelace"}]})
    assert response.status_code == 200, response.content[:300]
    assert CRMContacts.objects.get(parent_deal=deal).contact_id == "Ada Lovelace"


def test_a_link_to_a_missing_document_is_a_link_validation_error(auth_api, deal, contact):
    """``document.py:_validate_links`` -> ``Could not find Row #1: Contact: ZZ Nobody``,
    a 417 LinkValidationError; and the rows that were there stay, because nothing is
    deleted before the rows are validated."""
    assert _put(auth_api, deal, {"contacts": [{"contact": "Ada Lovelace"}]}).status_code == 200

    response = _put(auth_api, deal, {"contacts": [{"contact": "ZZ Nobody"}]})

    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "LinkValidationError"
    assert body["message"] == "Could not find Row #1: Contact: ZZ Nobody"
    assert CRMContacts.objects.filter(parent_deal=deal).count() == 1


# --- 7: a mandatory column with no value ---------------------------------------------


def test_a_row_missing_a_mandatory_value_is_a_mandatory_error(auth_api, deal):
    """base_document.py:747-756, the child-row wording, which the frontend splits on
    ``': '`` to name the field. It used to be the NOT NULL constraint, a 409."""
    response = _put(auth_api, deal, {"products": [{"product_name": "ZZ No Rate", "qty": 1}]})

    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "MandatoryError"
    assert body["messages"] == [
        "Error: <strong>CRM Products</strong> Row #1: Value missing for: Rate"
    ]


def test_every_missing_value_is_reported(auth_api, deal):
    response = _put(auth_api, deal, {"products": [{"qty": 1}, {"product_name": "ZZ", "rate": 1}, {"rate": 2}]})

    assert response.status_code == 417
    assert response.json()["messages"] == [
        "Error: <strong>CRM Products</strong> Row #1: Value missing for: Product Name",
        "Error: <strong>CRM Products</strong> Row #1: Value missing for: Rate",
        "Error: <strong>CRM Products</strong> Row #3: Value missing for: Product Name",
    ]


# --- 8: the parent's validate() sees the rows in the same request ----------------


def test_a_lone_contact_row_is_primary_in_the_same_response(auth_api, deal, contact):
    """crm_deal.py:120-149 on the same save: the only contact becomes primary and its
    email and mobile are copied onto the deal. The port answered with the values from
    before the rows were written, and caught up one save later."""
    response = _put(auth_api, deal, {"contacts": [{"contact": "Ada Lovelace"}]})

    data = response.json()["data"]
    assert data["contacts"][0]["is_primary"] is True
    assert data["email"] == "ada@test.example"
    assert data["mobile_no"] == "+1 111"


def test_rows_sent_on_create_are_seen_by_the_first_save(auth_api, alice, contact):
    with session_user(alice.name):
        CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
    response = auth_api.post(
        DEALS,
        {"deal_owner": alice.name, "contacts": [{"contact": "Ada Lovelace"}]},
        format="json",
    )
    assert response.status_code == 201, response.content[:300]
    data = response.json()["data"]
    assert data["contacts"][0]["is_primary"] is True
    assert data["email"] == "ada@test.example"


def test_totals_kept_by_the_rows_survive_the_parents_save(auth_api, deal):
    """A product row's own save keeps the parent's ``total`` and ``net_total`` with a
    bare ``update()``; the parent must be re-read before its own save, or the stale
    in-memory values are written back over them."""
    response = _put(
        auth_api,
        deal,
        {"products": [{"product_name": "ZZ Thing", "qty": 2, "rate": 100}]},
    )
    data = response.json()["data"]
    assert data["total"] is not None and float(data["total"]) == 200
    assert float(data["net_total"]) == 200
    deal.refresh_from_db()
    assert float(deal.total) == 200


def test_a_refused_parent_takes_its_new_rows_back(auth_api, deal, contact):
    """The rows are written before the parent's save; a refusal there must not leave
    them behind."""
    assert _put(auth_api, deal, {"contacts": [{"contact": "Ada Lovelace"}]}).status_code == 200

    response = _put(
        auth_api, deal, {"contacts": [], "status": "No Such Status"}
    )

    assert response.status_code == 417
    assert CRMContacts.objects.filter(parent_deal=deal).count() == 1
