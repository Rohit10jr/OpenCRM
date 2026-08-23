"""The sync itself.

Ports `crm/lead_syncing/doctype/lead_sync_source/facebook.py`'s `FacebookSyncSource` and
the page/form discovery around it.
"""

from __future__ import annotations

import json
import logging
import traceback as traceback_module

from django.db import transaction
from django.utils import timezone

from crm_app.integrations.facebook import graph

logger = logging.getLogger(__name__)


class DuplicateLeadError(Exception):
    """`facebook.py:9-10` — an expected outcome of a re-run, not a failure."""


def is_enabled() -> bool:
    from django.conf import settings

    return bool(getattr(settings, "ENABLE_FACEBOOK_LEAD_SYNC", False))


#: Who owns a lead that arrives from Facebook.
#:
#: `AS_BUILT.md` §4 is explicit that an integration must set this, and equally explicit that
#: stamping "whoever ran the script" is wrong — it silently claims records for one person
#: and is unrecoverable once the data exists.
#:
#: Upstream sets nothing at all (`facebook.py:52-59` inserts with only the mapped fields),
#: so upstream's Facebook leads are invisible to every Sales User and visible only to
#: managers. That is a real defect there — `UPSTREAM_BUGS` #29 — and reproducing it would
#: mean the feature does not work.
#:
#: `Administrator` is the choice: it is the account the sync runs as, the records are
#: visible to managers exactly as upstream's are, and it claims nothing for a real person.
#: Assignment rules or a manager then hand them out, which is the workflow the product
#: already has.
DEFAULT_LEAD_OWNER = "Administrator"

#: `install.py:391-414` seeds fifteen default `CRM Lead Source` rows, and `Facebook` is one
#: of them (`:404`).
FACEBOOK_LEAD_SOURCE = "Facebook"


def ensure_facebook_lead_source() -> str:
    """Return the `CRM Lead Source` name to stamp on a synced lead, creating it if absent.

    Upstream writes the string ``"Facebook"`` into a Link field and relies on
    `add_default_lead_sources()` having run at install. **This port never ported that
    seeding**, so the row does not exist and `CRMLead.source` is a real foreign key — the
    insert fails with a `ValueError` that the per-lead `except` would swallow into a
    failure log. Every synced lead would be logged as a failure, and the only symptom
    would be leads that never arrive.

    Creating it on demand is the smallest correct fix: the row is upstream's, its absence
    is this port's gap, and a lead source is a lookup value rather than a decision.

    The wider gap — that none of the fifteen default sources or statuses are seeded — is
    recorded in the progress file. It belongs in an install/bootstrap step, not here.
    """
    from crm_app.models import CRMLeadSource

    # `autoname=field:source_name`, so the PK is the name and creating it means supplying
    # that field rather than the pk.
    if not CRMLeadSource._default_manager.filter(pk=FACEBOOK_LEAD_SOURCE).exists():
        CRMLeadSource._default_manager.create(source_name=FACEBOOK_LEAD_SOURCE)
    return FACEBOOK_LEAD_SOURCE


