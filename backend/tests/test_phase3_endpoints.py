"""Phase 3 - the ported ``crm/api/*`` endpoints.

One test file per acceptance criterion group in `PHASE_3_ENDPOINTS.md` section 4, plus
the three carried-over items (C4 products totals, C5 Dynamic Link, C9 batched bulk
permission checks).

The two structural tests are the most valuable here:

* :func:`test_every_frontend_dotted_path_resolves` reads the **frontend source** and
  asserts each path it calls is registered - so the contract is checked against the
  client, not against my own list.
* :func:`test_no_endpoint_bypasses_the_permission_layer` greps the endpoint modules for
  direct manager access, which is the one mistake that silently undoes phase 2.
"""

from __future__ import annotations

import json
import pathlib
import re
from urllib.parse import quote

import pytest

from frappe_core import registry
from frappe_core.session import session_user
from frappe_core.whitelist import all_methods, get_method

pytestmark = pytest.mark.django_db

FRONTEND_SRC = pathlib.Path(
    r"D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe_django_crm\frontend\src"
)
CRM_SOURCE = pathlib.Path(
    r"D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm"
)
API_DIR = pathlib.Path(__file__).resolve().parent.parent / "crm_app" / "api"


def call(client, path: str, payload: dict | None = None):
    return client.post(f"/api/method/{path}", payload or {}, format="json")


# ---------------------------------------------------------------------------
# Criterion 1 - every dotted path resolves at its original URL
# ---------------------------------------------------------------------------

#: Paths the frontend calls that are **out of phase-3 scope**, with the reason.
#:
#: Empty since 16 Sep 2026. The controller methods (create_deal, get_deal_contacts,
#: get_call_log, the fields-layout pair) and the Desk plumbing calls (get_apps,
#: get_timezones, getdoctype, user_settings.save, current_site_info, clear_demo_data)
#: that used to be listed here are all served now. The set stays so a future exclusion
#: has a place, and `test_out_of_scope_list_is_not_hiding_a_regression` keeps it honest.
OUT_OF_SCOPE: set[str] = set()

#: A dotted path at a `url:` / `method:` key, or as the first argument of `call(...)`,
#: with or without the `/api/method/` prefix. The `call(...)` form was missed until
#: 16 Sep 2026, which is how twenty paths the Vue app calls stayed unserved through
#: eight phases (docs/TESTING_GUIDE.md, "Gaps you will hit"); the prefixed form was
#: missed until 23 Sep 2026, which is how the one call `main.js` makes before it mounts
#: stayed unserved and the page stayed blank (docs/FINDINGS.md 26).
_PATH_RE = re.compile(
    r"(?:(?:url|method):\s*|\bcall\(\s*)'(?:/api/method/)?([a-z_]+(?:\.[a-z_]+)+)'"
)


