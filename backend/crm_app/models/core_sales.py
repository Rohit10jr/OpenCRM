"""Cluster 2 - core sales. The heaviest logic in the port.

PHASE_1_MODELS.md section 5: "Read controllers line by line." Sources:
``crm_lead.py`` (545 LOC), ``crm_deal.py`` (472), plus the organization, task, note and
contacts doctypes.

Every ``frappe.throw`` ported below keeps its message **verbatim** - CLAUDE.md hard
rule 4, it is user-facing copy.

### Links to doctypes this port does not model

``Salutation``, ``Gender``, ``Currency``, ``Address`` and ``DocType`` are Frappe
platform lookups outside PHASE_1_MODELS.md section 1's list of nine. They are ported as
``CharField``s holding the same link value, which is wire-identical (the client sends
and receives ``"Mr"``, ``"USD"``, ``"CRM Lead"``) without dragging five more platform
tables into scope. Logged in PROGRESS.md.

### SLA fields

``sla``, ``sla_status``, ``response_by``, ``first_response_time`` and friends are ported
as **columns** here because they are part of the schema and the frontend reads them. The
logic that fills them (``set_sla`` / ``apply_sla``) is phase 5 - see PHASE_5_ASYNC.md
section 4, which establishes that upstream computes them on write, not on a schedule.
:meth:`CRMLead.apply_sla` / :meth:`CRMDeal.apply_sla` are the named seams.
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone

from frappe_core import assignment, registry
from frappe_core.exceptions import MandatoryError, ValidationError
from frappe_core.models import AutoIncrementDocument, BaseDocument
from frappe_core.naming import FieldValue, Hash, NamingSeries
from frappe_core.registry import register_doctype
from frappe_core.session import get_current_user

EMPLOYEE_COUNT_CHOICES = [
    (c, c) for c in ("1-10", "11-50", "51-200", "201-500", "501-1000", "1000+")
]

SLA_STATUS_CHOICES = [
    (c, c)
    for c in ("", "First Response Due", "Rolling Response Due", "Failed", "Fulfilled")
]

TASK_PRIORITY_CHOICES = [(c, c) for c in ("Low", "Medium", "High")]
TASK_STATUS_CHOICES = [
    (c, c) for c in ("Backlog", "Todo", "In Progress", "Done", "Canceled")
]


@register_doctype("CRM Organization")
class CRMOrganization(BaseDocument):
    """``autoname=field:organization_name`` - the PK is the display name, verbatim.

    Not slugified. ``crm/demo/deals.py:75-96`` keys a logo dict by ``"ScaleUp Labs"``
    and looks it up with the Link value, which is this PK; a slug would miss every time.
    See PROGRESS.md, phase 0, for the full argument.
    """

    organization_name = models.CharField(max_length=140, blank=True, default="")
    website = models.CharField(max_length=280, blank=True, default="")
    organization_logo = models.CharField(max_length=500, blank=True, default="")
    no_of_employees = models.CharField(
        max_length=20, choices=EMPLOYEE_COUNT_CHOICES, blank=True, default=""
    )
    annual_revenue = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    industry = models.ForeignKey(
        "crm_app.CRMIndustry", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    territory = models.ForeignKey(
        "crm_app.CRMTerritory", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    # Link to Frappe's Currency / Address - not modelled; see the module docstring.
    currency = models.CharField(max_length=140, blank=True, default="")
    address = models.CharField(max_length=140, blank=True, default="")
    exchange_rate = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["-modified"]
        name_strategy = FieldValue("organization_name")

    def update_exchange_rate(self, system_currency: str = "USD", fx_rate=None):
        """``crm_organization.py:validate -> update_exchange_rate``.

        Upstream reads the system currency from ``FCRM Settings`` and calls an external
        FX service. Both are injected here: the settings read belongs to the caller
        (phase 3) and the FX call is a phase-7 integration behind a feature flag
        (``ENABLE_*`` in settings). The *rule* - recompute when the currency changed or
        no rate is set, default to 1 when the currency matches the system one - is
        ported exactly.
        """
        if self.exchange_rate and not self._currency_changed():
            return
        rate = 1
        if self.currency and self.currency != system_currency and fx_rate is not None:
            rate = fx_rate
        self.exchange_rate = rate

    def _currency_changed(self) -> bool:
        if self._state.adding or not self.pk:
            return True
        previous = (
            type(self)._default_manager.filter(pk=self.pk).values_list("currency", flat=True).first()
        )
        return previous != self.currency

    @staticmethod
    def default_list_data():
        return {
            "columns": [
                {"label": "Organization", "type": "Data", "key": "organization_name", "width": "11rem"},
                {"label": "Website", "type": "Data", "key": "website", "width": "14rem"},
                {"label": "Industry", "type": "Link", "key": "industry", "width": "14rem"},
                {"label": "Annual Revenue", "type": "Currency", "key": "annual_revenue", "width": "14rem"},
                {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
            ],
            "rows": [
                "name",
                "organization_name",
                "organization_logo",
                "website",
                "industry",
                "annual_revenue",
                "modified",
            ],
        }


class SLAFieldsMixin(models.Model):
    """The SLA columns shared by CRM Lead and CRM Deal, identical in both JSONs."""

    sla = models.ForeignKey(
        "crm_app.CRMServiceLevelAgreement",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    sla_creation = models.DateTimeField(null=True, blank=True)
    sla_status = models.CharField(
        max_length=40, choices=SLA_STATUS_CHOICES, blank=True, default=""
    )
    response_by = models.DateTimeField(null=True, blank=True)
    # `Duration` is seconds (PHASE_1_MODELS.md section 2).
    first_response_time = models.IntegerField(null=True, blank=True)
    first_responded_on = models.DateTimeField(null=True, blank=True)
    last_response_time = models.IntegerField(null=True, blank=True)
    last_responded_on = models.DateTimeField(null=True, blank=True)
    communication_status = models.ForeignKey(
        "crm_app.CRMCommunicationStatus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        abstract = True

    def apply_sla(self):
        """PHASE 5 seam.

        Upstream calls ``set_sla()`` from ``before_validate`` and ``apply_sla()`` from
        ``before_save`` (``crm_lead.py:78-79,99-100``), mutating the fields above in
        place. Phase 5 fills this in; phase 1 only owns the columns.
        """
        return None


class StatusLifecycleMixin(models.Model):
    """Default the status on create, and log every status transition.

    Ports ``validate_status`` (``crm_lead.py:103-108``, ``crm_deal.py:107-112``) and
    ``add_status_change_log`` (``crm_status_change_log.py:45-83``). Subclasses set
    :attr:`status_model_name` and :attr:`default_status`.
    """

    #: ``"CRM Lead Status"`` or ``"CRM Deal Status"``.
    status_model_name: str = ""
    #: ``"New"`` for a lead, ``"Qualification"`` for a deal.
    default_status: str = ""

    class Meta:
        abstract = True

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_status = getattr(instance, "status_id", None)
        return instance

    def validate_status(self) -> None:
        """Only fires on create, and only when the caller supplied nothing."""
        if not self._state.adding or self.status_id:
            return

        status_model = registry.get_model(self.status_model_name)
        if status_model._default_manager.filter(pk=self.default_status).exists():
            self.status_id = self.default_status
            return

        first_open = (
            status_model._default_manager.filter(type="Open")
            .order_by("name")
            .values_list("pk", flat=True)
            .first()
        )
        if first_open:
            self.status_id = first_open

    def _status_type(self, status) -> str:
        if not status:
            return ""
        status_model = registry.get_model(self.status_model_name)
        return (
            status_model._default_manager.filter(pk=status)
            .values_list("type", flat=True)
            .first()
            or ""
        )

    def add_status_change_log(self, *, created: bool) -> None:
        """``crm_status_change_log.py:45-83``.

        Each row records a *period spent in* a status: ``from`` is the status held and
        ``from_date`` when it began; ``to`` and ``to_date`` are filled in when the record
        leaves it. So a transition closes the open row and opens a new one.

        **Deliberate divergence.** Upstream resolves the status type against
        ``"CRM Deal Status"`` unconditionally (``crm_status_change_log.py:46,51``) even
        though ``crm_lead.py:92`` calls it for leads, whose statuses live in
        ``CRM Lead Status``. Every lead log therefore gets an empty ``from_type`` and
        ``to_type`` upstream. We resolve against the right table per doctype. Nothing
        reads these fields today - not the frontend, not the backend - so the divergence
        is invisible, and writing the correct value costs nothing.
        """
        from frappe_core import children

        spec = children.discover_child_tables(type(self))["status_change_log"]
        rows = children.read_children(self, spec)
        now = timezone.now()
        user = get_current_user()
        to_status_type = self._status_type(self.status_id)

        payload = [
            {
                "from": getattr(row, "from"),
                "from_type": row.from_type,
                "to": getattr(row, "to"),
                "to_type": row.to_type,
                "from_date": row.from_date,
                "to_date": row.to_date,
                "duration": row.duration,
                "log_owner_id": row.log_owner_id,
            }
            for row in rows
        ]

        if not created:
            previous = getattr(self, "_loaded_status", None)
            if not payload and previous:
                # Backfill an opening row dated a minute earlier, so the record that was
                # already in a status before logging began still shows one.
                payload.append(
                    {
                        "from": previous,
                        "from_type": self._status_type(previous),
                        "to": "",
                        "to_type": "",
                        "from_date": now - timedelta(minutes=1),
                        "to_date": None,
                        "duration": None,
                        "log_owner_id": user,
                    }
                )
            if payload:
                last = payload[-1]
                last["to"] = self.status_id or ""
                last["to_type"] = to_status_type
                last["to_date"] = now
                last["log_owner_id"] = user
                if last["from_date"]:
                    last["duration"] = int((now - last["from_date"]).total_seconds())

        payload.append(
            {
                "from": self.status_id or "",
                "from_type": to_status_type,
                "to": "",
                "to_type": "",
                "from_date": now,
                "to_date": None,
                "duration": None,
                "log_owner_id": user,
            }
        )

        children.replace_children(self, "status_change_log", spec, payload)

    def sync_status_change_log(self, *, created: bool) -> None:
        """Log only when the status actually moved - upstream's ``has_value_changed``."""
        if not created and self.status_id == getattr(self, "_loaded_status", None):
            return
        self.add_status_change_log(created=created)