class FacebookSyncSource:
    """`facebook.py:20-138`."""

    def __init__(self, access_token: str, form_id: str, source=None):
        self.access_token = access_token
        self.form_id = str(form_id)
        self.source = source
        self._questions = None

    # -- mapping ---------------------------------------------------------------

    def question_mapping(self) -> dict:
        """`facebook.py:85-98` — form question key -> CRM Lead fieldname.

        Questions with no mapping are dropped, which is upstream's behaviour and the reason
        a freshly-discovered form syncs nothing until somebody maps its questions.
        """
        if self._questions is not None:
            return self._questions

        from crm_app.models import FacebookLeadFormQuestion

        rows = FacebookLeadFormQuestion._default_manager.filter(
            parent_form_id=self.form_id
        ).values_list("key", "mapped_to_crm_field")
        self._questions = {key: field for key, field in rows if key and field}
        return self._questions

    # -- fetching --------------------------------------------------------------

    @property
    def last_synced_at(self):
        return getattr(self.source, "last_synced_at", None)

    def fetch_leads(self) -> list[dict]:
        """`facebook.py:68-83`, plus pagination — see `graph.get_paged`."""
        params = {
            "access_token": self.access_token,
            "fields": "id,created_time,field_data",
            "limit": graph.PAGE_SIZE,
        }
        if self.last_synced_at:
            params["filtering"] = json.dumps(
                [
                    {
                        "field": "time_created",
                        "operator": "GREATER_THAN",
                        "value": int(self.last_synced_at.timestamp()),
                    }
                ]
            )
        return graph.get_paged(f"/{self.form_id}/leads", params)

    # -- writing ---------------------------------------------------------------

    def lead_fields(self, lead: dict) -> dict:
        """`facebook.py:41-49` — the Graph payload flattened onto CRM Lead fields."""
        mapping = self.question_mapping()
        answers = {
            item["name"]: (item.get("values") or [""])[0]
            for item in (lead.get("field_data") or [])
            if item.get("name")
        }
        fields = {mapping[k]: v for k, v in answers.items() if k in mapping}
        fields["source_id"] = ensure_facebook_lead_source()
        fields["facebook_lead_id"] = str(lead.get("id") or "")
        fields["facebook_form_id"] = self.form_id
        return fields

    def validate_duplicate_lead(self, fields: dict) -> None:
        """`facebook.py:134-138` — **the actual idempotency guarantee**.

        Matches on every *mapped* field plus the form id, so the same person submitting two
        different forms is two leads, and the same submission arriving twice is one.

        Upstream matches on `field_mapping.values()` and would `KeyError` if a mapped field
        were missing from a particular lead's payload — Facebook omits unanswered optional
        questions. Here the filter is built from the fields actually present, which is the
        same query for a complete payload and does not crash on an incomplete one.
        `UPSTREAM_BUGS` #30.
        """
        from crm_app.models import CRMLead

        mapping = self.question_mapping()
        filters = {
            field: fields[field] for field in mapping.values() if field in fields
        }
        filters["facebook_form_id"] = self.form_id

        if CRMLead._default_manager.filter(**filters).exists():
            raise DuplicateLeadError

    def sync_single_lead(self, lead: dict, raise_exception: bool = False) -> tuple[str, object]:
        """`facebook.py:40-66`. Returns ``(outcome, record)``.

        Outcome is one of ``created`` / ``duplicate`` / ``failed``. Upstream returns the
        document or ``None``, which cannot distinguish "already had it" from "broke" —
        and those need different responses from an operator.

        A failure logs and continues. One malformed lead in a batch of 500 must not stop
        the other 499, which is why upstream catches per lead rather than per sync.
        """
        from crm_app.models import CRMLead

        try:
            fields = self.lead_fields(lead)
            self.validate_duplicate_lead(fields)

            fields.setdefault("lead_owner_id", DEFAULT_LEAD_OWNER)
            with transaction.atomic():
                return "created", CRMLead._default_manager.create(**fields)
        except DuplicateLeadError:
            self.log_failure(lead, "Duplicate")
            if raise_exception:
                raise
            return "duplicate", None
        except Exception:
            self.log_failure(lead, "Failure", traceback_module.format_exc())
            if raise_exception:
                raise
            return "failed", None

    def log_failure(self, lead: dict | None, type: str = "Failure", traceback: str | None = None):
        """`facebook.py:104-118`.

        The log holds the raw Graph payload, which contains the person's name, email and
        phone. That is what makes `Failed Lead Sync Log` a doctype with a row rule rather
        than an open one.
        """
        from crm_app.models import FailedLeadSyncLog

        return FailedLeadSyncLog._default_manager.create(
            type=type,
            lead_data=json.dumps(lead or {}),
            traceback=traceback or "",
            source=self.source,
        )

    def update_last_synced_at(self) -> None:
        """`facebook.py:120-126`.

        A bare `update()`: this runs from a worker, and `save()` would stamp `modified_by`
        with whoever the worker happens to be running as.
        """
        if self.source is None:
            return
        from crm_app.models import LeadSyncSource

        now = timezone.now()
        LeadSyncSource._default_manager.filter(pk=self.source.pk).update(last_synced_at=now)
        self.source.last_synced_at = now

    def sync(self) -> dict:
        """`facebook.py:35-39`. Returns a summary rather than None, so the task result says
        something useful in the Celery backend."""
        leads = self.fetch_leads()
        counts = {"created": 0, "duplicate": 0, "failed": 0}

        for lead in leads:
            outcome, _record = self.sync_single_lead(lead)
            counts[outcome] += 1

        self.update_last_synced_at()
        return {"fetched": len(leads), **counts}


