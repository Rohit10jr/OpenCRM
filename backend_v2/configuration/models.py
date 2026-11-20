"""CONFIGURATION's documents (specs/CONFIGURATION.md section 4.2).

Ported from `backend/frappe_platform/models.py:1616-1839`.
"""

from django.conf import settings
from django.db import IntegrityError, models, transaction

from core.models import BaseDocument, SingletonDocument
from core.naming import FieldValue, Hash

SYSTEM_DATE_FORMATS = (
    "yyyy-mm-dd",
    "dd-mm-yyyy",
    "dd/mm/yyyy",
    "dd.mm.yyyy",
    "mm/dd/yyyy",
    "mm-dd-yyyy",
)
SYSTEM_TIME_FORMATS = ("HH:mm:ss", "HH:mm")
SYSTEM_FLOAT_PRECISIONS = ("", "2", "3", "4", "5", "6", "7", "8", "9")
SYSTEM_CURRENCY_PRECISIONS = ("", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9")
SYSTEM_ROUNDING_METHODS = (
    "Banker's Rounding (legacy)",
    "Banker's Rounding",
    "Commercial Rounding",
)
CURRENCY_NUMBER_FORMATS = (
    "#,###.##",
    "#.###,##",
    "# ###.##",
    "# ###,##",
    "#'###.##",
    "#, ###.##",
    "#,##,###.##",
    "#,###.###",
    "#.###",
    "#,###",
)

#: The fields the boot call answers as `sysdefaults`, in this order.
SYSDEFAULT_FIELDS = (
    "date_format",
    "time_format",
    "number_format",
    "float_precision",
    "currency_precision",
    "currency",
    "rounding_method",
)


def _choices(values):
    return [(value, value) for value in values]


def sysdefaults_from_environment() -> dict[str, str]:
    """`settings.FRAPPE_SYSDEFAULTS`, limited to the row's fields."""
    configured = getattr(settings, "FRAPPE_SYSDEFAULTS", {}) or {}
    return {field: configured[field] for field in SYSDEFAULT_FIELDS if field in configured}


#: `frappe/geo/doctype/currency/currency.py:9`: the currencies a new site has enabled.
DEFAULT_ENABLED_CURRENCIES = ("INR", "USD", "GBP", "EUR", "AED", "AUD", "JPY", "CNY", "CHF")


class Country(BaseDocument):
    """Frappe's `Country`, the Link target of an address's country. Everyone reads it;
    System Manager or Administrator writes it (old `platform_docs.py:458-466`)."""

    DOCTYPE = "Country"
    NAME_STRATEGY = FieldValue("country_name", label="Country Name")

    country_name = models.CharField("Country Name", max_length=140, unique=True)
    date_format = models.CharField("Date Format", max_length=140, blank=True, default="")
    time_format = models.CharField("Time format", max_length=140, blank=True, default="")
    time_zones = models.TextField("Time Zones", blank=True, default="")
    code = models.CharField("Code", max_length=140, blank=True, default="")

    class Meta(BaseDocument.Meta):
        ordering = ["name"]


class Language(BaseDocument):
    """Frappe's `Language`, the Link target of `User.language`, named after its code. The
    picker shows and searches the name and offers enabled rows only. Everyone reads it;
    System Manager or Administrator writes it (old `platform_docs.py:484-496`)."""

    DOCTYPE = "Language"
    NAME_STRATEGY = FieldValue("language_code", label="Language Code")
    SEARCH_FIELD = "language_name"
    SHOW_TITLE_FIELD_IN_LINK = True

    language_code = models.CharField("Language Code", max_length=140, unique=True)
    language_name = models.CharField("Language Name", max_length=140)
    flag = models.CharField("Flag", max_length=140, blank=True, default="")
    based_on = models.CharField("Based On", max_length=140, blank=True, default="")
    enabled = models.BooleanField("Enabled", default=False)

    class Meta(BaseDocument.Meta):
        ordering = ["name"]


class Currency(BaseDocument):
    """Frappe's `Currency`, named after its code; the Link target of System Settings'
    `currency` and, later, of a deal's, an organization's and FCRM Settings'. Nine are
    enabled on a new site; the picker offers enabled rows only (old
    `frappe_platform/models.py:1691-1726`)."""

    DOCTYPE = "Currency"
    NAME_STRATEGY = FieldValue("currency_name", label="Currency Name")

    currency_name = models.CharField("Currency Name", max_length=140, unique=True)
    enabled = models.BooleanField("Enabled", default=False)
    fraction = models.CharField("Fraction", max_length=140, blank=True, default="")
    fraction_units = models.IntegerField("Fraction Units", default=0)
    smallest_currency_fraction_value = models.DecimalField(
        "Smallest Currency Fraction Value",
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
    )
    symbol = models.CharField("Symbol", max_length=140, blank=True, default="")
    number_format = models.CharField(
        "Number Format",
        max_length=140,
        blank=True,
        default="",
        choices=_choices(CURRENCY_NUMBER_FORMATS),
    )
    symbol_on_right = models.BooleanField(
        "Show Currency Symbol on Right Side", default=False
    )

    class Meta(BaseDocument.Meta):
        ordering = ["name"]


class SystemSettings(SingletonDocument):
    """Frappe's `System Settings` single, the seven fields the CRM reads.

    The Defaults page edits six of them; all seven reach the browser as the boot call's
    `sysdefaults`. The row is written by this app's data migration from
    `FRAPPE_SYSDEFAULTS`, and written again by `load_or_create` if it is ever missing.
    """

    DOCTYPE = "System Settings"
    #: A text column upstream declares as a Link: an unknown currency is refused (417).
    TEXT_LINK_FIELDS = {"currency": ("configuration.Currency", "Currency")}

    date_format = models.CharField(
        "Date Format", max_length=140, choices=_choices(SYSTEM_DATE_FORMATS)
    )
    time_format = models.CharField(
        "Time Format",
        max_length=140,
        choices=_choices(SYSTEM_TIME_FORMATS),
        default="HH:mm:ss",
    )
    number_format = models.CharField(
        "Number Format", max_length=140, choices=_choices(CURRENCY_NUMBER_FORMATS)
    )
    float_precision = models.CharField(
        "Float Precision",
        max_length=140,
        blank=True,
        default="",
        choices=_choices(SYSTEM_FLOAT_PRECISIONS),
    )
    currency_precision = models.CharField(
        "Currency Precision",
        max_length=140,
        blank=True,
        default="",
        choices=_choices(SYSTEM_CURRENCY_PRECISIONS),
        help_text="If not set, the currency precision will depend on number format",
    )
    currency = models.CharField(
        "Currency",
        max_length=140,
        blank=True,
        default="",
        help_text="Default display currency",
    )
    rounding_method = models.CharField(
        "Rounding Method",
        max_length=140,
        choices=_choices(SYSTEM_ROUNDING_METHODS),
        default="Banker's Rounding (legacy)",
    )

    class Meta(SingletonDocument.Meta):
        verbose_name = "System Settings"

    @classmethod
    def load_or_create(cls):
        """The row, written from the environment's formats if it is missing.

        The boot call is a guest's, so the writer is Administrator (spec decision 11).
        Two first requests can both find it missing; the one whose insert loses reads
        the winner's row (old `frappe_platform/models.py:1806-1826`).
        """
        from accounts.roles import ADMINISTRATOR

        document = cls._default_manager.filter(pk=cls.singleton_name()).first()
        if document is not None:
            return document
        try:
            with transaction.atomic():
                document = cls(name=cls.singleton_name(), **sysdefaults_from_environment())
                document.save(user=ADMINISTRATOR)
                return document
        except IntegrityError:
            return cls._default_manager.get(pk=cls.singleton_name())

    def sysdefaults(self) -> dict[str, str]:
        """`frappe.defaults.get_defaults()` for the seven keys, as strings."""
        return {field: str(getattr(self, field) or "") for field in SYSDEFAULT_FIELDS}


SERVICE_PROVIDERS = (
    "frankfurter.app",
    "fawazahmed-exchange-api",
    "exchangerate.host",
    "exchangerate-api",
)
TIMELINE_TIMESTAMP_FORMATS = ("Relative", "Exact")
TIMELINE_SORT_ORDERS = ("Oldest First", "Newest First")
DROPDOWN_TYPES = ("Route", "Separator")


class FCRMSettings(SingletonDocument):
    """The CRM's own settings single, read by every screen (old
    `crm_app/models/metadata.py:316-379`). All 16 fields; the behaviour that reads each
    is its own unit's. No save hooks, as in `backend/` (spec section 4.3)."""

    DOCTYPE = "FCRM Settings"
    #: Upstream bug #20: the provider credential is restricted to the manager pair.
    RESTRICTED_FIELDS = ("access_key",)
    #: Attach fields; attach-on-save itself is ACTIVITIES'.
    ATTACH_FIELDS = ("brand_logo", "favicon")
    TEXT_LINK_FIELDS = {"currency": ("configuration.Currency", "Currency")}

    brand_name = models.CharField(max_length=140, blank=True, default="")
    brand_logo = models.CharField(max_length=500, blank=True, default="")
    favicon = models.CharField(max_length=500, blank=True, default="")
    enable_forecasting = models.BooleanField(default=False)
    enable_sales_hierarchy = models.BooleanField(default=False)
    currency = models.CharField(max_length=140, blank=True, default="")
    service_provider = models.CharField(
        max_length=40,
        choices=_choices(SERVICE_PROVIDERS),
        blank=True,
        default="frankfurter.app",
    )
    access_key = models.CharField(max_length=280, blank=True, default="")
    auto_update_expected_deal_value = models.BooleanField(default=True)
    update_timestamp_on_new_communication = models.BooleanField(default=True)
    auto_mark_replied_on_response = models.BooleanField(default=False)
    auto_reopen_on_new_communication = models.BooleanField(default=False)
    crm_timeline_timestamp_format = models.CharField(
        max_length=20, choices=_choices(TIMELINE_TIMESTAMP_FORMATS), default="Relative"
    )
    crm_timeline_sort_order = models.CharField(
        max_length=20, choices=_choices(TIMELINE_SORT_ORDERS), default="Oldest First"
    )
    persona_captured = models.BooleanField(default=False)

    class Meta(SingletonDocument.Meta):
        verbose_name = "FCRM Settings"

    @classmethod
    def load(cls, *, user):
        """The old loader's name (`backend/crm_app/models/metadata.py:369-376`): the same as
        `load_or_create`, so a later port that calls `load` still gets the standard items
        on a row it creates."""
        return cls.load_or_create(user=user)

    @classmethod
    def load_or_create(cls, *, user):
        """The row; if it is missing, written with `user` as actor and given the standard
        items. A row that exists is never refilled (old `metadata.py:369-376`)."""
        document = cls._default_manager.filter(pk=cls.singleton_name()).first()
        if document is not None:
            return document
        try:
            with transaction.atomic():
                document = cls(name=cls.singleton_name())
                document.save(user=user)
                add_standard_dropdown_items(document, user=user)
                return document
        except IntegrityError:
            return cls._default_manager.get(pk=cls.singleton_name())


class CRMDropdownItem(BaseDocument):
    """A row of FCRM Settings' `dropdown_items`, the sidebar's user menu. Read and written
    inline only; no route of its own."""

    DOCTYPE = "CRM Dropdown Item"
    NAME_STRATEGY = Hash()
    IS_CHILD_TABLE = True
    CHILD_FIELDS = (
        "name",
        "owner",
        "modified_by",
        "creation",
        "modified",
        "idx",
        "docstatus",
        "_assign",
        "_liked_by",
        "_comments",
        "_user_tags",
        "parent_settings",
        "parentfield",
        "parenttype",
        "name1",
        "label",
        "type",
        "route",
        "icon",
        "hidden",
        "is_standard",
        "open_in_new_window",
    )

    parent_settings = models.ForeignKey(
        FCRMSettings, on_delete=models.CASCADE, related_name="dropdown_items"
    )
    parenttype = models.CharField(max_length=140, default="FCRM Settings")
    parentfield = models.CharField(max_length=140, default="dropdown_items")
    # `name1` is upstream's fieldname: `name` is the key.
    name1 = models.CharField(max_length=140, blank=True, default="")
    label = models.CharField(max_length=140, blank=True, default="")
    type = models.CharField(
        max_length=20, choices=_choices(DROPDOWN_TYPES), blank=True, default=""
    )
    route = models.CharField(max_length=280, blank=True, default="")
    icon = models.TextField(blank=True, default="")
    hidden = models.BooleanField(default=False)
    is_standard = models.BooleanField(default=False)
    open_in_new_window = models.BooleanField(default=True)

    class Meta(BaseDocument.Meta):
        ordering = ["idx"]


#: `crm/hooks.py:314-357` `standard_dropdown_items`, verbatim (old `metadata.py:412-446`).
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
    {
        "name1": "about",
        "label": "About",
        "type": "Route",
        "icon": "info",
        "route": "#",
        "is_standard": True,
    },
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

#: What `force` puts back on a standard row; `hidden` and `open_in_new_window` stay as an
#: administrator set them.
_RESTORED_DROPDOWN_FIELDS = ("label", "type", "route", "icon")


def add_standard_dropdown_items(settings, *, user, force: bool = False) -> int:
    """`crm/install.py:530-542`: the standard items, unless the row has any; returns the
    rows written (old `metadata.py:449-491`, ported whole).

    `force` restores the standard rows by `name1` (label, type, route and icon back to
    what the app ships, a missing one re-added at the end) and leaves custom rows alone.
    Its operator command is milestone 6's.
    """
    rows = settings.dropdown_items
    if not rows.exists():
        for idx, item in enumerate(STANDARD_DROPDOWN_ITEMS, start=1):
            CRMDropdownItem(parent_settings=settings, idx=idx, **item).save(user=user)
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
                parent_settings=settings,
                idx=next_idx,
                name1=item["name1"],
                is_standard=True,
                **shipped,
            ).save(user=user)
            next_idx += 1
            written += 1
            continue
        if row.is_standard and all(
            getattr(row, field) == value for field, value in shipped.items()
        ):
            continue
        for field, value in shipped.items():
            setattr(row, field, value)
        row.is_standard = True
        row.save(user=user)
        written += 1
    return written