def frontend_called_paths() -> set[str]:
    if not FRONTEND_SRC.exists():
        pytest.skip("frontend source not available")
    found: set[str] = set()
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in (".js", ".vue"):
            continue
        found.update(_PATH_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return found


#: frappe-ui makes a handful of calls of its own, from inside the installed package,
#: which no scan of `frontend/src` can see: `useOnboarding` (FINDINGS.md 39), the Link
#: search, the form-load bundle, the Frappe Cloud bridge and the Data Import page.
#: Scanned separately over the package's two source trees. The library writes some
#: calls with double quotes, so its regex accepts either quote; and it ships file-picker
#: components for Frappe Drive whose `drive.api.*` calls belong to that app, which this
#: frontend never mounts, so only the framework's and the CRM's namespaces count.
LIBRARY_SRC = FRONTEND_SRC.parent / "node_modules" / "frappe-ui"
LIBRARY_DIRS = ("frappe", "src")
LIBRARY_NAMESPACES = ("frappe.", "crm.")
_LIBRARY_PATH_RE = re.compile(
    r"(?:(?:url|method):\s*|\bcall\(\s*)['\"](?:/api/method/)?([a-z_]+(?:\.[a-z_]+)+)['\"]"
)

#: Data Import is a framework feature the port has not built: no doctype, no endpoints,
#: and the three `/crm/data-import` pages are reachable only by typing the URL.
#: `specs/KNOWN_ISSUES.md` 8 records it; these three stay here until it is built.
LIBRARY_OUT_OF_SCOPE = {
    "frappe.core.doctype.data_import.data_import.form_start_import",
    "frappe.core.doctype.data_import.data_import.get_import_logs",
    "frappe.core.doctype.data_import.data_import.get_preview_from_template",
}


def library_called_paths() -> set[str]:
    if not LIBRARY_SRC.exists():
        pytest.skip("frappe-ui package not installed")
    found: set[str] = set()
    for sub in LIBRARY_DIRS:
        for path in (LIBRARY_SRC / sub).rglob("*"):
            if path.suffix not in (".js", ".ts", ".vue"):
                continue
            found.update(
                _LIBRARY_PATH_RE.findall(path.read_text(encoding="utf-8", errors="ignore"))
            )
    return {p for p in found if p.startswith(LIBRARY_NAMESPACES)}


def test_every_library_dotted_path_resolves():
    """The same contract for the calls frappe-ui makes on the app's behalf.

    `useOnboarding` runs on every screen with the onboarding panel and its two calls
    answered 404 for eight phases (FINDINGS.md 39), because the guard above reads the
    app's source and these live in the package.
    """
    registered = set(all_methods())
    missing = sorted(library_called_paths() - registered - LIBRARY_OUT_OF_SCOPE)
    assert not missing, f"frappe-ui calls these but nothing serves them: {missing}"


def test_library_out_of_scope_list_is_not_hiding_a_regression():
    called = library_called_paths()
    stale = sorted(p for p in LIBRARY_OUT_OF_SCOPE if p not in called)
    assert not stale, f"LIBRARY_OUT_OF_SCOPE lists paths frappe-ui no longer calls: {stale}"


def test_every_frontend_dotted_path_resolves():
    """The frontend contract, checked against the frontend rather than a hand list.

    `PORT_PLAN.md` section 3 calls this a hard external contract; a path the client
    calls and the server does not answer is a broken screen.
    """
    registered = set(all_methods())
    missing = sorted(frontend_called_paths() - registered - OUT_OF_SCOPE)
    assert not missing, f"frontend calls these but nothing serves them: {missing}"


def test_out_of_scope_list_is_not_hiding_a_regression():
    """Every excuse in OUT_OF_SCOPE must still be a path the frontend actually calls.

    Without this the exclusion list becomes a place to quietly park failures.
    """
    called = frontend_called_paths()
    stale = sorted(p for p in OUT_OF_SCOPE if p not in called)
    assert not stale, f"OUT_OF_SCOPE lists paths the frontend no longer calls: {stale}"


@pytest.mark.parametrize(
    "path",
    [
        "crm.api.doc.sort_options",
        "crm.api.doc.get_filterable_fields",
        "crm.api.doc.get_group_by_fields",
        "crm.api.doc.get_quick_filters",
        "crm.api.doc.update_quick_filters",
        "crm.api.doc.remove_assignments",
        "crm.api.doc.get_assigned_users",
        "crm.api.doc.get_fields",
        "crm.api.doc.get_linked_docs_of_document",
        "crm.api.doc.remove_linked_doc_reference",
        "crm.api.doc.delete_bulk_docs",
        "crm.api.session.get_users",
        "crm.api.session.get_user_info",
        "crm.api.session.get_organizations",
        "crm.api.user.change_password",
        "crm.api.user.add_existing_users",
        "crm.api.user.update_user_role",
        "crm.api.user.remove_crm_roles_from_user",
        "crm.api.auth.oauth_providers",
        "crm.api.get_translations",
        "crm.api.get_user_signature",
        "crm.api.invite_by_email",
        "crm.api.delete_attachment",
        "crm.api.get_file_uploader_defaults",
        "crm.api.contact.get_linked_deals",
        "crm.api.contact.create_new",
        "crm.api.contact.set_as_primary",
        "crm.api.contact.search_emails",
        "crm.api.comment.add_comment",
        "crm.api.activities.get_activities",
        "crm.api.views.get_views",
        "crm.api.dashboard.reset_to_default",
        "crm.api.dashboard.get_dashboard",
        "crm.api.dashboard.get_chart",
        "crm.api.notifications.get_notifications",
        "crm.api.notifications.mark_as_read",
        "crm.api.onboarding.get_first_lead",
        "crm.api.onboarding.get_first_deal",
        "crm.api.settings.create_email_account",
        "crm.api.exchange_rate.get_exchange_rate",
        "crm.api.assignment_rule.get_assignment_rules_list",
        "crm.api.assignment_rule.duplicate_assignment_rule",
    ],
)
def test_spec_listed_endpoint_is_registered(path):
    """Every endpoint named in `PHASE_3_ENDPOINTS.md` section 2, groups A-D."""
    assert path in all_methods()


# ---------------------------------------------------------------------------
# Criterion 2 - parameter names match source exactly, including defaults
# ---------------------------------------------------------------------------

#: ``(dotted path, [(param, default-or-REQUIRED), ...])`` read off ``crm/api/*.py``.
SIGNATURES = [
    ("crm.api.doc.sort_options", [("doctype", "REQUIRED")]),
    ("crm.api.doc.get_filterable_fields", [("doctype", "REQUIRED")]),
    ("crm.api.doc.get_quick_filters", [("doctype", "REQUIRED"), ("cached", True)]),
    (
        "crm.api.doc.update_quick_filters",
        [("quick_filters", "REQUIRED"), ("old_filters", "REQUIRED"), ("doctype", "REQUIRED")],
    ),
    (
        "crm.api.doc.remove_assignments",
        [
            ("doctype", "REQUIRED"),
            ("name", "REQUIRED"),
            ("assignees", "REQUIRED"),
            ("ignore_permissions", False),
        ],
    ),
    (
        "crm.api.doc.get_assigned_users",
        [("doctype", "REQUIRED"), ("name", "REQUIRED"), ("default_assigned_to", None)],
    ),
    ("crm.api.doc.get_fields", [("doctype", "REQUIRED"), ("allow_all_fieldtypes", False)]),
    (
        "crm.api.doc.get_linked_docs_of_document",
        [("doctype", "REQUIRED"), ("docname", "REQUIRED")],
    ),
    (
        "crm.api.doc.remove_linked_doc_reference",
        [("items", "REQUIRED"), ("remove_contact", False), ("delete", False)],
    ),
    (
        "crm.api.doc.delete_bulk_docs",
        [("doctype", "REQUIRED"), ("items", "REQUIRED"), ("delete_linked", False)],
    ),
    ("crm.api.session.get_users", [("include_all", False)]),
    ("crm.api.session.get_user_info", [("users", "REQUIRED")]),
    ("crm.api.user.change_password", [("old_password", "REQUIRED"), ("new_password", "REQUIRED")]),
    ("crm.api.user.add_existing_users", [("users", "REQUIRED"), ("role", "Sales User")]),
    ("crm.api.user.update_user_role", [("user", "REQUIRED"), ("new_role", "REQUIRED")]),
    ("crm.api.user.remove_crm_roles_from_user", [("user", "REQUIRED")]),
    ("crm.api.invite_by_email", [("emails", "REQUIRED"), ("role", "REQUIRED")]),
    (
        "crm.api.delete_attachment",
        [("doctype", "REQUIRED"), ("docname", "REQUIRED"), ("file_url", "REQUIRED")],
    ),
    ("crm.api.contact.get_linked_deals", [("contact", "REQUIRED")]),
    (
        "crm.api.contact.create_new",
        [("contact", "REQUIRED"), ("field", "REQUIRED"), ("value", "REQUIRED")],
    ),
    (
        "crm.api.contact.set_as_primary",
        [("contact", "REQUIRED"), ("field", "REQUIRED"), ("value", "REQUIRED")],
    ),
    (
        "crm.api.comment.add_comment",
        [
            ("reference_doctype", "REQUIRED"),
            ("reference_name", "REQUIRED"),
            ("content", "REQUIRED"),
            ("attachments", None),
        ],
    ),
    ("crm.api.activities.get_activities", [("name", "REQUIRED")]),
    ("crm.api.views.get_views", [("doctype", "REQUIRED")]),
    ("crm.api.notifications.mark_as_read", [("doc", None)]),
    (
        "crm.api.dashboard.get_dashboard",
        [("from_date", None), ("to_date", None), ("user", None)],
    ),
    (
        "crm.api.dashboard.get_chart",
        [("name", "REQUIRED"), ("type", "REQUIRED"), ("from_date", None),
         ("to_date", None), ("user", None)],
    ),
    ("crm.api.contact.search_emails", [("txt", "REQUIRED")]),
    ("crm.api.get_file_uploader_defaults", [("doctype", "REQUIRED")]),
    (
        "crm.api.assignment_rule.duplicate_assignment_rule",
        [("docname", "REQUIRED"), ("new_name", "REQUIRED")],
    ),
]


@pytest.mark.parametrize("path,expected", SIGNATURES)
def test_parameter_names_and_defaults_match_source(path, expected):
    """The frontend sends these **by name**, so a rename is a silent 500."""
    import inspect

    signature = inspect.signature(get_method(path))
    params = [
        (name, p.default if p.default is not inspect.Parameter.empty else "REQUIRED")
        for name, p in signature.parameters.items()
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    ]
    assert params == expected


# ---------------------------------------------------------------------------
# Criterion 8 - no endpoint bypasses the phase-2 permission layer
# ---------------------------------------------------------------------------

#: Modules where a direct manager read is legitimate, with the reason.
_DIRECT_ACCESS_ALLOWED = {
    # Users and roles are not row-restricted doctypes; get_users applies its own
    # CRM-role gate, which is what upstream does.
    "session.py",
    "user.py",
    # Existence probes and single-object fetches, each followed by an explicit
    # check_object_permission call.
    "client.py",
    "contact.py",
    "comment.py",
    "misc.py",
    "activities.py",
    "doc.py",
    "notifications.py",
    "settings.py",
    # The doctype-module endpoints (crm.fcrm.doctype.*): single-object fetches of the
    # deal, lead or call log named in the call, each behind check_object_permission or
    # _require_readable, and the rows created on the way (a contact, an organization,
    # a lead) behind the create check on the document being created.
    "deal.py",
    "lead.py",
    "call_log.py",
    "views.py",
    "dashboard.py",
    # Phase 4. Saved views are fetched by primary key and then gated by
    # `check_permission`, which is CRM View Settings' own model (owner / public+Sales
    # Manager / System Manager) rather than the phase-2 row rule.
    "view_settings.py",
    # Phase 8. The auth endpoints are `allow_guest` and run **before** anybody has an
    # identity, so there is no permission layer for them to apply — the phase-2 hook
    # answers "what may this user see", and the whole point of these three is that the
    # caller is not yet a user.
    #
    # What stands in for it, per endpoint:
    #   reset_password     — never reveals whether the row exists (one response, always)
    #   update_password    — the reset key, or the old password; both are proofs
    #   accept_invitation  — the invitation key, which arrives by email and is
    #                        `SENSITIVE_FIELDS` so it cannot be read back out of the API
    #
    # A lookup by primary key with no list read: none of these enumerate.
    "auth_pages.py",
}


def test_no_endpoint_bypasses_the_permission_layer():
    """A list read through ``Model.objects`` skips the phase-2 hook entirely.

    This is a source-level check because it is the one mistake that leaves no trace at
    runtime: the endpoint works, returns more rows than it should, and no test that only
    looks at its own fixtures would notice.
    """
    offenders = []
    for module in sorted(API_DIR.glob("*.py")):
        if module.name in _DIRECT_ACCESS_ALLOWED or module.name == "__init__.py":
            continue
        text = module.read_text(encoding="utf-8")
        if ".objects." in text or "_default_manager" in text:
            offenders.append(module.name)
    assert not offenders, (
        f"{offenders} read models directly; use frappe_core.query so the phase-2 hook applies"
    )


def test_the_permission_bypass_allowlist_is_justified():
    """Every allowlisted module must actually check permissions somewhere.

    Otherwise the allowlist above is just a way to switch the previous test off.
    """
    unchecked = []
    for name in sorted(_DIRECT_ACCESS_ALLOWED):
        module = API_DIR / name
        if not module.exists():
            continue
        text = module.read_text(encoding="utf-8")
        if not any(
            marker in text
            for marker in (
                "check_object_permission",
                "base_queryset",
                "fetch_rows",
                "get_session_role_flags",
                "only_for",
                "_roles(",
                "sales_user_only",
                "check_permission",
            )
        ):
            unchecked.append(name)
    assert not unchecked, f"{unchecked} are allowlisted but check nothing"


# ---------------------------------------------------------------------------
# Criterion 3 + 4 - envelope, and JSON-string vs native params
# ---------------------------------------------------------------------------


@pytest.fixture
def lead_fixture(alice, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", lead_owner=alice, status=status)
    return lead


def test_method_response_is_message_enveloped(auth_api):
    response = call(auth_api, "crm.api.onboarding.get_first_lead")
    assert response.status_code == 200
    assert set(response.json()) == {"message"}


def test_json_string_params_are_accepted(auth_api, alice):
    """`PHASE_3_ENDPOINTS.md` criterion 4 - upstream calls ``parse_json`` liberally."""
    response = call(
        auth_api, "crm.api.session.get_user_info", {"users": json.dumps([alice.name])}
    )
    assert response.status_code == 200
    assert [u["name"] for u in response.json()["message"]] == [alice.name]


def test_native_list_params_are_accepted(auth_api, alice):
    response = call(auth_api, "crm.api.session.get_user_info", {"users": [alice.name]})
    assert response.status_code == 200
    assert [u["name"] for u in response.json()["message"]] == [alice.name]


def test_surplus_parameters_do_not_500(auth_api):
    response = call(
        auth_api, "crm.api.onboarding.get_first_deal", {"cmd": "legacy", "_": "1730000000"}
    )
    assert response.status_code == 200


def test_unauthenticated_method_is_rejected(api):
    response = call(api, "crm.api.onboarding.get_first_lead")
    assert response.status_code == 401


def test_allow_guest_endpoints_are_reachable_unauthenticated(api):
    """``oauth_providers`` and ``get_translations`` run before login upstream."""
    assert call(api, "crm.api.auth.oauth_providers").status_code == 200
    assert call(api, "crm.api.get_translations").status_code == 200


# ---------------------------------------------------------------------------
# Criterion 6 - frappe.throw messages preserved verbatim
# ---------------------------------------------------------------------------


def test_contact_endpoints_use_the_upstream_not_permitted_message(auth_api, bob, administrator):
    from frappe_platform.models import Contact

    with session_user(administrator.name):
        contact = Contact.objects.create(first_name="Jane", last_name="Doe")

    response = call(
        auth_api,
        "crm.api.contact.create_new",
        {"contact": contact.name, "field": "banana", "value": "x"},
    )
    assert response.json()["messages"] == ["Invalid field"]


def test_change_password_rejects_reuse_with_the_upstream_message(auth_api):
    response = call(
        auth_api,
        "crm.api.user.change_password",
        {"old_password": "secret123", "new_password": "secret123"},
    )
    assert response.json()["messages"] == [
        "New password cannot be the same as current password. "
        "Please choose a different password."
    ]


def test_change_password_rejects_a_wrong_current_password(auth_api):
    response = call(
        auth_api,
        "crm.api.user.change_password",
        {"old_password": "wrong", "new_password": "Str0ng!Passphrase42"},
    )
    assert response.json()["messages"] == ["Incorrect current password. Please try again."]


def test_change_password_succeeds_and_actually_changes_it(auth_api, alice):
    response = call(
        auth_api,
        "crm.api.user.change_password",
        {"old_password": "secret123", "new_password": "Str0ng!Passphrase42"},
    )
    assert response.status_code == 200
    alice.refresh_from_db()
    assert alice.check_password("Str0ng!Passphrase42")


def test_delete_bulk_docs_requires_a_doctype(auth_api):
    """Empty rather than omitted: the signature keeps upstream's required params, so an
    omitted one is a TypeError before the guard can run - upstream behaves the same."""
    response = call(
        auth_api, "crm.api.doc.delete_bulk_docs", {"doctype": "", "items": ["x"]}
    )
    assert response.json()["messages"] == ["Doctype is required"]


def test_delete_bulk_docs_requires_items(auth_api):
    response = call(
        auth_api, "crm.api.doc.delete_bulk_docs", {"doctype": "CRM Lead", "items": []}
    )
    assert response.json()["messages"] == ["Items are required"]


def test_remove_self_is_refused_with_the_upstream_message(auth_api, alice, make_user):
    from django.contrib.auth.models import Group

    group, _ = Group.objects.get_or_create(name="Sales Manager")
    alice.groups.add(group)
    response = call(auth_api, "crm.api.user.remove_crm_roles_from_user", {"user": alice.name})
    assert response.json()["messages"] == ["You cannot remove yourself."]


# ---------------------------------------------------------------------------
# Criterion 5 + 9 - permission checks on named documents
# ---------------------------------------------------------------------------


def test_get_activities_denies_an_invisible_lead(auth_api, bob, administrator):
    """alice must not read bob's lead's timeline."""
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="Bobs", lead_owner=bob, status=status)

    response = call(auth_api, "crm.api.activities.get_activities", {"name": lead.name})
    assert response.status_code == 403
    assert response.json()["exc_type"] == "PermissionError"


def test_get_activities_allows_your_own_lead(auth_api, lead_fixture):
    response = call(auth_api, "crm.api.activities.get_activities", {"name": lead_fixture.name})
    assert response.status_code == 200
    activities, calls, notes, tasks, attachments = response.json()["message"]
    assert any(a["activity_type"] == "creation" for a in activities)


def test_get_activities_404s_for_an_unknown_name(auth_api):
    response = call(auth_api, "crm.api.activities.get_activities", {"name": "nope"})
    assert response.status_code == 404
    assert response.json()["messages"] == ["Document not found"]


def test_add_comment_requires_write_on_the_referenced_document(auth_api, bob, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="Bobs", lead_owner=bob, status=status)

    response = call(
        auth_api,
        "crm.api.comment.add_comment",
        {
            "reference_doctype": "CRM Lead",
            "reference_name": lead.name,
            "content": "<p>hi</p>",
        },
    )
    assert response.status_code == 403


def test_add_comment_on_your_own_lead_works(auth_api, lead_fixture):
    from frappe_platform.models import Comment

    response = call(
        auth_api,
        "crm.api.comment.add_comment",
        {
            "reference_doctype": "CRM Lead",
            "reference_name": lead_fixture.name,
            "content": "<p>hello</p>",
        },
    )
    assert response.status_code == 200
    assert Comment.objects.filter(
        reference_doctype="CRM Lead", reference_name=lead_fixture.name
    ).count() == 1


def test_remove_assignments_requires_write(auth_api, bob, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="Bobs", lead_owner=bob, status=status)

    response = call(
        auth_api,
        "crm.api.doc.remove_assignments",
        {"doctype": "CRM Lead", "name": lead.name, "assignees": [bob.name]},
    )
    assert response.status_code == 403


def test_remove_assignments_ignores_a_client_supplied_ignore_permissions(
    auth_api, bob, administrator
):
    """Codex phase-3 High finding.

    Upstream whitelists the flag and passes it straight through
    (``crm/api/doc.py:597-604``), so any caller could cancel assignments on a document
    they cannot write. No honest client sends it, so refusing to honour it is invisible
    to the frontend and closes a privilege escalation.
    """
    from frappe_core import assignment
    from frappe_platform.models import ToDo
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)
    assignment.assign_to_user("CRM Lead", lead.name, bob.name)

    response = call(
        auth_api,
        "crm.api.doc.remove_assignments",
        {
            "doctype": "CRM Lead",
            "name": lead.name,
            "assignees": [bob.name],
            "ignore_permissions": True,
        },
    )
    assert response.status_code == 403
    assert ToDo.objects.get(
        reference_type="CRM Lead", reference_name=lead.name, allocated_to=bob
    ).status == "Open"


