"""CONFIGURATION's documents (specs/CONFIGURATION.md section 4.2).

Ported from `backend/frappe_platform/models.py:1616-1839`.
"""

from django.conf import settings
from django.db import IntegrityError, models, transaction

from core.models import SingletonDocument

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


class SystemSettings(SingletonDocument):
    """Frappe's `System Settings` single, the seven fields the CRM reads.

    The Defaults page edits six of them; all seven reach the browser as the boot call's
    `sysdefaults`. The row is written by this app's data migration from
    `FRAPPE_SYSDEFAULTS`, and written again by `load_or_create` if it is ever missing.
    """

    DOCTYPE = "System Settings"

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
