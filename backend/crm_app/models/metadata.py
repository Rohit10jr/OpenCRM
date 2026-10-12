"""Cluster 6 - UI metadata, notifications, org and settings.

PHASE_1_MODELS.md section 5: "Models only - behaviour is phase 4."

Two models here are load-bearing for other phases:

* ``FCRM Settings.enable_sales_hierarchy`` is read by the phase-2 permission engine
  (PHASE_2_PERMISSIONS.md section 2, step 3).
* ``CRM Sales Hierarchy`` is the nested-set tree that engine walks.
"""

from django.db import models

from frappe_core.models import AutoIncrementDocument, BaseDocument
from frappe_core.naming import FieldValue, Format, Hash, Prompt
from frappe_core.registry import register_doctype
from crm_app import realtime
from crm_app.models.telephony import SingletonMixin

VIEW_TYPE_CHOICES = [("list", "list"), ("group_by", "group_by"), ("kanban", "kanban")]
LAYOUT_TYPE_CHOICES = [
    (c, c)
    for c in ("Quick Entry", "Side Panel", "Data Fields", "Grid Row", "Required Fields")
]

#: ``fcrm_settings.service_provider`` - four fixed FX providers.
SERVICE_PROVIDER_CHOICES = [
    (c, c)
    for c in (
        "frankfurter.app",
        "fawazahmed-exchange-api",
        "exchangerate.host",
        "exchangerate-api",
    )
]
SCRIPT_VIEW_CHOICES = [("Form", "Form"), ("List", "List")]
DROPDOWN_TYPE_CHOICES = [("Route", "Route"), ("Separator", "Separator")]
NOTIFICATION_TYPE_CHOICES = [
    (c, c) for c in ("Mention", "Task", "Assignment", "WhatsApp")
]
INVITATION_ROLE_CHOICES = [
    ("", ""),
    ("Sales User", "Sales User"),
    ("Sales Manager", "Sales Manager"),
    ("System Manager", "System Manager"),
]
INVITATION_STATUS_CHOICES = [
    ("", ""),
    ("Pending", "Pending"),
    ("Accepted", "Accepted"),
    ("Expired", "Expired"),
]
GLOBAL_SETTING_TYPE_CHOICES = [
    ("Quick Filters", "Quick Filters"),
    ("Sidebar Items", "Sidebar Items"),
]
TIMELINE_TIMESTAMP_CHOICES = [("Relative", "Relative"), ("Exact", "Exact")]
TIMELINE_SORT_CHOICES = [("Oldest First", "Oldest First"), ("Newest First", "Newest First")]


@register_doctype("CRM View Settings")
class CRMViewSettings(AutoIncrementDocument):
    """Per-user saved views. One of the three integer-PK doctypes.

    Phase 4 turns this into behaviour; ``get_data``'s lookup key is
    ``{dt, type: view_type or "list", is_standard: 1, user}``
    (``crm/api/doc.py:324-331``), which is why all four are indexed together.

    ``Code`` fields hold JSON strings upstream. Ported as ``TextField`` to keep the
    stored representation byte-identical - phase 4 parses them.
    """

    dt = models.CharField(max_length=140, db_index=True)
    user = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="view_settings",
    )
    label = models.CharField(max_length=140, blank=True, default="")
    type = models.CharField(max_length=20, choices=VIEW_TYPE_CHOICES, default="list")
    columns = models.TextField(blank=True, default="")
    rows = models.TextField(blank=True, default="")
    filters = models.TextField(blank=True, default="")
    order_by = models.TextField(blank=True, default="")
    group_by_field = models.CharField(max_length=140, blank=True, default="")
    column_field = models.CharField(max_length=140, blank=True, default="")
    kanban_columns = models.TextField(blank=True, default="")
    kanban_fields = models.TextField(blank=True, default="")
    title_field = models.CharField(max_length=140, blank=True, default="")
    route_name = models.CharField(max_length=140, blank=True, default="")
    icon = models.CharField(max_length=140, blank=True, default="")
    pinned = models.BooleanField(default=False)
    public = models.BooleanField(default=False)
    load_default_columns = models.BooleanField(default=False)
    is_standard = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-modified"]
        indexes = [
            models.Index(
                fields=["dt", "type", "is_standard", "user"], name="view_settings_lookup_idx"
            ),
        ]


@register_doctype("CRM Fields Layout")
class CRMFieldsLayout(BaseDocument):
    """``autoname=format:{dt}-{type}`` - the only doctype using that strategy.

    This is where the layout fieldtypes deliberately skipped in phase 1 come back, as
    layout *data* rather than columns (PHASE_4_METADATA.md section 2).
    """

    dt = models.CharField(max_length=140, db_index=True)
    type = models.CharField(max_length=40, choices=LAYOUT_TYPE_CHOICES, blank=True, default="")
    layout = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        name_strategy = Format("{dt}-{type}")