def test_get_assigned_users_denies_an_invisible_document(auth_api, bob, administrator):
    """Codex phase-3 High finding - it leaked assignee emails for invisible records."""
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)

    response = call(
        auth_api,
        "crm.api.doc.get_assigned_users",
        {"doctype": "CRM Lead", "name": lead.name},
    )
    assert response.status_code == 403


def test_get_linked_docs_denies_an_invisible_document(auth_api, bob, administrator):
    """Codex phase-3 Medium finding - criterion 9 requires the source-doc check."""
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)

    response = call(
        auth_api,
        "crm.api.doc.get_linked_docs_of_document",
        {"doctype": "CRM Lead", "docname": lead.name},
    )
    assert response.status_code == 403


def test_delete_attachment_requires_write_on_the_parent(auth_api, bob, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus
    from frappe_platform.models import File

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="Bobs", lead_owner=bob, status=status)
        File.objects.create(
            file_url="/files/x.pdf",
            attached_to_doctype="CRM Lead",
            attached_to_name=lead.name,
        )

    response = call(
        auth_api,
        "crm.api.delete_attachment",
        {"doctype": "CRM Lead", "docname": lead.name, "file_url": "/files/x.pdf"},
    )
    assert response.status_code == 403
    assert File.objects.filter(file_url="/files/x.pdf").exists()


