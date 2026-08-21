"""A6 - every routable doctype is accounted for.

**The standing test.** Five findings across four phases were the same shape:

> A doctype's endpoints are not its attack surface - the generic route is.

Each phase carefully gated the endpoints it wrote, and each time the generated
``/api/resource/`` route stood open beside them doing the same job unguarded. Every
agent's tests passed, because they tested the endpoint just written. Codex caught three;
a manual audit caught the rest. Nothing structural was stopping the sixth.

This test is that structure. It does not decide whether a doctype is safe - it makes the
*absence of a decision* fail. Registering a new doctype now breaks the build until
somebody writes a line here saying which of three things it is:

* it has a **row rule**, or
* it is **reviewed and deliberately open**, with the reason, or
* it is **not yet reviewed**, with what to check.

The third list is deliberately allowed to be non-empty. A test that demanded 24 rules on
the day it was written would have been deleted or blanket-suppressed by the next person
in a hurry; one that demands a *sentence* gets kept, and the sentence is what turns "audit
the route surface" from a vague intention into a finite list of named work.

**Writing a reason you have not checked defeats the entire point.** If you do not know,
put it in NOT_YET_REVIEWED with the question. That is not a failure state, it is the
honest one.
"""

import pytest

from frappe_core import registry
from frappe_core.field_security import restricted_fields, sensitive_fields

#: Test fixtures from `tests_support`, registered only under the test settings.
TEST_DOCTYPE_PREFIX = "Phase Zero"

#: Reviewed, and open on purpose. The reason is the deliverable - it is what a future
#: reader needs in order to disagree with the decision.
REVIEWED_OPEN = {
    # --- reference data: the vocabularies every dropdown in the product renders. Writes
    # are administrative, but upstream grants them to Sales User too (its own
    # `crm_lead_status.json` and siblings), and nothing about a status list is
    # confidential. Reproduced.
    "CRM Lead Status": "reference data - status vocabulary, rendered in every list view",
    "CRM Deal Status": "reference data - status vocabulary, rendered in every list view",
    "CRM Lead Source": "reference data - source vocabulary, shown on every lead form",
    "CRM Industry": "reference data - industry vocabulary, shown on organisation forms",
    "CRM Territory": "reference data - territory tree, shown on lead and deal forms",
    "CRM Lost Reason": "reference data - reasons offered when a deal is marked lost",
    "CRM Communication Status": "reference data - communication status vocabulary",
    "CRM Holiday List": "reference data - business calendar, read by the SLA engine",
    "CRM Dashboard": "chart definitions, not data - `get_dashboard` filters the numbers",
    # --- collaborative records: upstream grants all three roles full CRUD and registers
    # no hook, so an open route here is *faithful*, not a modelling gap. This is the
    # opposite of `Comment`, where upstream's role table restricted access and our missing
    # hook was the divergence.
    #
    # The product relies on it: `pages/Tasks.vue` and `pages/Notes.vue` are company-wide
    # list views with no owner filter, and the task list shows `reference_doctype` so you
    # can see which record each task belongs to. Deferring to the parent - the rule
    # `crm_app/permissions/attachments.py` already implements - would empty those pages of
    # anything attached to a record you cannot open.
    #
    # The residual exposure is real and upstream's: a task titled "Call Acme, they will go
    # to 400k" is readable by someone who cannot open the deal. Reproduced rather than
    # fixed, because it is user-visible behaviour and a deliberate grant, not a bug nobody
    # can observe.
    "CRM Task": (
        "collaborative - upstream grants all roles full CRUD and `pages/Tasks.vue` is a "
        "company-wide board. Deferring to the parent would empty it"
    ),
    "FCRM Note": (
        "same as CRM Task - `pages/Notes.vue` is company-wide, and a note can legitimately "
        "have no parent at all"
    ),
    "CRM Global Settings": (
        "no secrets: holds only `dt`, `type` and a JSON blob. Upstream grants all three "
        "roles full CRUD (`crm_global_settings.json`), deliberately. Reproduced."
    ),
}

#: Registered, routable, and **nobody has audited it**. Each entry names the question,
#: not a guess. Emptying this list is A7.
NOT_YET_REVIEWED = {
    "Contact": "shared across leads and deals; upstream relies on role permissions",
    "CRM Organization": "same as Contact - is org data meant to be company-wide?",
    "Tag": "low risk, but writes are unconstrained",
    "CRM Call Log": "call history references leads and deals; recording URLs are on the row",
    "CRM Telephony Agent": "holds colleagues' phone numbers",
    "CRM Service Level Agreement": "SLA definitions; writes change response deadlines",
    "CRM Product": "catalogue data; writes change prices used in deal totals",
    "Email Template": "writes change the wording of mail the system sends on your behalf",
}