@register_doctype("CRM Form Script")
class CRMFormScript(BaseDocument):
    """``autoname=prompt`` - the only doctype where the client supplies ``name``.

    ``script`` is user-authored JavaScript executed **client-side**. It is stored and
    served, never evaluated server-side (PHASE_4_METADATA.md section 2). Write access is
    admin-only upstream; phase 3 must preserve that.
    """

    dt = models.CharField(max_length=140, db_index=True)
    view = models.CharField(max_length=20, choices=SCRIPT_VIEW_CHOICES, default="Form")
    script = models.TextField(blank=True, default="")
    enabled = models.BooleanField(default=False)
    is_standard = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        name_strategy = Prompt()


@register_doctype("CRM Dashboard")
class CRMDashboard(BaseDocument):
    layout = models.TextField(blank=True, default="[]")
    title = models.CharField(max_length=140, blank=True, default="")
    user = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="dashboards",
    )
    private = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        name_strategy = FieldValue("title", label="Name")


@register_doctype("CRM Notification")
class CRMNotification(BaseDocument):
    """One of the three doctypes with a row-level permission rule.

    PHASE_2_PERMISSIONS.md section 1: it uses its **own** doctype-local rule
    (``crm_notification.py``), not the org-hierarchy one. Phase 2 registers it.
    """

    type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    from_user = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sent_notifications",
    )
    to_user = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )
    read = models.BooleanField(default=False)
    comment = models.ForeignKey(
        "frappe_platform.Comment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    message = models.TextField(blank=True, default="")
    notification_text = models.TextField(blank=True, default="")
    reference_doctype = models.CharField(max_length=140, blank=True, default="")
    reference_name = models.CharField(max_length=140, blank=True, default="")
    notification_type_doctype = models.CharField(max_length=140, blank=True, default="")
    notification_type_doc = models.CharField(max_length=140, blank=True, default="")

    class Meta:
        ordering = ["-creation"]
        name_strategy = Hash()

    def on_update(self):
        """``crm_notification.py:30-32`` - filled in by phase 6.

        Note the guard is upstream's: no ``to_user``, no event. The column is NOT NULL
        here, so it cannot fire on a saved row, but the check stays because deleting it
        would be a silent divergence from the source rather than a visible one.

        The publish is deliberately unguarded by any try/except of its own -
        ``realtime.publish`` never raises, and never returning False here would be
        indistinguishable from succeeding.
        """
        if self.to_user_id:
            realtime.publish("crm_notification", user=self.to_user_id)

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        self.on_update()
        return result


@register_doctype("CRM Invitation")
class CRMInvitation(BaseDocument):
    email = models.CharField(max_length=140)
    role = models.CharField(max_length=40, choices=INVITATION_ROLE_CHOICES)
    key = models.CharField(max_length=140, blank=True, default="", db_index=True)
    invited_by = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_invitations",
    )
    status = models.CharField(
        max_length=20, choices=INVITATION_STATUS_CHOICES, blank=True, default=""
    )
    email_sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    #: `key` is a **bearer token**: whoever holds it redeems the invitation, and with it
    #: the role the invitation grants. The only thing that ever needs it is the email in
    #: `tasks.py`, which reads the attribute directly. Nothing should receive it over the
    #: wire - `InviteUserPage.vue`, the sole consumer, asks for `name`, `email` and `role`.
    #:
    #: Upstream leaves it a plain `Data` field readable by every Sales User, which is what
    #: makes `accept_invitation` redeemable by the wrong person (bug #21).
    SENSITIVE_FIELDS = ("key",)

    class Meta:
        ordering = ["-creation"]
        name_strategy = Hash()


@register_doctype("CRM Sales Hierarchy")
class CRMSalesHierarchy(BaseDocument):
    """The nested-set tree the phase-2 permission engine walks.

    PHASE_2_PERMISSIONS.md section 3: subtree membership is
    ``Member.lft >= Mgr.lft AND Member.lft <= Mgr.rgt``, and the lookup runs on **every**
    list request for leads and deals.

    Phase 1 ports the schema, including ``lft``/``rgt``. **Phase 2 owns maintaining them
    and the subtree query**, and should decide there between treebeard and the
    nested-set columns - the spec calls for treebeard, but that choice belongs with the
    code that depends on its performance. ``lft`` and ``rgt`` are indexed for the
    range scan either way.
    """
    #: ``fetch_from`` in ``crm_sales_hierarchy.json``.
    FETCH_FROM = {"full_name": ("user", "full_name")}


    full_name = models.CharField(max_length=280, blank=True, default="")
    user = models.ForeignKey(
        "frappe_platform.User",
        on_delete=models.CASCADE,
        related_name="hierarchy_nodes",
        db_index=True,
    )
    reports_to = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reports"
    )
    old_parent = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    lft = models.IntegerField(null=True, blank=True, db_index=True)
    rgt = models.IntegerField(null=True, blank=True, db_index=True)
    is_group = models.BooleanField(default=False)

    class Meta:
        ordering = ["lft"]
        name_strategy = Hash()