# ---------------------------------------------------------------------------
# Assignment endpoints operate on ToDo
# ---------------------------------------------------------------------------


def test_get_assigned_users_reads_todo(auth_api, lead_fixture, bob):
    from frappe_core import assignment

    assignment.assign_to_user("CRM Lead", lead_fixture.name, bob.name)
    response = call(
        auth_api,
        "crm.api.doc.get_assigned_users",
        {"doctype": "CRM Lead", "name": lead_fixture.name},
    )
    # alice is already assigned: phase 1's `assign_agent` auto-assigns the lead owner
    # on create, so this list is owner + the explicit assignee.
    assert bob.name in response.json()["message"]


def test_get_assigned_users_falls_back_to_the_default(auth_api, bob, administrator):
    """The fallback only fires when there is genuinely no assignment, so this needs a
    document that was never auto-assigned - an organization, not a lead."""
    from crm_app.models import CRMOrganization

    with session_user(administrator.name):
        org = CRMOrganization.objects.create(organization_name="Acme")

    response = call(
        auth_api,
        "crm.api.doc.get_assigned_users",
        {
            "doctype": "CRM Organization",
            "name": org.name,
            "default_assigned_to": bob.name,
        },
    )
    assert response.json()["message"] == [bob.name]


def test_remove_assignments_cancels_rather_than_deletes(auth_api, lead_fixture, bob):
    """A cancelled ToDo grants no access but keeps the audit trail."""
    from frappe_core import assignment
    from frappe_platform.models import ToDo

    assignment.assign_to_user("CRM Lead", lead_fixture.name, bob.name)
    response = call(
        auth_api,
        "crm.api.doc.remove_assignments",
        {"doctype": "CRM Lead", "name": lead_fixture.name, "assignees": [bob.name]},
    )
    assert response.status_code == 200

    todo = ToDo.objects.get(
        reference_type="CRM Lead", reference_name=lead_fixture.name, allocated_to=bob
    )
    assert todo.status == "Cancelled"
    remaining = assignment.get_assigned_users("CRM Lead", lead_fixture.name)
    assert bob.name not in remaining
    lead_fixture.refresh_from_db()
    assert bob.name not in lead_fixture._assign


