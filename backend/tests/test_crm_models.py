"""Phase 1 clusters 2-6, checked against the DocType JSON itself.

Rather than restating the schema by hand - which would only prove I can copy twice -
these tests read ``crm/fcrm/doctype/<name>/<name>.json`` from the Frappe source and
assert the Django model agrees with it. That covers the phase-1 Codex prompt's questions
directly: missing or wrong fields vs the JSON, layout fieldtypes wrongly made into
columns, wrong Link targets, and child tables exposed as standalone routes.

If the source is not present the schema tests skip rather than pass silently.
"""

import json
from pathlib import Path

import pytest
from django.db.models.fields.related import ForeignKey, OneToOneField

from frappe_core import registry
from frappe_core.naming import AutoIncrement, FieldValue, Format, Hash, NamingSeries, Prompt

FRAPPE_DOCTYPE_DIR = Path(
    r"D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm\fcrm\doctype"
)

#: PHASE_1_MODELS.md section 2 - "SKIP, layout only, not data".
LAYOUT_FIELDTYPES = {
    "Section Break",
    "Column Break",
    "Tab Break",
    "HTML",
    "Heading",
    "Fold",
    "Button",
}

#: Frappe doctype -> (module dir, Django model), for every doctype phase 1 ported.
PORTED = {
    # cluster 3 - taxonomy
    "CRM Lead Status": "crm_lead_status",
    "CRM Deal Status": "crm_deal_status",
    "CRM Lead Source": "crm_lead_source",
    "CRM Industry": "crm_industry",
    "CRM Lost Reason": "crm_lost_reason",
    "CRM Communication Status": "crm_communication_status",
    "CRM Territory": "crm_territory",
    "CRM Product": "crm_product",
    "CRM Products": "crm_products",
    # cluster 2 - core sales
    "CRM Organization": "crm_organization",
    "CRM Lead": "crm_lead",
    "CRM Deal": "crm_deal",
    "CRM Contacts": "crm_contacts",
    "CRM Task": "crm_task",
    "FCRM Note": "fcrm_note",
    # cluster 4 - SLA
    "CRM Service Level Agreement": "crm_service_level_agreement",
    "CRM Service Day": "crm_service_day",
    "CRM Service Level Priority": "crm_service_level_priority",
    "CRM Holiday List": "crm_holiday_list",
    "CRM Holiday": "crm_holiday",
    "CRM Rolling Response Time": "crm_rolling_response_time",
    "CRM Status Change Log": "crm_status_change_log",
    # cluster 5 - telephony
    "CRM Call Log": "crm_call_log",
    "CRM Telephony Agent": "crm_telephony_agent",
    "CRM Telephony Phone": "crm_telephony_phone",
    "CRM Twilio Settings": "crm_twilio_settings",
    "CRM Exotel Settings": "crm_exotel_settings",
    # cluster 6 - UI metadata + misc
    "CRM View Settings": "crm_view_settings",
    "CRM Fields Layout": "crm_fields_layout",
    "CRM Form Script": "crm_form_script",
    "CRM Dashboard": "crm_dashboard",
    "CRM Dropdown Item": "crm_dropdown_item",
    "CRM Notification": "crm_notification",
    "CRM Invitation": "crm_invitation",
    "CRM Sales Hierarchy": "crm_sales_hierarchy",
    "FCRM Settings": "fcrm_settings",
    "CRM Global Settings": "crm_global_settings",
}

#: Deferred to phase 7 (PHASE_1_MODELS.md section 5, "Deferred" row).
DEFERRED = {
    "facebook_lead_form",
    "facebook_lead_form_question",
    "facebook_page",
    "failed_lead_sync_log",
    "lead_sync_source",
    "crm_product_sync_issue",
    "erpnext_crm_settings",
}