@register_doctype("CRM Global Settings")
class CRMGlobalSettings(BaseDocument):
    """Not a singleton despite the name - one row per (dt, type).

    ``crm/api/doc.py:168`` looks it up as
    ``{"dt": doctype, "type": "Quick Filters"}``.
    """

    dt = models.CharField(max_length=140, default="DocType", db_index=True)
    type = models.CharField(max_length=40, choices=GLOBAL_SETTING_TYPE_CHOICES)
    json = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        name_strategy = Hash()
        indexes = [
            models.Index(fields=["dt", "type"], name="global_settings_lookup_idx"),
        ]


@register_doctype("FCRM Settings", is_single=True)
class FCRMSettings(SingletonMixin, BaseDocument):
    """``"issingle": 1``.

    ``enable_sales_hierarchy`` is read by the phase-2 permission engine
    (PHASE_2_PERMISSIONS.md section 2, step 3) and ``enable_forecasting`` by
    ``CRMDeal.validate_forecasting`` (``crm_deal.py:249``).
    """

    brand_name = models.CharField(max_length=140, blank=True, default="")
    brand_logo = models.CharField(max_length=500, blank=True, default="")
    favicon = models.CharField(max_length=500, blank=True, default="")
    enable_forecasting = models.BooleanField(default=False)
    enable_sales_hierarchy = models.BooleanField(default=False)
    currency = models.CharField(max_length=140, blank=True, default="")
    service_provider = models.CharField(
        max_length=40, choices=SERVICE_PROVIDER_CHOICES, blank=True, default="frankfurter.app"
    )
    # An FX-provider credential, declared `Data` rather than `Password` in the JSON and
    # carrying no `permlevel`. Phase 1 flagged it and declined to hide it, because the
    # settings screen reads it back and `SENSITIVE_FIELDS` is all-or-nothing: hiding it
    # would have broken that screen to make an improvement the source does not make.
    #
    # That was the right call with the tools of the time. `RESTRICTED_FIELDS` is the tool
    # it needed - see the declaration below.
    access_key = models.CharField(max_length=280, blank=True, default="")
    auto_update_expected_deal_value = models.BooleanField(default=True)
    update_timestamp_on_new_communication = models.BooleanField(default=True)
    auto_mark_replied_on_response = models.BooleanField(default=False)
    auto_reopen_on_new_communication = models.BooleanField(default=False)
    crm_timeline_timestamp_format = models.CharField(
        max_length=20, choices=TIMELINE_TIMESTAMP_CHOICES, default="Relative"
    )
    crm_timeline_sort_order = models.CharField(
        max_length=20, choices=TIMELINE_SORT_CHOICES, default="Oldest First"
    )
    persona_captured = models.BooleanField(default=False)

    #: **Stricter than upstream, and the one place in A4 where that matters.**
    #:
    #: This record is read by *every* screen in the product - `stores/settings.js` loads
    #: it and the activity timeline takes `crm_timeline_timestamp_format` from it - so it
    #: is world-readable by necessity, and upstream agrees (`fcrm_settings.json` grants
    #: Sales User `read: 1`). The exchange-rate provider credential is sitting on it in
    #: the clear, with no `permlevel`.
    #:
    #: Upstream's own authors used `permlevel: 1` on `CRM Twilio Settings.api_key` for
    #: exactly this, so the omission reads as an oversight rather than a decision -
    #: recorded as upstream bug #20. Managers still see it, which is all the settings
    #: screen needs.
    RESTRICTED_FIELDS = ("access_key",)

    @classmethod
    def load(cls):
        """The single row, created with its standard user-menu items on first use, which
        is how upstream's install leaves it (FINDINGS.md 42)."""
        obj, created = cls._default_manager.get_or_create(pk=cls.singleton_name())
        if created:
            add_standard_dropdown_items(obj)
        return obj

    class Meta:
        verbose_name = "FCRM Settings"