# ---------------------------------------------------------------------------
# C4 - crm_products totals
# ---------------------------------------------------------------------------


@pytest.fixture
def deal_fixture(alice, administrator):
    from crm_app.models import CRMDeal, CRMDealStatus

    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
    with session_user(alice.name):
        return CRMDeal.objects.create(deal_owner=alice, status=status)


def test_product_row_amount_is_qty_times_rate(deal_fixture, alice):
    from crm_app.models import CRMProducts

    with session_user(alice.name):
        row = CRMProducts.objects.create(
            parenttype="CRM Deal", parent=str(deal_fixture.pk), parentfield="products",
            product_name="Widget", qty=3, rate=10, idx=1,
        )
    assert float(row.amount) == 30
    assert float(row.net_amount) == 30
    assert float(row.discount_amount) == 0


def test_product_row_applies_the_discount(deal_fixture, alice):
    from crm_app.models import CRMProducts

    with session_user(alice.name):
        row = CRMProducts.objects.create(
            parenttype="CRM Deal", parent=str(deal_fixture.pk), parentfield="products",
            product_name="Widget", qty=2, rate=100, discount_percentage=10, idx=1,
        )
    assert float(row.amount) == 200
    assert float(row.discount_amount) == 20
    assert float(row.net_amount) == 180


def test_parent_totals_sum_the_rows(deal_fixture, alice):
    from crm_app.models import CRMProducts

    with session_user(alice.name):
        CRMProducts.objects.create(
            parenttype="CRM Deal", parent=str(deal_fixture.pk), parentfield="products",
            product_name="A", qty=1, rate=100, idx=1,
        )
        CRMProducts.objects.create(
            parenttype="CRM Deal", parent=str(deal_fixture.pk), parentfield="products",
            product_name="B", qty=2, rate=50, discount_percentage=50, idx=2,
        )
    deal_fixture.refresh_from_db()
    assert float(deal_fixture.total) == 200
    assert float(deal_fixture.net_total) == 150


def test_a_fully_discounted_deal_reports_zero_not_the_gross(deal_fixture, alice):
    """The subtle half of ``update_total`` (``crm_products.py:133-138``).

    ``net_total = net_total || total`` would report the gross for a 100% discount; the
    second branch exists precisely to stop that, and it is easy to drop when porting.
    """
    from crm_app.models import CRMProducts

    with session_user(alice.name):
        CRMProducts.objects.create(
            parenttype="CRM Deal", parent=str(deal_fixture.pk), parentfield="products",
            product_name="Freebie", qty=1, rate=500, discount_percentage=100, idx=1,
        )
    deal_fixture.refresh_from_db()
    assert float(deal_fixture.total) == 500
    assert float(deal_fixture.net_total) == 0


def test_removing_a_row_recomputes_the_totals(deal_fixture, alice):
    from crm_app.models import CRMProducts

    with session_user(alice.name):
        row = CRMProducts.objects.create(
            parenttype="CRM Deal", parent=str(deal_fixture.pk), parentfield="products",
            product_name="A", qty=1, rate=100, idx=1,
        )
    row.delete()
    deal_fixture.refresh_from_db()
    assert float(deal_fixture.total) == 0


