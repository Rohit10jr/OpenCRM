"""``validate_name`` and path-style document names.

Frappe ``version-15`` is the branch CRM ``main`` targets
(``.github/workflows/builds.yml:43``). Line references below are to that branch, cloned
at ``D:\\02_Personal\\01_OpenSource\\02_FrameWorks\\frappe``.

Two defects these cover, both found while signing off decision 4 (``field:`` names are
stored verbatim, never slugified):

1. ``validate_name`` was not ported at all - none of upstream's three rules ran, so a
   name containing ``<script>`` reached every list view that renders it.
2. The URL pattern was ``[^/]+``, making any record whose name contains a slash
   permanently unreachable. Upstream routes these with a path converter,
   ``Rule("/resource/<doctype>/<path:name>/")`` (``frappe/api/v1.py:148-151``).
"""

from urllib.parse import quote

import pytest

from frappe_core.exceptions import NameError as FrappeNameError
from frappe_core.exceptions import ValidationError
from frappe_core.naming import validate_name
from tests_support.models import FieldDoc, PromptDoc

pytestmark = pytest.mark.django_db


# --- validate_name, rule by rule ----------------------------------------------
# Upstream: frappe/model/naming.py:476-503


def test_empty_name_is_rejected():
    with pytest.raises(ValidationError, match="No Name Specified for Widget"):
        validate_name("Widget", "")


def test_name_starting_with_new_doctype_is_rejected():
    """naming.py:489-492 - Frappe's marker for a name that failed to generate."""
    with pytest.raises(FrappeNameError, match="please contact the administrator"):
        validate_name("Widget", "New Widget 1")


def test_name_equal_to_the_doctype_is_rejected():
    """naming.py:495-496."""
    with pytest.raises(FrappeNameError, match="Name of Widget cannot be Widget"):
        validate_name("Widget", "Widget")


def test_a_single_may_be_named_after_its_doctype():
    """The ``issingle`` exemption in naming.py:495 - singletons are named this way."""
    assert validate_name("FCRM Settings", "FCRM Settings", is_single=True) == "FCRM Settings"


def test_doctype_named_DocType_is_exempt():
    """naming.py:495 carves out ``name != "DocType"`` explicitly."""
    assert validate_name("DocType", "DocType") == "DocType"


@pytest.mark.parametrize("name", ["<script>", "a>b", "<", ">", "Acme <b>Corp</b>"])
def test_angle_brackets_are_rejected(name):
    """naming.py:498-501. The only characters Frappe forbids - and the reason matters:
    a name is rendered untrusted in every list view."""
    with pytest.raises(FrappeNameError, match="cannot contain special characters"):
        validate_name("Widget", name)


@pytest.mark.parametrize(
    "name",
    [
        "R/GA",              # a real agency
        "A/B Testing Inc",
        "Smith & Co",
        "Cafe #1",
        "Q?A Ltd",
        "Ben+Jerry",
        "ScaleUp Labs",
        "100% Pure",
    ],
)
def test_everything_other_than_angle_brackets_is_a_legal_name(name):
    """Frappe forbids ``<>`` and nothing else. Slashes, spaces, ``#``, ``?``, ``&``
    are all legal, so the port must not invent stricter rules than the source."""
    assert validate_name("CRM Organization", name) == name


def test_name_is_stripped_not_slugified():
    """The whole of decision 4 in one assertion.

    ``_field_autoname`` is ``(cstr(doc.get(fieldname)) or "").strip()``
    (naming.py:553-559). Corroborated by ``crm/demo/deals.py:75-96``, which keys
    ``_org_logos`` by the raw name ``"ScaleUp Labs"`` while its values are slugified
    asset paths - upstream slugifies filenames, never record names.
    """
    assert validate_name("CRM Organization", "  ScaleUp Labs  ") == "ScaleUp Labs"


# --- the rules apply however the name was produced ----------------------------


def test_a_generated_field_name_is_validated():
    with pytest.raises(FrappeNameError, match="cannot contain special characters"):
        FieldDoc.objects.create(organization_name="<script>alert(1)</script>")