@register_doctype("CRM Dropdown Item", is_child_table=True)
class CRMDropdownItem(BaseDocument):
    """Child of FCRM Settings only."""

    parent_settings = models.ForeignKey(
        FCRMSettings, on_delete=models.CASCADE, related_name="dropdown_items"
    )
    parenttype = models.CharField(max_length=140, default="FCRM Settings")
    parentfield = models.CharField(max_length=140, default="dropdown_items")

    # `name1` really is the fieldname upstream - `name` is taken by the PK.
    name1 = models.CharField(max_length=140, blank=True, default="")
    label = models.CharField(max_length=140, blank=True, default="")
    type = models.CharField(max_length=20, choices=DROPDOWN_TYPE_CHOICES, blank=True, default="")
    route = models.CharField(max_length=280, blank=True, default="")
    icon = models.TextField(blank=True, default="")
    hidden = models.BooleanField(default=False)
    is_standard = models.BooleanField(default=False)
    open_in_new_window = models.BooleanField(default=True)

    class Meta:
        ordering = ["idx"]
        name_strategy = Hash()


#: ``crm/hooks.py:314-357`` ``standard_dropdown_items``, verbatim. The user menu at the
#: top of the sidebar (``UserDropdown.vue``) is built from FCRM Settings' dropdown_items
#: rows and shows nothing without them: no Settings, no About, no Log out. Upstream
#: writes these at install (``crm/install.py:530 add_standard_dropdown_items``) and
#: re-syncs them after every migrate; the port never seeded them (FINDINGS.md 42).
STANDARD_DROPDOWN_ITEMS = (
    {"name1": "app_selector", "label": "Apps", "type": "Route", "route": "#", "is_standard": True},
    {
        "name1": "settings",
        "label": "Settings",
        "type": "Route",
        "icon": "settings",
        "route": "#",
        "is_standard": True,
    },
    {
        "name1": "login_to_fc",
        "label": "Login to Frappe Cloud",
        "type": "Route",
        "route": "#",
        "is_standard": True,
    },
    {"name1": "about", "label": "About", "type": "Route", "icon": "info", "route": "#", "is_standard": True},
    {"name1": "separator", "label": "", "type": "Separator", "is_standard": True},
    {
        "name1": "logout",
        "label": "Log out",
        "type": "Route",
        "icon": "log-out",
        "route": "#",
        "is_standard": True,
    },
)


#: What ``force`` puts back on a standard row. ``hidden`` and ``open_in_new_window`` are
#: left as the administrator set them: hiding "Login to Frappe Cloud" is a choice, not
#: damage.
_RESTORED_DROPDOWN_FIELDS = ("label", "type", "route", "icon")


def add_standard_dropdown_items(settings: FCRMSettings, force: bool = False) -> int:
    """``crm/install.py:530-542``: seed the standard items, unless the row has any.

    Returns the number of rows written. Upstream appends them through the document, so
    each child row is inserted with the session user as its owner and ``idx`` in hook
    order; the same here, through ``BaseDocument.save``. ``FCRMSettings.load`` calls
    this for a row it creates; migration ``crm_app/0010`` covered the rows that existed
    before it.

    ``force`` restores the standard rows by their Name - Label, Type, Route and Icon back
    to what the app ships, a missing one re-added at the end - and leaves custom rows
    alone. The Home Actions grid lets a standard row's Type be switched to Separator,
    and done to Settings that removes the only way into Settings (FINDINGS.md 78,
    upstream bug 47). Upstream's function returns early while any row exists; its way
    back is Desk, which this port does not have.
    """
    rows = settings.dropdown_items
    if not rows.exists():
        for idx, item in enumerate(STANDARD_DROPDOWN_ITEMS, start=1):
            CRMDropdownItem(parent_settings=settings, idx=idx, **item).save()
        return len(STANDARD_DROPDOWN_ITEMS)
    if not force:
        return 0

    written = 0
    next_idx = (rows.aggregate(models.Max("idx"))["idx__max"] or 0) + 1
    for item in STANDARD_DROPDOWN_ITEMS:
        shipped = {field: item.get(field, "") for field in _RESTORED_DROPDOWN_FIELDS}
        row = rows.filter(name1=item["name1"]).first()
        if row is None:
            CRMDropdownItem(
                parent_settings=settings, idx=next_idx, name1=item["name1"], is_standard=True, **shipped
            ).save()
            next_idx += 1
            written += 1
            continue
        if all(getattr(row, field) == value for field, value in shipped.items()) and row.is_standard:
            continue
        for field, value in shipped.items():
            setattr(row, field, value)
        row.is_standard = True
        row.save()
        written += 1
    return written


__all__ = [
    "CRMViewSettings",
    "CRMFieldsLayout",
    "CRMFormScript",
    "CRMDashboard",
    "CRMNotification",
    "CRMInvitation",
    "CRMSalesHierarchy",
    "CRMGlobalSettings",
    "FCRMSettings",
    "CRMDropdownItem",
]
