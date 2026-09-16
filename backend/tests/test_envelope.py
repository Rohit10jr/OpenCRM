"""The response and error envelopes - PHASE_0_FOUNDATION.md section 6c.

Section 6c left the error shape open ("check ``frontend/src/`` error handling and match
it exactly"). It is pinned here against the real consumers in the shipped frontend, each
cited on the assertion it justifies.
"""

import json
from urllib.parse import quote

import pytest

from frappe_core.exceptions import (
    DoesNotExistError,
    MandatoryError,
    PermissionError as FrappePermissionError,
    ValidationError,
    build_error_body,
    throw,
)

pytestmark = pytest.mark.django_db

WIDGETS = "/api/resource/" + quote("Phase Zero Widget")


# --- success envelopes --------------------------------------------------------


def test_resource_list_is_wrapped_in_data(auth_api):
    assert set(auth_api.get(WIDGETS).json()) == {"data"}


def test_method_call_is_wrapped_in_message(auth_api):
    body = auth_api.get("/api/method/frappe.auth.get_logged_user").json()
    assert set(body) == {"message"}


# --- error envelope shape -----------------------------------------------------


def test_error_body_carries_exc_type(auth_api):
    """``src/data/document.js:40`` branches on ``err.exc_type``."""
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    assert body["exc_type"] == "DoesNotExistError"


def test_error_body_carries_a_messages_list_of_plain_strings(auth_api):
    """``document.js:41`` reads ``err.messages[0]``; ``:62`` calls ``.map()`` on it."""
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    assert isinstance(body["messages"], list)
    assert all(isinstance(m, str) for m in body["messages"])
    assert body["messages"][0]


def test_error_body_carries_a_scalar_message(auth_api):
    """``SettingsPage.vue:92`` prints ``err.message + ': ' + err.messages[0]``."""
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    assert isinstance(body["message"], str)


def test_server_messages_is_double_encoded(auth_api):
    """``FilesUploader.vue:216`` does ``JSON.parse(JSON.parse(_server_messages)[0]).message``.

    frappe-ui derives ``error.messages`` from this field, so its exact double-encoding
    is load-bearing rather than decorative.
    """
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    outer = json.loads(body["_server_messages"])
    assert isinstance(outer, list)
    inner = json.loads(outer[0])
    assert set(inner) >= {"message", "title"}
    assert inner["message"] == body["messages"][0]


def test_error_body_is_not_wrapped_in_an_envelope(auth_api):
    """The frontend reads exc_type off the top level, not out of ``data``/``message``."""
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    assert "data" not in body
    assert "exception" in body


def test_exception_string_matches_frappes_format(auth_api):
    body = auth_api.get(f"{WIDGETS}/does-not-exist").json()
    assert body["exception"].startswith("frappe.exceptions.DoesNotExistError: ")


# --- status codes -------------------------------------------------------------


@pytest.mark.parametrize(
    "exc,expected_status,expected_type",
    [
        (ValidationError, 417, "ValidationError"),
        (FrappePermissionError, 403, "PermissionError"),
        (DoesNotExistError, 404, "DoesNotExistError"),
        (MandatoryError, 417, "MandatoryError"),
    ],
)
def test_status_codes_match_frappe(exc, expected_status, expected_type):
    assert exc.http_status_code == expected_status
    assert exc("x").exc_type == expected_type


def test_unauthenticated_is_401_with_authentication_error(api):
    """``src/stores/users.js:34`` branches on ``'AuthenticationError'``."""
    response = api.get(WIDGETS)
    assert response.status_code == 401
    assert response.json()["exc_type"] == "AuthenticationError"


# --- message preservation -----------------------------------------------------


def test_throw_preserves_the_message_verbatim():
    """CLAUDE.md hard rule 4 - the text is user-facing copy."""
    message = "Organization is required to convert a Lead to a Deal"
    with pytest.raises(ValidationError) as caught:
        throw(message)
    assert caught.value.message == message
    assert build_error_body("ValidationError", [message])["messages"] == [message]


def test_thrown_message_survives_the_round_trip(auth_api):
    body = auth_api.get(f"{WIDGETS}/PZW-0000-00000").json()
    assert "PZW-0000-00000" in body["messages"][0]


def test_validation_errors_from_the_serializer_are_flattened(auth_api):
    """DRF nests field errors; the frontend wants ``['field: message', ...]``."""
    response = auth_api.post(
        "/api/resource/" + quote("Phase Zero Field"), {}, format="json"
    )
    # 417, not DRF's 400: upstream has one status for a validation failure, wherever
    # it is detected, and the port's own ValidationError already answers 417.
    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "ValidationError"
    assert any("organization_name" in m for m in body["messages"])


def test_empty_message_list_never_reaches_the_client():
    """frappe-ui shows ``messages[0]``; an empty list would render a blank toast."""
    body = build_error_body("ValidationError", [])
    assert body["messages"] == ["Internal Server Error"]


# --- naming, linked deletes and bad filters were 500s (FINDINGS.md 1-3) ---------