class OwnerAssignmentMixin(models.Model):
    """Assign the record to its owner, as ``CRM Lead`` and ``CRM Deal`` both do.

    Upstream (``crm_lead.py:86-88,94-98``, ``crm_deal.py:86-88,98-102``)::

        def validate(self):
            if not self.is_new() and self.has_value_changed("<x>_owner") and self.<x>_owner:
                self.share_with_agent(self.<x>_owner)
                self.assign_agent(self.<x>_owner)

        def after_insert(self):
            if self.<x>_owner:
                if self.<x>_owner != frappe.session.user:
                    self.share_with_agent(self.<x>_owner)
                self.assign_agent(self.<x>_owner)

    Subclasses set :attr:`owner_field`.

    Note this assigns the record to its **own owner**, who already satisfies the
    permission rule's ``<x>_owner == user`` clause (``PHASE_2_PERMISSIONS.md`` section 2).
    So the ``ToDo`` written here does not grant access - it drives the assignee chip the
    list views render from ``_assign``. The ``ToDo`` path matters for *access* when
    someone other than the owner is assigned, which happens through the phase-3
    assignment endpoints.
    """

    #: ``"lead_owner"`` or ``"deal_owner"``.
    owner_field: str = ""

    class Meta:
        abstract = True

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        # Frappe compares against the stored document in has_value_changed(); stash the
        # loaded value so the same check costs no extra query.
        instance._loaded_owner = getattr(instance, f"{cls.owner_field}_id", None)
        return instance

    def _owner_value(self):
        return getattr(self, f"{self.owner_field}_id", None)

    def assign_agent(self, agent) -> None:
        """``crm_lead.py:158-169``. Skips silently when already assigned."""
        if not agent:
            return
        if agent in assignment.get_assigned_users(self.get_doctype(), self.pk):
            return
        assignment.assign_to_user(self.get_doctype(), self.pk, agent)

    def share_with_agent(self, agent) -> None:
        """``crm_lead.py:171-201`` - **deliberate no-op seam.**

        Upstream writes ``DocShare`` rows: it adds one for the new owner and removes
        every other share on the document. We do not port that yet, because nothing in
        this port would read the result.

        Frappe folds shares into a list query as
        ``(user_permission_conditions OR shared) AND permission_query_conditions``
        (``frappe/model/db_query.py:856-865`` then ``:881``). Two consequences: sharing
        never overrides the org-hierarchy rule even upstream, and we have neither a
        ``DocShare`` model nor a user-permissions layer for it to widen. Porting it alone
        would write rows no query consults.

        To finish it: port ``DocShare`` as a tenth platform doctype, add the shared-docs
        clause to ``frappe_core.query``, then implement this method. The call sites are
        already faithful, so nothing else moves.
        """
        return None

    def sync_owner_assignment(self, *, created: bool) -> None:
        """Run the owner-change side effects. Call *after* the row exists.

        Upstream splits this across ``validate`` and ``after_insert``; both need
        ``self.name``, and on create it only exists post-insert.
        """
        owner = self._owner_value()
        if not owner:
            return

        if created:
            if owner != get_current_user():
                self.share_with_agent(owner)
            self.assign_agent(owner)
            return

        if owner != getattr(self, "_loaded_owner", None):
            self.share_with_agent(owner)
            self.assign_agent(owner)