def load_doctype_json(dirname: str) -> dict:
    path = FRAPPE_DOCTYPE_DIR / dirname / f"{dirname}.json"
    if not path.exists():
        pytest.skip(f"Frappe source not available at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def data_fields(doc: dict) -> list[dict]:
    return [f for f in doc.get("fields", []) if f.get("fieldtype") not in LAYOUT_FIELDTYPES]


def layout_fields(doc: dict) -> list[dict]:
    return [f for f in doc.get("fields", []) if f.get("fieldtype") in LAYOUT_FIELDTYPES]


def model_field_names(model) -> set[str]:
    names = set()
    for field in model._meta.get_fields():
        if getattr(field, "concrete", False):
            names.add(field.name)
            attname = getattr(field, "attname", None)
            if attname:
                names.add(attname)
    return names


# --- coverage -----------------------------------------------------------------


def test_every_non_deferred_doctype_is_ported():
    """Nothing quietly skipped."""
    if not FRAPPE_DOCTYPE_DIR.exists():
        pytest.skip("Frappe source not available")
    on_disk = {
        d.name
        for d in FRAPPE_DOCTYPE_DIR.iterdir()
        if d.is_dir() and (d / f"{d.name}.json").exists()
    }
    expected = on_disk - DEFERRED
    ported = set(PORTED.values())
    assert expected - ported == set(), f"not ported: {sorted(expected - ported)}"


def test_the_ported_count_matches_the_plan():
    """PORT_PLAN.md section 5 counts 39 CRM doctypes.

    39 directories exist under ``crm/fcrm/doctype``. Two of them are phase-7 deferred
    (``crm_product_sync_issue``, ``erpnext_crm_settings``); the other deferred names in
    the plan (``facebook_*``, ``lead_sync_source``, ``failed_lead_sync_log``) live under
    ``crm/lead_syncing`` and are not in this directory at all. So 37 are in scope here.
    """
    assert len(PORTED) == 37


@pytest.mark.parametrize("doctype", sorted(PORTED))
def test_doctype_is_registered(doctype):
    assert registry.has_doctype(doctype), f"{doctype} is not in the registry"


# --- fields match the JSON ----------------------------------------------------


@pytest.mark.parametrize("doctype,dirname", sorted(PORTED.items()))
def test_every_data_field_exists_on_the_model(doctype, dirname):
    doc = load_doctype_json(dirname)
    model = registry.get_model(doctype)
    present = model_field_names(model)

    missing = [
        f["fieldname"]
        for f in data_fields(doc)
        # Table fields are reverse relations, declared on the child side.
        if f.get("fieldtype") not in ("Table", "Table MultiSelect")
        and f.get("fieldname") not in present
    ]
    assert not missing, f"{doctype} is missing {missing}"


@pytest.mark.parametrize("doctype,dirname", sorted(PORTED.items()))
def test_no_layout_fieldtype_leaked_into_the_model(doctype, dirname):
    """PHASE_1_MODELS.md section 2, trap 1.

    ``crm_lead`` alone declares 21 layout fields against 40 data fields; turning those
    into columns is the classic way to generate junk schema.
    """
    doc = load_doctype_json(dirname)
    model = registry.get_model(doctype)
    present = model_field_names(model)

    leaked = [f["fieldname"] for f in layout_fields(doc) if f.get("fieldname") in present]
    assert not leaked, f"{doctype} materialised layout fields {leaked}"


@pytest.mark.parametrize("doctype,dirname", sorted(PORTED.items()))
def test_table_fields_are_reverse_relations_not_columns(doctype, dirname):
    """A ``Table`` field is a child table, never a column on the parent."""
    doc = load_doctype_json(dirname)
    model = registry.get_model(doctype)
    concrete = {
        f.name for f in model._meta.get_fields() if getattr(f, "concrete", False)
    }
    for field in data_fields(doc):
        if field.get("fieldtype") in ("Table", "Table MultiSelect"):
            assert field["fieldname"] not in concrete, (
                f"{doctype}.{field['fieldname']} is a Table field and must not be a column"
            )


@pytest.mark.parametrize("doctype,dirname", sorted(PORTED.items()))
def test_child_tables_are_flagged_and_not_routable(doctype, dirname):
    """PHASE_1_MODELS.md section 3."""
    doc = load_doctype_json(dirname)
    entry = registry.get_entry(doctype)
    is_child = bool(doc.get("istable"))
    assert entry.is_child_table == is_child, f"{doctype} istable mismatch"
    if is_child:
        assert doctype not in registry.routable_doctypes()
    else:
        assert doctype in registry.routable_doctypes()


@pytest.mark.parametrize("doctype,dirname", sorted(PORTED.items()))
def test_child_tables_carry_frappes_own_columns(doctype, dirname):
    """``parenttype``, ``parentfield`` and ``idx`` - PHASE_1_MODELS.md section 3."""
    doc = load_doctype_json(dirname)
    if not doc.get("istable"):
        pytest.skip("not a child table")
    present = model_field_names(registry.get_model(doctype))
    assert {"parenttype", "parentfield", "idx"} <= present


# --- naming strategies --------------------------------------------------------

EXPECTED_STRATEGY = {
    "naming_series:": NamingSeries,
    "autoincrement": AutoIncrement,
    "hash": Hash,
    "prompt": Prompt,
}


@pytest.mark.parametrize("doctype,dirname", sorted(PORTED.items()))
def test_naming_strategy_matches_the_json(doctype, dirname):
    """PHASE_0_FOUNDATION.md section 2, verified per doctype against ``autoname``."""
    doc = load_doctype_json(dirname)
    autoname = doc.get("autoname")
    model = registry.get_model(doctype)
    strategy = model.get_name_strategy()

    if doc.get("issingle"):
        pytest.skip("singletons are pinned to a fixed name")

    if autoname is None:
        # Frappe's default when autoname is absent is hash.
        assert isinstance(strategy, Hash), f"{doctype} should be hash-named"
    elif autoname.startswith("field:"):
        assert isinstance(strategy, FieldValue), f"{doctype} should use FieldValue"
        assert strategy.fieldname == autoname.split(":", 1)[1]
    elif autoname.startswith("format:"):
        assert isinstance(strategy, Format)
        assert strategy.template == autoname.split(":", 1)[1]
    elif autoname == "naming_series:":
        assert isinstance(strategy, NamingSeries)
    else:
        assert isinstance(strategy, EXPECTED_STRATEGY[autoname]), (
            f"{doctype} autoname={autoname} got {strategy!r}"
        )


def test_the_three_autoincrement_doctypes_have_integer_pks():
    """PHASE_0_FOUNDATION.md section 2 - "genuinely integer PKs"."""
    for doctype in ("CRM Task", "CRM View Settings"):
        model = registry.get_model(doctype)
        assert model._meta.pk.get_internal_type() == "BigAutoField", doctype


def test_naming_series_patterns_match_the_json():
    assert registry.get_model("CRM Lead").get_name_strategy().pattern == "CRM-LEAD-.YYYY.-"
    assert registry.get_model("CRM Deal").get_name_strategy().pattern == "CRM-DEAL-.YYYY.-"


# --- Link targets -------------------------------------------------------------

#: Frappe platform lookups this port deliberately models as plain CharFields rather
#: than tables - see crm_app/models/core_sales.py's module docstring.
UNMODELLED_LINK_TARGETS = {"Salutation", "Gender", "Currency", "Address", "DocType"}


@pytest.mark.parametrize("doctype,dirname", sorted(PORTED.items()))
def test_link_fields_point_at_the_right_doctype(doctype, dirname):
    """A wrong Link target is silent until data is wrong; check every one."""
    doc = load_doctype_json(dirname)
    model = registry.get_model(doctype)

    for field in data_fields(doc):
        if field.get("fieldtype") != "Link":
            continue
        target = field.get("options")
        if target in UNMODELLED_LINK_TARGETS:
            continue
        try:
            django_field = model._meta.get_field(field["fieldname"])
        except Exception:
            pytest.fail(f"{doctype}.{field['fieldname']} missing")
        if not isinstance(django_field, (ForeignKey, OneToOneField)):
            pytest.fail(
                f"{doctype}.{field['fieldname']} links to {target} but is "
                f"{type(django_field).__name__}"
            )
        related = django_field.related_model
        related_doctype = getattr(related, "get_doctype", lambda: None)()
        assert related_doctype == target, (
            f"{doctype}.{field['fieldname']} -> {related_doctype}, expected {target}"
        )


def test_unmodelled_link_targets_are_charfields():
    """The documented deviation, asserted so it stays deliberate."""
    lead = registry.get_model("CRM Lead")
    for fieldname in ("salutation", "gender"):
        assert lead._meta.get_field(fieldname).get_internal_type() == "CharField"


# --- credentials --------------------------------------------------------------


@pytest.mark.parametrize(
    "doctype,fields",
    [
        ("CRM Twilio Settings", ["api_secret", "auth_token"]),
        ("CRM Exotel Settings", ["api_token"]),
    ],
)
def test_password_fieldtypes_are_not_serialisable(doctype, fields):
    """``Password`` in the JSON must not reach the wire.

    ``FCRM Settings.access_key`` is deliberately **not** in this list: the JSON declares
    it ``Data`` and unhidden, so upstream shows it in the settings UI. Blocking it would
    break that screen for a hardening the source does not do. Noted in PROGRESS.md.
    """
    serializer_fields = registry.get_entry(doctype).get_serializer_class()().get_fields()
    for fieldname in fields:
        assert fieldname not in serializer_fields, f"{doctype}.{fieldname} is serialisable"


@pytest.mark.parametrize(
    "doctype,fieldname",
    [
        ("CRM Twilio Settings", "auth_token"),
        ("CRM Exotel Settings", "api_token"),
    ],
)
def test_password_fieldtypes_are_not_selectable(db, doctype, fieldname):
    from frappe_core.exceptions import ValidationError
    from frappe_core.query import fetch_rows

    with pytest.raises(ValidationError, match="not readable"):
        fetch_rows(doctype, fields=["name", fieldname])


def test_every_password_fieldtype_in_the_source_is_declared_sensitive():
    """Catch a phase-1 agent adding a Password field without declaring it."""
    if not FRAPPE_DOCTYPE_DIR.exists():
        pytest.skip("Frappe source not available")
    from frappe_core.field_security import sensitive_fields

    for doctype, dirname in PORTED.items():
        doc = load_doctype_json(dirname)
        model = registry.get_model(doctype)
        blocked = sensitive_fields(model)
        for field in data_fields(doc):
            if field.get("fieldtype") == "Password":
                assert field["fieldname"] in blocked, (
                    f"{doctype}.{field['fieldname']} is a Password field but is not "
                    "in SENSITIVE_FIELDS"
                )