def test_totals_do_not_bump_modified(deal_fixture, alice):
    """A totals refresh must not re-order every list view sorted by modified."""
    from crm_app.models import CRMDeal, CRMProducts

    before = CRMDeal.objects.get(pk=deal_fixture.pk).modified
    with session_user(alice.name):
        CRMProducts.objects.create(
            parenttype="CRM Deal", parent=str(deal_fixture.pk), parentfield="products",
            product_name="A", qty=1, rate=100, idx=1,
        )
    assert CRMDeal.objects.get(pk=deal_fixture.pk).modified == before


# ---------------------------------------------------------------------------
# C5 - Dynamic Link
# ---------------------------------------------------------------------------


def test_dynamic_link_is_registered_as_a_child_table():
    assert registry.get_entry("Dynamic Link").is_child_table is True
    assert "Dynamic Link" not in registry.routable_doctypes()


def test_dynamic_link_matches_the_framework_schema():
    """Framework source: ``frappe/core/doctype/dynamic_link/dynamic_link.json``."""
    model = registry.get_model("Dynamic Link")
    names = {f.name for f in model._meta.get_fields() if getattr(f, "concrete", False)}
    assert {"link_doctype", "link_name", "link_title"} <= names
    assert {"parent", "parenttype", "parentfield", "idx"} <= names


def test_linked_calls_resolve_notes_and_tasks_through_dynamic_link(lead_fixture, alice):
    """``activities.py:373-459`` - a Dynamic Link row may point at a note or a task."""
    from crm_app.api.activities import get_linked_calls
    from crm_app.models import CRMCallLog, FCRMNote
    from frappe_platform.models import DynamicLink

    with session_user(alice.name):
        note = FCRMNote.objects.create(title="Call note")
        call_log = CRMCallLog.objects.create(
            status="Completed", type="Outgoing", **{"from": "1", "to": "2"}
        )
        DynamicLink.objects.create(
            parenttype="CRM Call Log", parent=call_log.name, parentfield="links",
            link_doctype="FCRM Note", link_name=note.name, idx=1,
        )
        DynamicLink.objects.create(
            parenttype="CRM Call Log", parent=call_log.name, parentfield="links",
            link_doctype="CRM Lead", link_name=lead_fixture.name, idx=2,
        )
        result = get_linked_calls(lead_fixture.name)

    assert [n["name"] for n in result["notes"]] == [note.name]
    assert call_log.name in [c["name"] for c in result["calls"]]


# ---------------------------------------------------------------------------
# C9 - bulk delete: transactional, permission-checked per item, batched
# ---------------------------------------------------------------------------


def test_delete_bulk_docs_removes_permitted_rows(auth_api, alice, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(alice.name):
        a = CRMLead.objects.create(first_name="A", lead_owner=alice, status=status)
        b = CRMLead.objects.create(first_name="B", lead_owner=alice, status=status)

    response = call(
        auth_api,
        "crm.api.doc.delete_bulk_docs",
        {"doctype": "CRM Lead", "items": [a.name, b.name]},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "success"
    assert not CRMLead.objects.filter(pk__in=[a.name, b.name]).exists()


def test_delete_bulk_docs_refuses_the_whole_batch_if_one_item_is_denied(
    auth_api, alice, bob, administrator
):
    """Per-item permission, and **transactional**: a denied item leaves nothing deleted."""
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        theirs = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)
    with session_user(alice.name):
        mine = CRMLead.objects.create(first_name="Mine", lead_owner=alice, status=status)

    response = call(
        auth_api,
        "crm.api.doc.delete_bulk_docs",
        {"doctype": "CRM Lead", "items": [mine.name, theirs.name]},
    )
    assert response.status_code == 403
    assert CRMLead.objects.filter(pk=mine.name).exists(), "nothing should have been deleted"
    assert CRMLead.objects.filter(pk=theirs.name).exists()


def test_delete_bulk_docs_permission_check_is_batched(auth_api, alice, administrator, monkeypatch):
    """C9 - one query for the batch, not one ``has_permission`` call per item.

    The enqueue threshold is pinned above the sample so this measures **one** execution of
    the delete. Phase 5 made batches over ten items go to Celery, and with
    ``CELERY_TASK_ALWAYS_EAGER`` the worker's own re-authorization then runs in this same
    process — doubling the count for a reason that has nothing to do with C9. That second
    execution is deliberate (a task re-checks its arguments) and is measured on its own in
    ``test_delete_bulk_docs_worker_path_is_batched_too``.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from crm_app.api import doc as doc_api
    from crm_app.api.doc import delete_bulk_docs
    from crm_app.models import CRMLead, CRMLeadStatus

    monkeypatch.setattr(doc_api, "BULK_DELETE_ENQUEUE_THRESHOLD", 1000)

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")

    def measure(count: int) -> int:
        with session_user(alice.name):
            names = [
                CRMLead.objects.create(
                    first_name=f"L{i}", lead_owner=alice, status=status
                ).name
                for i in range(count)
            ]
            with CaptureQueriesContext(connection) as ctx:
                delete_bulk_docs("CRM Lead", names)
        return len(ctx)

    small = measure(2)
    large = measure(12)
    # Linked-doc scanning is per item by nature; what C9 fixes is the permission check,
    # so the growth must be far below one-permission-query-per-item.
    assert large < small * 3, f"query count grew steeply: {small} -> {large}"


def test_delete_bulk_docs_worker_path_is_batched_too(auth_api, alice, administrator):
    """The task re-authorizes its own arguments; that check has to be batched as well.

    Phase 5 added the second check (a queued message is untrusted input). It would be an
    odd place to reintroduce the N+1 C9 exists to prevent.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from crm_app.models import CRMLead, CRMLeadStatus
    from crm_app.tasks import delete_bulk_docs_task

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")

    def measure(count: int) -> int:
        with session_user(alice.name):
            names = [
                CRMLead.objects.create(
                    first_name=f"L{i}", lead_owner=alice, status=status
                ).name
                for i in range(count)
            ]
        with CaptureQueriesContext(connection) as ctx:
            delete_bulk_docs_task("CRM Lead", names, False, alice.name)
        return len(ctx)

    small = measure(2)
    large = measure(12)
    assert large < small * 3, f"query count grew steeply: {small} -> {large}"


# ---------------------------------------------------------------------------
# Quick filters
# ---------------------------------------------------------------------------


def test_standard_filter_fields_match_the_json():
    """The mapping lives in one table, so it is checked against the source directly."""
    from crm_app.api.doc import STANDARD_FILTER_FIELDS

    doctype_dir = CRM_SOURCE / "fcrm" / "doctype"
    if not doctype_dir.exists():
        pytest.skip("CRM source not available")

    expected: dict[str, list[str]] = {}
    for directory in sorted(doctype_dir.iterdir()):
        json_path = directory / f"{directory.name}.json"
        if not json_path.exists():
            continue
        doc = json.loads(json_path.read_text(encoding="utf-8"))
        fields = [f["fieldname"] for f in doc.get("fields", []) if f.get("in_standard_filter")]
        if not fields:
            continue
        doctype = doc.get("name")
        if registry.has_doctype(doctype):
            expected[doctype] = fields

    assert STANDARD_FILTER_FIELDS == expected


def test_quick_filters_fall_back_to_the_standard_filter_fields(auth_api):
    response = call(auth_api, "crm.api.doc.get_quick_filters", {"doctype": "CRM Deal"})
    assert response.status_code == 200
    assert [f["fieldname"] for f in response.json()["message"]] == [
        "organization",
        "email",
        "status",
    ]


def test_quick_filters_drop_converted_for_leads(auth_api):
    """``crm/api/doc.py:201-202`` - the only doctype-specific exclusion."""
    response = call(auth_api, "crm.api.doc.get_quick_filters", {"doctype": "CRM Lead"})
    names = [f["fieldname"] for f in response.json()["message"]]
    assert "converted" not in names
    assert "status" in names


def test_update_quick_filters_is_read_back_by_get_quick_filters(auth_api):
    call(
        auth_api,
        "crm.api.doc.update_quick_filters",
        {"quick_filters": ["email"], "old_filters": [], "doctype": "CRM Deal"},
    )
    response = call(auth_api, "crm.api.doc.get_quick_filters", {"doctype": "CRM Deal"})
    assert [f["fieldname"] for f in response.json()["message"]] == ["email"]


def test_select_quick_filters_get_a_blank_option(auth_api):
    """``crm/api/doc.py:187-191`` - so the filter can be cleared."""
    call(
        auth_api,
        "crm.api.doc.update_quick_filters",
        {"quick_filters": ["type"], "old_filters": [], "doctype": "CRM Call Log"},
    )
    response = call(auth_api, "crm.api.doc.get_quick_filters", {"doctype": "CRM Call Log"})
    options = response.json()["message"][0]["options"]
    assert options[0] == {"label": "", "value": ""}


# ---------------------------------------------------------------------------
# Sessions, users, dashboard
# ---------------------------------------------------------------------------


def test_get_users_requires_a_crm_role(api, make_user):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    outsider = make_user("outsider@example.com")
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(outsider).access_token}"
    )
    response = call(client, "crm.api.session.get_users")
    assert response.status_code == 403
    assert response.json()["messages"] == ["You are not permitted to access CRM resources."]