@register_doctype("CRM Lead")
class CRMLead(StatusLifecycleMixin, OwnerAssignmentMixin, SLAFieldsMixin, BaseDocument):
    owner_field = "lead_owner"
    status_model_name = "CRM Lead Status"
    default_status = "New"

    naming_series = models.CharField(max_length=140, blank=True, default="CRM-LEAD-.YYYY.-")
    salutation = models.CharField(max_length=140, blank=True, default="")
    first_name = models.CharField(max_length=140, blank=True, default="")
    middle_name = models.CharField(max_length=140, blank=True, default="")
    last_name = models.CharField(max_length=140, blank=True, default="")
    gender = models.CharField(max_length=140, blank=True, default="")
    lead_name = models.CharField(max_length=280, blank=True, default="")
    job_title = models.CharField(max_length=140, blank=True, default="")
    # `organization` on a Lead is free text, not a Link - it becomes a CRM Organization
    # only on conversion (crm_lead.py:244-262).
    organization = models.CharField(max_length=140, blank=True, default="")

    status = models.ForeignKey(
        "crm_app.CRMLeadStatus", on_delete=models.PROTECT, related_name="leads"
    )
    email = models.CharField(max_length=140, blank=True, default="")
    website = models.CharField(max_length=280, blank=True, default="")
    mobile_no = models.CharField(max_length=140, blank=True, default="")
    phone = models.CharField(max_length=140, blank=True, default="")
    no_of_employees = models.CharField(
        max_length=20, choices=EMPLOYEE_COUNT_CHOICES, blank=True, default=""
    )
    annual_revenue = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    lead_owner = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_leads",
        db_index=True,
    )
    source = models.ForeignKey(
        "crm_app.CRMLeadSource", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    industry = models.ForeignKey(
        "crm_app.CRMIndustry", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    territory = models.ForeignKey(
        "crm_app.CRMTerritory", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    image = models.CharField(max_length=500, blank=True, default="")
    converted = models.BooleanField(default=False)
    total = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    net_total = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    facebook_lead_id = models.CharField(max_length=140, blank=True, default="")
    facebook_form_id = models.CharField(max_length=140, blank=True, default="")
    lost_reason = models.ForeignKey(
        "crm_app.CRMLostReason", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    lost_notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-modified"]
        name_strategy = NamingSeries("CRM-LEAD-.YYYY.-")

    #: Child tables with more than one possible parent, so they carry ``parent`` +
    #: ``parenttype`` instead of a FK. See frappe_core.children.
    POLYMORPHIC_CHILD_TABLES = {
        "products": "CRM Products",
        "status_change_log": "CRM Status Change Log",
        "rolling_responses": "CRM Rolling Response Time",
    }

    #: Filled in by ``validate_status`` on create, so the serializer must not demand it
    #: (frappe_core/serializers.py). Upstream's client omits it too.
    AUTO_DEFAULTED_FIELDS = ("status",)

    #: ``image`` is hidden in the JSON; get_data drops hidden columns
    #: (``crm/api/doc.py:350-352``).
    @staticmethod
    def get_hidden_fields():
        return ["image"]

    # -- lifecycle (crm_lead.py) --------------------------------------------------

    def set_full_name(self):
        """``crm_lead.py:113-122``. Mutates ``lead_name``; runs *before* set_lead_name.

        Three details an earlier revision of this port got wrong, all of them visible:
        it only fires when ``first_name`` is set, it **includes the salutation**, and it
        writes to ``self.lead_name`` rather than returning a value.
        """
        if self.first_name:
            self.lead_name = " ".join(
                part
                for part in (
                    self.salutation,
                    self.first_name,
                    self.middle_name,
                    self.last_name,
                )
                if part
            )

    def set_lead_name(self, ignore_mandatory: bool = False):
        """``crm_lead.py:123-135``. Message verbatim.

        Note the fallback order and that the email fallback uses the **local part**
        only - ``ada@example.com`` becomes ``ada``, not the whole address.
        """
        if self.lead_name:
            return
        if not self.organization and not self.email and not ignore_mandatory:
            raise ValidationError(
                "A Lead requires either a person's name or an organization's name"
            )
        if self.organization:
            self.lead_name = self.organization
        elif self.email:
            self.lead_name = self.email.split("@")[0]
        else:
            # Only reachable with ignore_mandatory, matching upstream.
            self.lead_name = "Unnamed Lead"

    def validate_email(self):
        """``crm_lead.py:140-144``. Message verbatim."""
        if self.email and self.lead_owner_id and self.email == self.lead_owner_id:
            raise ValidationError("Lead Owner cannot be same as the Lead Email Address")

    def validate_lost_reason(self):
        """``crm_lead.py:147-154``. Both messages verbatim - note they differ by one word."""
        if not self.status_id:
            return
        if getattr(self.status, "type", None) != "Lost":
            return
        if not self.lost_reason_id:
            raise ValidationError("Please specify a reason for losing the lead.")
        if self.lost_reason_id == "Other" and not self.lost_notes:
            raise ValidationError("Please specify the reason for losing the lead.")

    def run_validate(self, ignore_mandatory: bool = False):
        """``crm_lead.py:81-92`` ``validate()``, in upstream's order.

        ``set_full_name`` must run before ``set_lead_name`` - it is what populates
        ``lead_name`` for a lead that has a person's name, which then short-circuits the
        fallback chain.
        """
        self.set_full_name()
        self.set_lead_name(ignore_mandatory=ignore_mandatory)
        self.validate_email()
        self.validate_lost_reason()

    def clean(self):
        """Frappe ``validate()`` maps to ``Model.clean()`` (PHASE_1_MODELS.md section 4)."""
        self.run_validate()

    def save(self, *args, **kwargs):
        self.validate_status()
        self.run_validate(ignore_mandatory=kwargs.pop("ignore_mandatory", False))
        self.apply_sla()
        creating = self._state.adding
        status_moved = creating or self.status_id != getattr(self, "_loaded_status", None)
        result = super().save(*args, **kwargs)
        if status_moved:
            self.add_status_change_log(created=creating)
        self._loaded_status = self.status_id
        # After the insert, because assignment references self.name.
        self.sync_owner_assignment(created=creating)
        self._loaded_owner = self._owner_value()
        return result

    def convert_to_deal(self, deal: dict | None = None, **kwargs):
        """``crm_lead.py:405-406`` - delegates to :mod:`crm_app.conversion`."""
        from crm_app.conversion import convert_to_deal

        return convert_to_deal(self, deal=deal, **kwargs)

    @staticmethod
    def get_non_filterable_fields():
        """``crm_lead.py:409-410``."""
        return ["converted"]

    @staticmethod
    def default_list_data():
        """Verbatim from ``crm_lead.py:default_list_data``."""
        return {
            "columns": [
                {"label": "Full Name", "type": "Data", "key": "lead_name", "width": "12rem"},
                {"label": "Organization", "type": "Link", "key": "organization", "options": "CRM Organization", "width": "10rem"},
                {"label": "Status", "type": "Link", "options": "CRM Lead Status", "key": "status", "width": "8rem"},
                {"label": "Email", "type": "Data", "key": "email", "width": "12rem"},
                {"label": "Mobile No.", "type": "Data", "key": "mobile_no", "width": "11rem"},
                {"label": "Assigned To", "type": "Text", "key": "_assign", "width": "10rem"},
                {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
            ],
            "rows": [
                "name",
                "lead_name",
                "organization",
                "status",
                "email",
                "mobile_no",
                "lead_owner",
                "first_name",
                "sla_status",
                "response_by",
                "first_response_time",
                "first_responded_on",
                "modified",
                "_assign",
                "image",
            ],
        }


@register_doctype("CRM Deal")
class CRMDeal(StatusLifecycleMixin, OwnerAssignmentMixin, SLAFieldsMixin, BaseDocument):
    owner_field = "deal_owner"
    status_model_name = "CRM Deal Status"
    default_status = "Qualification"

    naming_series = models.CharField(max_length=140, blank=True, default="CRM-DEAL-.YYYY.-")
    organization = models.ForeignKey(
        CRMOrganization, on_delete=models.PROTECT, null=True, blank=True, related_name="deals"
    )
    organization_name = models.CharField(max_length=140, blank=True, default="")
    probability = models.FloatField(null=True, blank=True)
    annual_revenue = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    website = models.CharField(max_length=280, blank=True, default="")
    next_step = models.CharField(max_length=280, blank=True, default="")
    lead = models.ForeignKey(
        CRMLead, on_delete=models.SET_NULL, null=True, blank=True, related_name="deals"
    )
    deal_owner = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_deals",
        db_index=True,
    )
    email = models.CharField(max_length=140, blank=True, default="")
    mobile_no = models.CharField(max_length=140, blank=True, default="")
    phone = models.CharField(max_length=140, blank=True, default="")
    status = models.ForeignKey(
        "crm_app.CRMDealStatus", on_delete=models.PROTECT, related_name="deals"
    )
    territory = models.ForeignKey(
        "crm_app.CRMTerritory", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    source = models.ForeignKey(
        "crm_app.CRMLeadSource", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    industry = models.ForeignKey(
        "crm_app.CRMIndustry", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    no_of_employees = models.CharField(
        max_length=20, choices=EMPLOYEE_COUNT_CHOICES, blank=True, default=""
    )
    job_title = models.CharField(max_length=140, blank=True, default="")
    lead_name = models.CharField(max_length=280, blank=True, default="")
    salutation = models.CharField(max_length=140, blank=True, default="")
    first_name = models.CharField(max_length=140, blank=True, default="")
    last_name = models.CharField(max_length=140, blank=True, default="")
    gender = models.CharField(max_length=140, blank=True, default="")
    contact = models.ForeignKey(
        "frappe_platform.Contact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_for_deals",
    )
    currency = models.CharField(max_length=140, blank=True, default="")
    total = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    net_total = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    deal_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    lost_reason = models.ForeignKey(
        "crm_app.CRMLostReason", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    lost_notes = models.TextField(blank=True, default="")
    exchange_rate = models.FloatField(default=1)
    expected_deal_value = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    expected_closure_date = models.DateField(null=True, blank=True)
    closed_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-modified"]
        name_strategy = NamingSeries("CRM-DEAL-.YYYY.-")

    #: ``contacts`` is a real FK (single parent) and is discovered automatically; these
    #: three are shared with CRM Lead and so carry ``parent`` + ``parenttype``.
    POLYMORPHIC_CHILD_TABLES = {
        "products": "CRM Products",
        "status_change_log": "CRM Status Change Log",
        "rolling_responses": "CRM Rolling Response Time",
    }

    #: Filled in by ``validate_status`` on create - see the note on ``CRMLead``.
    AUTO_DEFAULTED_FIELDS = ("status",)

    # -- lifecycle (crm_deal.py) --------------------------------------------------

    def validate_lost_reason(self):
        """``crm_deal.py:256-263``. Messages verbatim - "deal", not "lead"."""
        if not self.status_id:
            return
        if getattr(self.status, "type", None) != "Lost":
            return
        if not self.lost_reason_id:
            raise ValidationError("Please specify a reason for losing the deal.")
        if self.lost_reason_id == "Other" and not self.lost_notes:
            raise ValidationError("Please specify the reason for losing the deal.")

    def validate_forecasting(self, forecasting_enabled: bool | None = None):
        """``crm_deal.py:249-253``.

        Upstream reads ``FCRM Settings.enable_forecasting`` inline. We now do the same
        when the caller passes nothing - phase 1 made it a required parameter, which left
        the rule silently inert because nothing passed it. The override is kept so a test
        can exercise both branches without touching the singleton.

        Upstream raises ``MandatoryError``, not ``ValidationError`` - the frontend
        branches on ``exc_type == 'MandatoryError'`` (``src/data/document.js:61``), so the
        class matters.
        """
        if forecasting_enabled is None:
            forecasting_enabled = self._settings_flag("enable_forecasting")
        if not forecasting_enabled:
            return
        if not self.expected_deal_value:
            raise MandatoryError("Expected deal value is required.")
        if not self.expected_closure_date:
            raise MandatoryError("Expected closure date is required.")

    @staticmethod
    def _settings_flag(name: str) -> bool:
        from crm_app.models.metadata import FCRMSettings

        return bool(getattr(FCRMSettings.load(), name, False))

    def update_closed_date(self) -> None:
        """``crm_deal.py:220-225``.

        Note this compares the status **name** to the literal ``"Won"``, while
        :meth:`save` separately sets ``closed_date`` when the status *type* is ``Won``.
        Both are upstream, and they are not equivalent: rename the Won status and only
        the type check still fires. Ported as-is - the type check is the one that
        actually covers the case, and this one is harmless.
        """
        if self.status_id == "Won" and not self.closed_date:
            self.closed_date = timezone.now().date()

    def update_default_probability(self) -> None:
        """``crm_deal.py:227-232`` - inherit the status's probability when unset."""
        if self.probability:
            return
        self.probability = (
            registry.get_model("CRM Deal Status")
            ._default_manager.filter(pk=self.status_id)
            .values_list("probability", flat=True)
            .first()
            or 0
        )

    def update_expected_deal_value(self) -> None:
        """``crm_deal.py:234-243``.

        The guard reads oddly and is faithful: upstream requires ``expected_deal_value``
        to be **already set** before it will overwrite it from the product total. So this
        never populates an empty value - it only keeps a non-empty one in step. A deal
        with products but no expected value is left alone, and then
        ``validate_forecasting`` raises for it when forecasting is on. Reproduced rather
        than corrected, because the behaviour is user-visible either way.
        """
        if not self._settings_flag("auto_update_expected_deal_value"):
            return
        total = self.net_total or self.total
        if total and self.expected_deal_value:
            self.expected_deal_value = total

    def validate_forecasting_fields(self) -> None:
        """``crm_deal.py:245-253`` - the three updates, then the mandatory checks."""
        self.update_closed_date()
        self.update_default_probability()
        self.update_expected_deal_value()
        self.validate_forecasting()

    def set_primary_contact(self, contact=None) -> None:
        """``crm_deal.py:114-125``.

        With exactly one contact and no explicit choice, that contact becomes primary.
        Naming an explicit contact makes it primary and demotes the rest.
        """
        rows = list(self.contacts.all())
        if not rows:
            return

        if not contact and len(rows) == 1:
            rows[0].is_primary = True
            rows[0].save(update_fields=["is_primary"])
            return

        if contact:
            for row in rows:
                row.is_primary = row.contact_id == contact
                row.save(update_fields=["is_primary"])

    def set_primary_email_mobile_no(self) -> None:
        """``crm_deal.py:127-149`` - denormalise the primary contact's details.

        With no contacts, or none flagged primary, the three fields are **cleared**;
        upstream does the same rather than leaving stale values behind.
        """
        rows = list(self.contacts.all())
        if not rows:
            self.email = self.mobile_no = self.phone = ""
            return

        primaries = [row for row in rows if row.is_primary]
        if len(primaries) > 1:
            raise ValidationError("Only one Contact can be set as primary.")

        if not primaries:
            self.email = self.mobile_no = self.phone = ""
            return

        primary = primaries[0]
        self.email = (primary.email or "").strip()
        self.mobile_no = (primary.mobile_no or "").strip()
        self.phone = (primary.phone or "").strip()

    def clean(self):
        self.validate_lost_reason()

    def save(self, *args, **kwargs):
        self.validate_status()
        # Child rows only exist once the parent does, so the contact-derived fields are
        # resolved post-insert on create (see below) and inline on update.
        if not self._state.adding:
            self.set_primary_contact()
            self.set_primary_email_mobile_no()
        self.validate_forecasting_fields()
        self.validate_lost_reason()
        self.apply_sla()
        creating = self._state.adding
        status_moved = creating or self.status_id != getattr(self, "_loaded_status", None)
        won = status_moved and getattr(self.status, "type", None) == "Won"
        if won:
            # crm_deal.py:91-93 - the *type* check, distinct from update_closed_date's
            # name check, and it overwrites rather than only filling a blank.
            self.closed_date = timezone.now().date()
        result = super().save(*args, **kwargs)
        if status_moved:
            self.add_status_change_log(created=creating)
        self._loaded_status = self.status_id
        self.sync_owner_assignment(created=creating)
        self._loaded_owner = self._owner_value()
        return result

    def sync_contact_fields(self) -> None:
        """Re-derive the contact-linked fields and persist them.

        Callers that add or change child contacts run this; ``save()`` cannot, because on
        create the rows do not exist until the parent is inserted.
        """
        self.set_primary_contact()
        self.set_primary_email_mobile_no()
        type(self)._default_manager.filter(pk=self.pk).update(
            email=self.email, mobile_no=self.mobile_no, phone=self.phone
        )

    @staticmethod
    def default_list_data():
        return {
            "columns": [
                {"label": "Organization", "type": "Link", "key": "organization", "options": "CRM Organization", "width": "11rem"},
                {"label": "Amount", "type": "Currency", "key": "annual_revenue", "width": "9rem"},
                {"label": "Status", "type": "Link", "options": "CRM Deal Status", "key": "status", "width": "10rem"},
                {"label": "Email", "type": "Data", "key": "email", "width": "12rem"},
                {"label": "Mobile No.", "type": "Data", "key": "mobile_no", "width": "11rem"},
                {"label": "Assigned To", "type": "Text", "key": "_assign", "width": "10rem"},
                {"label": "Last Modified", "type": "Datetime", "key": "modified", "width": "8rem"},
            ],
            "rows": [
                "name",
                "organization",
                "annual_revenue",
                "currency",
                "status",
                "email",
                "mobile_no",
                "deal_owner",
                "sla_status",
                "response_by",
                "first_response_time",
                "first_responded_on",
                "modified",
                "_assign",
            ],
        }


@register_doctype("CRM Contacts", is_child_table=True)
class CRMContacts(BaseDocument):
    """Child of CRM Deal only - ``crm/api/contact.py:38`` filters
    ``parenttype="CRM Deal"`` - so unlike CRM Products this one takes a real FK.
    """

    parent_deal = models.ForeignKey(
        CRMDeal, on_delete=models.CASCADE, related_name="contacts", null=True, blank=True
    )
    parenttype = models.CharField(max_length=140, default="CRM Deal")
    parentfield = models.CharField(max_length=140, default="contacts")

    #: ``fetch_from`` in ``crm_contacts.json`` - these five mirror the linked Contact
    #: on every save. Without them, converting a lead produced a deal with a contact
    #: attached but no email or phone, because the child row was never populated.
    FETCH_FROM = {
        "full_name": ("contact", "full_name"),
        "email": ("contact", "email_id"),
        "mobile_no": ("contact", "mobile_no"),
        "phone": ("contact", "phone"),
        "gender": ("contact", "gender"),
    }

    contact = models.ForeignKey(
        "frappe_platform.Contact", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    full_name = models.CharField(max_length=280, blank=True, default="")
    email = models.CharField(max_length=140, blank=True, default="")
    mobile_no = models.CharField(max_length=140, blank=True, default="")
    phone = models.CharField(max_length=140, blank=True, default="")
    gender = models.CharField(max_length=140, blank=True, default="")
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()


@register_doctype("CRM Task")
class CRMTask(AutoIncrementDocument):
    """One of the three genuinely integer-PK doctypes (``autoname=autoincrement``)."""

    title = models.CharField(max_length=280)
    description = models.TextField(blank=True, default="")
    priority = models.CharField(
        max_length=20, choices=TASK_PRIORITY_CHOICES, blank=True, default=""
    )
    status = models.CharField(
        max_length=20, choices=TASK_STATUS_CHOICES, blank=True, default=""
    )
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crm_tasks",
    )
    # Link to DocType + Dynamic Link - the pair is Frappe's generic reference.
    reference_doctype = models.CharField(max_length=140, blank=True, default="", db_index=True)
    reference_docname = models.CharField(max_length=140, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["-modified"]
        indexes = [
            models.Index(
                fields=["reference_doctype", "reference_docname"], name="crm_task_reference_idx"
            ),
        ]


@register_doctype("FCRM Note")
class FCRMNote(BaseDocument):
    """No ``autoname`` in the JSON - Frappe's default for that is ``hash``."""

    title = models.CharField(max_length=280)
    content = models.TextField(blank=True, default="")
    reference_doctype = models.CharField(
        max_length=140, blank=True, default="CRM Lead", db_index=True
    )
    reference_docname = models.CharField(max_length=140, blank=True, default="", db_index=True)

    class Meta:
        ordering = ["-modified"]
        name_strategy = Hash()
        indexes = [
            models.Index(
                fields=["reference_doctype", "reference_docname"], name="fcrm_note_reference_idx"
            ),
        ]


__all__ = [
    "CRMOrganization",
    "CRMLead",
    "CRMDeal",
    "CRMContacts",
    "CRMTask",
    "FCRMNote",
]
