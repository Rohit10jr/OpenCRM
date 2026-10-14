"""``frappe.email.doctype.email_template.email_template.get_email_template``.

``EmailEditor.vue:297-313`` hands the endpoint a template name and the whole lead or deal
it is composing against, and puts ``data.subject`` and ``data.message`` into the composer.

The context shape is the part worth pinning: upstream passes the document *dict itself*
to ``render_template``, so a template says ``{{ first_name }}`` and not
``{{ doc.first_name }}``. Getting that wrong would render every template as placeholders
and look like a template-authoring problem rather than a port bug.
"""

import json

import pytest

from crm_app.models import CRMLead, CRMLeadStatus
from frappe_core import registry
from frappe_core.session import session_user
from frappe_platform.models import EmailTemplate

pytestmark = pytest.mark.django_db

PATH = "/api/method/frappe.email.doctype.email_template.email_template.get_email_template"


def render(client, template_name, doc=None):
    return client.post(PATH, {"template_name": template_name, "doc": doc}, format="json")


@pytest.fixture
def template(administrator):
    with session_user(administrator.name):
        return EmailTemplate.objects.create(
            name="ZZ Welcome",
            subject="Welcome aboard, {{ first_name }}",
            response="<p>Hello {{ first_name }} from {{ organization }}.</p>",
            reference_doctype="CRM Lead",
        )


@pytest.fixture
def lead(alice):
    with session_user(alice.name):
        CRMLeadStatus.objects.get_or_create(lead_status="New", defaults={"type": "Open"})
        return CRMLead.objects.create(
            first_name="Ada", organization="ZZ Analytical", lead_owner=alice
        )


def test_the_documents_fields_are_the_template_variables(auth_api, template, lead):
    """``get_formatted_email`` renders ``subject`` and ``response_`` against the doc dict."""
    doc = {"first_name": lead.first_name, "organization": lead.organization}
    response = render(auth_api, template.name, doc)
    assert response.status_code == 200
    message = response.json()["message"]
    assert message["subject"] == "Welcome aboard, Ada"
    assert message["message"] == "<p>Hello Ada from ZZ Analytical.</p>"


def test_a_json_string_doc_renders_the_same_as_a_dict(auth_api, template):
    """Upstream's ``get_formatted_email`` json-loads a string doc
    (``email_template.py:41-42``); a query-string caller has no other way to send one."""
    doc = {"first_name": "Grace", "organization": "ZZ Compilers"}
    as_dict = render(auth_api, template.name, doc).json()["message"]
    as_string = render(auth_api, template.name, json.dumps(doc)).json()["message"]
    assert as_dict == as_string
    assert as_string["subject"] == "Welcome aboard, Grace"


def test_use_html_switches_the_body_to_response_html(auth_api, administrator):
    """``response_`` is a property, not a column: ``response_html`` when ``use_html`` is
    set, ``response`` otherwise (``email_template.py:28-30``). Both fields can hold
    content at once, so reading the wrong one is silent."""
    with session_user(administrator.name):
        EmailTemplate.objects.create(
            name="ZZ Raw",
            subject="Raw {{ first_name }}",
            response="<p>the rich-text body</p>",
            response_html="<h1>{{ first_name }}</h1>",
            use_html=True,
        )
    message = render(auth_api, "ZZ Raw", {"first_name": "Ada"}).json()["message"]
    assert message["message"] == "<h1>Ada</h1>"
    assert message["subject"] == "Raw Ada"


def test_an_unknown_variable_renders_as_its_own_placeholder(auth_api, template):
    """``get_jenv`` sets ``undefined=DebugUndefined`` (``frappe/utils/jinja.py:35``), so a
    name the document does not carry comes back as ``{{ name }}`` rather than raising or
    silently vanishing. That is what lets a template written for a Deal be applied to a
    Lead: the composer shows the gap and the user fills it in.
    """
    message = render(auth_api, template.name, {"first_name": "Ada"}).json()["message"]
    assert message["subject"] == "Welcome aboard, Ada"
    assert message["message"] == "<p>Hello Ada from {{ organization }}.</p>"


def test_a_doc_that_is_neither_dict_nor_json_renders_placeholders(auth_api, template):
    """Nothing legitimate sends this; the point is that it is not a 500."""
    message = render(auth_api, template.name, "not json at all").json()["message"]
    assert message["subject"] == "Welcome aboard, {{ first_name }}"


def test_the_template_is_sandboxed(auth_api, administrator):
    """Template text is user-authored and rendered server-side, which is server-side
    template injection unless the environment refuses it. ``render_template`` rejects
    dunder access before compiling, with upstream's sentence
    (``frappe/utils/jinja.py:111-112``); the ``SandboxedEnvironment`` is the second wall
    behind it."""
    with session_user(administrator.name):
        EmailTemplate.objects.create(
            name="ZZ Escape", subject="x", response="{{ ''.__class__.__mro__ }}"
        )
    response = render(auth_api, "ZZ Escape", {})
    assert response.status_code == 417
    body = response.json()
    assert body["exc_type"] == "ValidationError"
    assert body["message"] == "Illegal template"


def test_a_missing_template_is_a_404(auth_api):
    response = render(auth_api, "ZZ Nope", {})
    assert response.status_code == 404
    body = response.json()
    assert body["exc_type"] == "DoesNotExistError"
    assert body["message"] == "Email Template ZZ Nope not found"


def test_any_authenticated_user_may_render_a_template(auth_api, template, lead):
    """Upstream calls ``check_permission("read")``, which resolves to the DocType's role
    permissions: ``email_template.json`` gives ``Desk User`` read, and every System User
    holds that role, so every CRM user may render a template. Since FINDINGS.md 87 the
    port has the row rule that says the same (``crm_app/permissions/__init__.py``): reads
    open to everyone, create, write and delete for System Manager alone. The composer's
    template picker keeps listing templates to every Sales User
    (``docs/http/13_bulk_and_misc.http`` 3.7 drives the same read through
    ``/api/resource/``); the refused writes are ``tests/test_email_template_rule.py``.

    The endpoint still calls the check, so this is the rule answering, not its absence.
    """
    assert registry.get_entry("Email Template").has_permission is not None, (
        "the Email Template row rule is gone - FINDINGS.md 87"
    )
    response = render(auth_api, template.name, {"first_name": "Ada"})
    assert response.status_code == 200


def test_get_is_accepted_as_well_as_post(auth_api, template):
    """Upstream's bare ``@frappe.whitelist()`` allows GET, and this endpoint only reads."""
    doc = json.dumps({"first_name": "Ada"})
    response = auth_api.get(PATH, {"template_name": template.name, "doc": doc})
    assert response.status_code == 200
    assert response.json()["message"]["subject"] == "Welcome aboard, Ada"