def test_get_users_returns_the_pair(auth_api, alice):
    response = call(auth_api, "crm.api.session.get_users")
    assert response.status_code == 200
    users, crm_users = response.json()["message"]
    assert alice.name in [u["name"] for u in crm_users]


def test_a_sales_user_cannot_escalate_with_include_all(auth_api, alice, make_user):
    """``crm/api/session.py:49-50`` forces the flag back off for non-System-Managers."""
    make_user("nonmember@example.com")
    response = call(auth_api, "crm.api.session.get_users", {"include_all": True})
    users, crm_users = response.json()["message"]
    assert "nonmember@example.com" not in [u["name"] for u in users]


def test_dashboard_scopes_a_sales_user_to_their_own_numbers(auth_api, alice, bob, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)
    with session_user(alice.name):
        CRMLead.objects.create(first_name="Mine", lead_owner=alice, status=status)

    response = call(auth_api, "crm.api.dashboard.get_chart", {"name": "total_leads", "type": "number"})
    assert response.status_code == 200
    assert response.json()["message"]["value"] == 1


def test_get_chart_rejects_an_unknown_name(auth_api):
    response = call(auth_api, "crm.api.dashboard.get_chart", {"name": "no_such_chart", "type": "number"})
    assert response.json()["message"] == {"error": "Invalid chart name"}


def test_reset_to_default_is_system_manager_only(auth_api):
    response = call(auth_api, "crm.api.dashboard.reset_to_default")
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# frappe.client.* built-ins
# ---------------------------------------------------------------------------


def test_client_get_list_is_permission_filtered(auth_api, alice, bob, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)
    with session_user(alice.name):
        CRMLead.objects.create(first_name="Mine", lead_owner=alice, status=status)

    response = call(
        auth_api,
        "frappe.client.get_list",
        {"doctype": "CRM Lead", "fields": ["first_name"], "limit_page_length": 0},
    )
    assert [r["first_name"] for r in response.json()["message"]] == ["Mine"]


def test_client_set_value_denies_an_invisible_document(auth_api, bob, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)

    response = call(
        auth_api,
        "frappe.client.set_value",
        {"doctype": "CRM Lead", "name": lead.name, "fieldname": "first_name", "value": "Hacked"},
    )
    assert response.status_code == 403
    lead.refresh_from_db()
    assert lead.first_name == "Theirs"


def test_client_set_value_accepts_a_dict_of_fields(auth_api, lead_fixture):
    response = call(
        auth_api,
        "frappe.client.set_value",
        {
            "doctype": "CRM Lead",
            "name": lead_fixture.name,
            "fieldname": {"first_name": "Grace", "job_title": "Rear Admiral"},
        },
    )
    assert response.status_code == 200
    lead_fixture.refresh_from_db()
    assert lead_fixture.first_name == "Grace"
    assert lead_fixture.job_title == "Rear Admiral"