def _real_routable() -> set[str]:
    return {
        dt for dt in registry.routable_doctypes() if not dt.startswith(TEST_DOCTYPE_PREFIX)
    }


def _ruled() -> set[str]:
    return {
        dt
        for dt in _real_routable()
        if registry.get_entry(dt).permission_query_conditions is not None
    }


# --- the standing assertion --------------------------------------------------------------


def test_every_routable_doctype_is_accounted_for():
    """Registering a doctype without deciding what protects it fails here.

    The failure message names the doctype and the three options, because the person who
    hits this will be someone who added a model and has no idea why the build broke.
    """
    accounted = _ruled() | set(REVIEWED_OPEN) | set(NOT_YET_REVIEWED)
    unaccounted = _real_routable() - accounted

    assert not unaccounted, (
        f"Routable doctypes with no decision recorded: {sorted(unaccounted)}.\n"
        "Every doctype registered without `routable=False` is a public CRUD surface "
        "unless a rule says otherwise. Add a row rule in crm_app/permissions/, or add an "
        "entry to REVIEWED_OPEN with the reason, or to NOT_YET_REVIEWED with the question. "
        "See specs/SECURITY_MODEL.md."
    )


def test_the_lists_do_not_overlap_or_go_stale():
    """A doctype that gained a rule must leave the open lists, or the lists stop meaning
    anything - a reader would not know whether an entry is a live decision or a leftover."""
    ruled = _ruled()

    assert not (ruled & set(REVIEWED_OPEN)), (
        f"{sorted(ruled & set(REVIEWED_OPEN))} now have rules - remove them from REVIEWED_OPEN"
    )
    assert not (ruled & set(NOT_YET_REVIEWED)), (
        f"{sorted(ruled & set(NOT_YET_REVIEWED))} now have rules - remove them from "
        "NOT_YET_REVIEWED"
    )
    assert not (set(REVIEWED_OPEN) & set(NOT_YET_REVIEWED)), "a doctype cannot be in both"


def test_the_open_lists_only_name_doctypes_that_exist():
    """Catches a rename or a deletion leaving a dangling entry behind."""
    known = set(registry.all_doctypes())
    for name in (*REVIEWED_OPEN, *NOT_YET_REVIEWED):
        assert name in known, f"{name!r} is listed here but is not a registered doctype"


# --- the invariant that would have caught A3 and A4 ---------------------------------------


def test_a_doctype_holding_secrets_must_have_a_rule():
    """Credentials imply a rule. No exceptions list, because there is no good reason.

    `SENSITIVE_FIELDS` keeps a value out of responses; it does not stop the *record* being
    rewritten, and A3 was exactly that - the mail password was hidden while any caller
    could repoint `smtp_server` at a host they controlled. Hiding the credential was never
    the same as protecting the account.
    """
    ruled = _ruled()
    offenders = []
    for doctype in _real_routable() - ruled:
        model = registry.get_entry(doctype).model
        declared = (sensitive_fields(model) - {"password", "last_login"}) | restricted_fields(
            model
        )
        if declared:
            offenders.append((doctype, sorted(declared)))

    assert not offenders, (
        f"Doctypes declaring secrets with no permission rule: {offenders}. "
        "Hiding a field from responses does not stop the record being rewritten."
    )


@pytest.mark.parametrize("doctype", sorted(NOT_YET_REVIEWED))
def test_an_unreviewed_doctype_carries_a_real_question(doctype):
    """Guards the quality of the backlog, not the code.

    A one-word placeholder here would let the list look complete while meaning nothing,
    which is the failure mode this whole file exists to prevent.
    """
    reason = NOT_YET_REVIEWED[doctype]
    assert len(reason) > 30, f"{doctype}: say what needs checking, not {reason!r}"


@pytest.mark.parametrize("doctype", sorted(REVIEWED_OPEN))
def test_a_deliberately_open_doctype_carries_a_real_reason(doctype):
    reason = REVIEWED_OPEN[doctype]
    assert len(reason) > 30, f"{doctype}: say why it is open, not {reason!r}"


# --- coverage, stated rather than implied -------------------------------------------------


def test_report_the_current_split(capsys):
    """Not an assertion - a number that shows up in the run, so "the route surface is
    audited" is never assumed when a third of it is still on the backlog."""
    ruled, reviewed, pending = len(_ruled()), len(REVIEWED_OPEN), len(NOT_YET_REVIEWED)
    total = ruled + reviewed + pending

    with capsys.disabled():
        print(
            f"\n  route surface: {total} routable | {ruled} ruled | "
            f"{reviewed} reviewed-open | {pending} awaiting review (A7)"
        )

    assert total == len(_real_routable())