def test_a_client_supplied_prompt_name_is_validated():
    """Upstream validates at insert regardless of origin (naming.py:181)."""
    with pytest.raises(FrappeNameError, match="cannot contain special characters"):
        PromptDoc.objects.create(name="<b>x</b>", label="x")


def test_a_generated_name_is_stripped_before_saving():
    doc = FieldDoc.objects.create(organization_name="  Acme Corp  ")
    assert doc.pk == "Acme Corp"


def test_autoincrement_documents_skip_validation():
    """Their PK is None until the database assigns it, so there is nothing to check."""
    from tests_support.models import CounterDoc

    doc = CounterDoc.objects.create(label="x")
    assert isinstance(doc.pk, int)


# --- path-style names over HTTP ------------------------------------------------


def test_a_name_containing_a_slash_is_addressable(auth_api):
    """The routing half of the defect.

    ``[^/]+`` could not match "R/GA", so the record existed but no URL reached it.
    Percent-encoding does not help: WSGI decodes ``%2F`` in PATH_INFO before Django
    resolves the URL, so the pattern itself has to accept the slash.
    """
    FieldDoc.objects.create(organization_name="R/GA")

    url = "/api/resource/" + quote("Phase Zero Field") + "/" + quote("R/GA")
    response = auth_api.get(url)

    assert response.status_code == 200
    assert response.json()["data"]["name"] == "R/GA"


def test_a_name_with_several_slashes_is_addressable(auth_api):
    FieldDoc.objects.create(organization_name="Smith/Jones/Co")

    url = "/api/resource/" + quote("Phase Zero Field") + "/" + quote("Smith/Jones/Co")

    assert auth_api.get(url).json()["data"]["name"] == "Smith/Jones/Co"


def test_a_slashed_name_can_be_updated_and_deleted(auth_api):
    """A read-only fix would be half a fix - PUT and DELETE share the pattern."""
    FieldDoc.objects.create(organization_name="A/B Testing Inc")
    url = "/api/resource/" + quote("Phase Zero Field") + "/" + quote("A/B Testing Inc")

    assert auth_api.put(url, {"organization_name": "A/B Testing Inc"}, format="json").status_code == 200
    assert auth_api.delete(url).status_code == 200
    assert not FieldDoc.objects.filter(pk="A/B Testing Inc").exists()


def test_the_list_route_still_resolves(auth_api):
    """The name group is now ``.+?``; the list route must not be swallowed by it."""
    FieldDoc.objects.create(organization_name="Acme Corp")

    response = auth_api.get("/api/resource/" + quote("Phase Zero Field"))

    assert response.status_code == 200
    assert any(row["name"] == "Acme Corp" for row in response.json()["data"])


def test_an_ordinary_name_is_unaffected(auth_api):
    FieldDoc.objects.create(organization_name="ScaleUp Labs")

    url = "/api/resource/" + quote("Phase Zero Field") + "/" + quote("ScaleUp Labs")

    assert auth_api.get(url).json()["data"]["name"] == "ScaleUp Labs"


# --- the strategies' own refusals are Frappe's, not a 500 (FINDINGS.md 2) -------


def test_an_empty_naming_field_is_reported_by_its_label():
    """``set_name_from_naming_options`` (naming.py:206-210): a ``field:`` doctype with
    nothing in the field says "<Label> is required" - the label, not the fieldname -
    with the default ``frappe.throw`` class, ``ValidationError``."""
    with pytest.raises(ValidationError, match="^Organization Name is required$"):
        FieldDoc.objects.create(organization_name="")


def test_a_strategy_can_carry_the_doctype_json_label():
    """Where the JSON label is not the title-cased fieldname - ``id`` is "ID",
    ``lead_status`` is "Status" - the strategy is told the label explicitly."""
    from frappe_core.naming import FieldValue

    with pytest.raises(ValidationError, match="^Org is required$"):
        FieldValue("organization_name", label="Org").generate(FieldDoc(organization_name=""))


def test_a_prompt_doctype_without_a_name_uses_upstreams_words():
    """``_prompt_autoname`` (naming.py:562-569)."""
    with pytest.raises(ValidationError, match="^Please set the document name$"):
        PromptDoc.objects.create(label="x")