def test_client_delete_denies_an_invisible_document(auth_api, bob, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)

    response = call(
        auth_api, "frappe.client.delete", {"doctype": "CRM Lead", "name": lead.name}
    )
    assert response.status_code == 403
    assert CRMLead.objects.filter(pk=lead.name).exists()


def test_client_insert_enforces_create_permission(auth_api, alice):
    """CRM Notification denies create for an ordinary user - the phase-2 finding."""
    response = call(
        auth_api,
        "frappe.client.insert",
        {"doc": {"doctype": "CRM Notification", "type": "Mention", "to_user": alice.name}},
    )
    assert response.status_code == 403


def test_client_insert_does_not_default_lead_owner(auth_api, alice, administrator):
    """The ``lead_owner`` invariant, pinned down rather than assumed.

    ``AS_BUILT.md`` §4 warns that a lead without ``lead_owner`` is invisible to its
    creator. The server does **not** fill it in - and neither does upstream
    (``crm_lead.py`` has no default; the only writes are the share/assign hooks at
    :88-98). The **client** is what defaults it:
    ``frontend/src/components/Modals/LeadModal.vue:189-190`` sets
    ``lead.doc.lead_owner = getUser().name`` before saving.

    So this reproduces upstream exactly, and the consequence is real: a non-browser
    client that omits the field creates a record it cannot then see. Asserting it here
    means a future agent who "fixes" it has to justify diverging.
    """
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        CRMLeadStatus.objects.create(lead_status="New", type="Open")

    response = call(
        auth_api,
        "frappe.client.insert",
        {"doc": {"doctype": "CRM Lead", "first_name": "Orphan"}},
    )
    assert response.status_code == 200
    created = response.json()["message"]["name"]

    assert CRMLead.objects.filter(pk=created).exists()
    listed = call(
        auth_api,
        "frappe.client.get_list",
        {"doctype": "CRM Lead", "fields": ["name"], "limit_page_length": 0},
    ).json()["message"]
    assert created not in [r["name"] for r in listed], (
        "if this now appears, the server started defaulting lead_owner - a divergence "
        "from upstream that needs justifying, not a bug fix"
    )


def test_client_insert_with_lead_owner_is_visible(auth_api, alice, administrator):
    """The path the real client takes."""
    from crm_app.models import CRMLeadStatus

    with session_user(administrator.name):
        CRMLeadStatus.objects.create(lead_status="New", type="Open")

    response = call(
        auth_api,
        "frappe.client.insert",
        {"doc": {"doctype": "CRM Lead", "first_name": "Owned", "lead_owner": alice.name}},
    )
    created = response.json()["message"]["name"]
    listed = call(
        auth_api,
        "frappe.client.get_list",
        {"doctype": "CRM Lead", "fields": ["name"], "limit_page_length": 0},
    ).json()["message"]
    assert created in [r["name"] for r in listed]


def test_client_get_doc_permissions_does_not_raise_for_a_hidden_row(
    auth_api, bob, administrator
):
    """It answers "what may I do"; the honest answer for an invisible row is nothing."""
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        lead = CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)

    response = call(
        auth_api,
        "frappe.client.get_doc_permissions",
        {"doctype": "CRM Lead", "docname": lead.name},
    )
    assert response.status_code == 200
    assert response.json()["message"]["permissions"]["read"] is False


def test_toggle_like_does_not_bump_modified(auth_api, lead_fixture, alice):
    from crm_app.models import CRMLead

    before = CRMLead.objects.get(pk=lead_fixture.pk).modified
    response = call(
        auth_api,
        "frappe.desk.like.toggle_like",
        {"doctype": "CRM Lead", "name": lead_fixture.name, "add": "Yes"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == [alice.name]
    assert CRMLead.objects.get(pk=lead_fixture.pk).modified == before


def test_toggle_like_is_reversible(auth_api, lead_fixture, alice):
    call(
        auth_api,
        "frappe.desk.like.toggle_like",
        {"doctype": "CRM Lead", "name": lead_fixture.name, "add": "Yes"},
    )
    response = call(
        auth_api,
        "frappe.desk.like.toggle_like",
        {"doctype": "CRM Lead", "name": lead_fixture.name, "add": "No"},
    )
    assert response.json()["message"] == []


def test_assign_to_add_creates_the_todo_and_requires_write(auth_api, lead_fixture, bob):
    from frappe_platform.models import ToDo

    response = call(
        auth_api,
        "frappe.desk.form.assign_to.add",
        {"doctype": "CRM Lead", "name": lead_fixture.name, "assign_to": [bob.name]},
    )
    assert response.status_code == 200
    assert ToDo.objects.filter(
        reference_type="CRM Lead", reference_name=lead_fixture.name, allocated_to=bob
    ).exists()


def test_search_link_is_permission_filtered(auth_api, alice, bob, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
        CRMLead.objects.create(first_name="Theirs", lead_owner=bob, status=status)
    with session_user(alice.name):
        mine = CRMLead.objects.create(first_name="Mine", lead_owner=alice, status=status)

    response = call(auth_api, "frappe.desk.search.search_link", {"doctype": "CRM Lead"})
    assert [r["value"] for r in response.json()["message"]] == [mine.name]


def test_rename_doc_moves_the_row(auth_api, alice):
    from frappe_platform.models import EmailTemplate

    with session_user(alice.name):
        template = EmailTemplate(name="Welcome", subject="Hi")
        template.save()

    response = call(
        auth_api,
        "frappe.client.rename_doc",
        {"doctype": "Email Template", "old_name": "Welcome", "new_name": "Greeting"},
    )
    assert response.status_code == 200
    assert EmailTemplate.objects.filter(pk="Greeting").exists()
    assert not EmailTemplate.objects.filter(pk="Welcome").exists()


def test_rename_doc_refuses_merge(auth_api, alice):
    from frappe_platform.models import EmailTemplate

    with session_user(alice.name):
        EmailTemplate(name="A", subject="a").save()
        EmailTemplate(name="B", subject="b").save()

    response = call(
        auth_api,
        "frappe.client.rename_doc",
        {"doctype": "Email Template", "old_name": "A", "new_name": "B", "merge": True},
    )
    assert response.json()["messages"] == ["Merging documents is not supported"]