# ---------------------------------------------------------------------------
# Discovery — pages and forms
# ---------------------------------------------------------------------------


def get_account_details(access_token: str) -> dict:
    """`facebook.py:162-168`. Message preserved verbatim."""
    from frappe_core.exceptions import throw

    try:
        return graph.get("me", {"access_token": access_token})
    except Exception:
        throw("Please check your access token")


def fetch_and_store_pages(access_token: str) -> list[dict]:
    """`facebook.py:141-160` — discover the pages this token can see, and their forms."""
    from frappe_core.exceptions import throw

    from crm_app.models import FacebookPage

    if not access_token:
        throw("Access token is required")

    account = get_account_details(access_token)
    if not account.get("id"):
        throw("Invalid access token provided for Facebook.")

    pages = graph.get("/me/accounts", {"access_token": access_token}).get("data") or []

    for page in pages:
        page_id = str(page.get("id") or "")
        if not page_id:
            continue
        if not FacebookPage._default_manager.filter(pk=page_id).exists():
            FacebookPage._default_manager.create(
                id=page_id,
                page_name=page.get("name") or "",
                category=page.get("category") or "",
                account_id=str(account["id"]),
                access_token=page.get("access_token") or "",
            )
        page["forms"] = fetch_and_store_forms(page_id, page.get("access_token") or "")

    return pages


def fetch_and_store_forms(page_id: str, page_access_token: str) -> list[dict]:
    """`facebook.py:184-205`."""
    from crm_app.models import FacebookLeadForm, FacebookLeadFormQuestion

    forms = graph.get_paged(
        f"/{page_id}/leadgen_forms",
        {
            "access_token": page_access_token,
            "fields": "id,name,questions",
            "limit": graph.PAGE_SIZE,
        },
    )

    for form in forms:
        form_id = str(form.get("id") or "")
        if not form_id or FacebookLeadForm._default_manager.filter(pk=form_id).exists():
            continue

        record = FacebookLeadForm._default_manager.create(
            id=form_id, form_name=form.get("name") or "", page_id=page_id
        )
        for idx, question in enumerate(form.get("questions") or [], start=1):
            FacebookLeadFormQuestion._default_manager.create(
                parent_form=record,
                idx=idx,
                label=question.get("label") or "",
                key=question.get("key") or "",
                type=question.get("type") or "",
                id=str(question.get("id") or ""),
                # Left blank: mapping a question to a CRM field is an operator decision,
                # and guessing it would silently write data into the wrong column.
                mapped_to_crm_field="",
            )

    return forms


def sync_source(source) -> dict:
    """`lead_sync_source.py:62-68` — run one source."""
    from frappe_core.exceptions import throw

    if source.type != "Facebook":
        return {"skipped": f"unsupported source type {source.type}"}
    if not source.facebook_lead_form_id:
        throw("Please select a lead gen form before syncing!")

    token = source.get_password("access_token")
    if not token:
        return {"skipped": "no access token"}

    return FacebookSyncSource(token, source.facebook_lead_form_id, source=source).sync()


def sync_due_sources(frequency: str) -> dict:
    """Every enabled source on this schedule. Called by phase 5's six registered tasks.

    A failure in one source must not stop the others: a bad token on one form would
    otherwise silently stop every other form on the same schedule.
    """
    from crm_app.models import LeadSyncSource

    results = {}
    sources = LeadSyncSource._default_manager.filter(
        enabled=True, background_sync_frequency=frequency
    )
    for source in sources:
        try:
            results[str(source.pk)] = sync_source(source)
        except Exception as exc:
            logger.warning("facebook: sync failed for source %s", source.pk, exc_info=True)
            results[str(source.pk)] = {"error": str(exc)}
    return {"frequency": frequency, "sources": results}