def test_a_name_with_angle_brackets_is_a_name_error(auth_api):
    """``validate_name`` throws ``frappe.NameError``, which upstream declares with 409
    (``frappe/exceptions.py:50``). It used to be a plain ``ValueError``, so a 500."""
    response = auth_api.post(
        "/api/resource/" + quote("Phase Zero Field"),
        {"organization_name": "ZZ <script>"},
        format="json",
    )
    assert response.status_code == 409
    body = response.json()
    assert body["exc_type"] == "NameError"
    assert body["message"] == "Name cannot contain special characters like '<', '>'"


def test_deleting_a_linked_document_is_a_link_exists_error(administrator, api_as):
    """Django's ``ProtectedError`` subclasses ``IntegrityError`` and was rendered as a
    409 "Duplicate" carrying Django's wording. Upstream refuses with
    ``LinkExistsError`` and the sentence from ``delete_doc.py:452``."""
    from crm_app.models.core_sales import CRMOrganization
    from crm_app.models.taxonomy import CRMIndustry

    industry = CRMIndustry.objects.create(industry="ZZ Fintech")
    CRMOrganization.objects.create(organization_name="ZZ Acme", industry=industry)

    url = "/api/resource/" + quote("CRM Industry") + "/" + quote("ZZ Fintech")
    response = api_as(administrator).delete(url)

    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "LinkExistsError"
    assert body["message"] == (
        "Cannot delete or cancel because CRM Industry ZZ Fintech "
        "is linked with CRM Organization ZZ Acme"
    )
    assert CRMIndustry.objects.filter(pk="ZZ Fintech").exists()


def test_a_link_from_a_child_row_names_the_parent():
    """``delete_doc.py:318-341``: a Link that sits in a child table is reported as the
    parent document, never as the child row itself, and with no row position: only the
    dynamic-link check adds ``at Row``, and the port's foreign keys are static Links."""
    from django.db.models.deletion import ProtectedError

    from crm_app.models.core_sales import CRMContacts, CRMDeal
    from frappe_core.exceptions import link_exists_error
    from frappe_platform.models import Contact

    contact = Contact(name="Ada Lovelace", first_name="Ada", last_name="Lovelace")
    deal = CRMDeal(name="CRM-DEAL-2026-00001")
    row = CRMContacts(parent_deal=deal, contact=contact, idx=2)
    refusal = ProtectedError(
        "Cannot delete some instances of model 'Contact' because they are referenced "
        "through protected foreign keys: 'CRMContacts.contact'.",
        {row},
    )

    error = link_exists_error(refusal)

    assert error.http_status_code == 417
    assert error.message == (
        "Cannot delete or cancel because Contact Ada Lovelace "
        "is linked with CRM Deal CRM-DEAL-2026-00001"
    )


def test_the_link_named_in_the_refusal_is_the_one_reported():
    """A row can hold two links to the same doctype - every document has ``owner`` and
    ``modified_by`` - so the foreign key is matched by the field Django names, not by
    the first field pointing at the model."""
    from django.db.models.deletion import ProtectedError

    from crm_app.models.core_sales import CRMLead
    from frappe_core.exceptions import link_exists_error
    from frappe_platform.models import User

    lead = CRMLead(name="CRM-LEAD-2026-00001")
    lead.owner = User(name="alice@example.com")
    lead.modified_by = User(name="bob@example.com")
    refusal = ProtectedError(
        "Cannot delete some instances of model 'User' because they are referenced "
        "through protected foreign keys: 'CRMLead.modified_by'.",
        {lead},
    )

    assert link_exists_error(refusal).message == (
        "Cannot delete or cancel because User bob@example.com "
        "is linked with CRM Lead CRM-LEAD-2026-00001"
    )


def test_drf_response_headers_survive_the_envelope():
    """``Retry-After`` on a 429 and ``WWW-Authenticate`` on a 401 are set by DRF's own
    handler; the envelope must carry them across rather than check a ``_headers``
    attribute Django's ``HttpResponse`` no longer has."""
    from rest_framework.exceptions import Throttled

    from frappe_core.exceptions import frappe_exception_handler

    response = frappe_exception_handler(Throttled(wait=7), {})

    assert response.status_code == 429
    assert response["Retry-After"] == "7"


def test_a_filter_on_an_unknown_field_is_a_client_error(auth_api):
    """The ORM raised ``FieldError`` and the request answered 500; a typo in a saved
    view's filter is the caller's mistake, and the same sentence ``fields=`` uses."""
    response = auth_api.get(WIDGETS + '?filters=[["no_such_field","=","x"]]')
    assert response.status_code == 400
    body = response.json()
    assert body["exc_type"] == "ValidationError"
    assert body["message"] == "Unknown field 'no_such_field' for this document type"


def test_an_unknown_doctype_on_a_method_endpoint_is_404(auth_api):
    """``registry.DocTypeNotFound`` was a bare ``KeyError``, a 500 on every method
    endpoint that resolves a doctype; the resource routes translated it themselves.
    Upstream's ``frappe.get_meta`` raises ``DoesNotExistError`` (FINDINGS.md 17)."""
    response = auth_api.post(
        "/api/method/crm.api.doc.get_fields", {"doctype": "No Such Doctype"}, format="json"
    )
    assert response.status_code == 404
    body = response.json()
    assert body["exc_type"] == "DoesNotExistError"
    assert body["message"] == "DocType No Such Doctype not found"
