"""Frappe-compatible document naming strategies."""

import re
import secrets
from datetime import datetime, timezone

from django.apps import apps
from django.db import transaction
from django.db.models.functions import Length

from core import exceptions

DEFAULT_SERIES_DIGITS = 5
FORBIDDEN_NAME_CHARACTERS = "<>"
_SERIES_DATE_TOKENS = ("YYYY", "YY", "MM", "DD", "WW")
_FORMAT_TOKEN = re.compile(r"\{(\w+)\}")


def _field_label(instance, fieldname: str) -> str:
    try:
        field = instance._meta.get_field(fieldname)
    except Exception:
        return fieldname
    label = str(field.verbose_name)
    return label.title() if label == field.name.replace("_", " ") else label


def append_number_if_name_exists(model, value: str, separator: str = "-") -> str:
    manager = model._default_manager
    if not manager.filter(pk=value).exists():
        return value
    pattern = f"^{re.escape(value)}{re.escape(separator)}[0-9]+$"
    last = manager.filter(pk__regex=pattern).order_by(Length("pk").desc(), "-pk").first()
    count = 1
    if last is not None:
        try:
            count = int(str(last.pk).rsplit(separator, 1)[1]) + 1
        except (IndexError, ValueError):
            pass
    return f"{value}{separator}{count}"


def validate_name(doctype: str, name: str, is_single: bool = False) -> str:
    if not name:
        raise exceptions.ValidationError(f"No Name Specified for {doctype}")
    if name.startswith("New " + doctype):
        raise exceptions.NameError(
            "There were some errors setting the name, please contact the administrator"
        )
    name = name.strip()
    if not is_single and doctype == name and name != "DocType":
        raise exceptions.NameError(f"Name of {doctype} cannot be {name}")
    if re.findall(f"[{FORBIDDEN_NAME_CHARACTERS}]+", name):
        characters = ", ".join(f"'{character}'" for character in FORBIDDEN_NAME_CHARACTERS)
        raise exceptions.NameError(
            f"Name cannot contain special characters like {characters}"
        )
    return name


class NameStrategy:
    requires_client_name = False
    db_assigned = False

    def generate(self, instance):
        raise NotImplementedError

    def __repr__(self):
        return f"{type(self).__name__}()"


class DataImportTimestamp(NameStrategy):
    def generate(self, instance) -> str:
        generated_at = datetime.now(timezone.utc)
        return (
            f"{instance.reference_doctype} Import on "
            f"{generated_at.strftime('%Y-%m-%d %H:%M:%S.%f')}"
        )


class NamingSeries(NameStrategy):
    def __init__(self, pattern: str, digits: int = DEFAULT_SERIES_DIGITS):
        if not pattern:
            raise ValueError("NamingSeries requires a pattern")
        self.pattern = pattern
        self.digits = digits

    def __repr__(self):
        return f"NamingSeries({self.pattern!r})"

    def resolve_prefix(self, instance=None, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        parts = []
        digits = self.digits
        for part in self.pattern.split("."):
            if not part:
                continue
            if part in _SERIES_DATE_TOKENS:
                parts.append(self._format_date_token(part, now))
            elif set(part) == {"#"}:
                digits = len(part)
            else:
                parts.append(part)
        return "".join(parts), digits

    @staticmethod
    def _format_date_token(token: str, now: datetime) -> str:
        values = {
            "YYYY": f"{now.year:04d}",
            "YY": f"{now.year % 100:02d}",
            "MM": f"{now.month:02d}",
            "DD": f"{now.day:02d}",
            "WW": f"{int(now.strftime('%U')) + 1:02d}",
        }
        return values[token]

    def generate(self, instance) -> str:
        prefix, digits = self.resolve_prefix(instance)
        return f"{prefix}{next_series_value(prefix):0{digits}d}"


class FieldValue(NameStrategy):
    def __init__(self, fieldname: str, label: str | None = None):
        if not fieldname:
            raise ValueError("FieldValue requires a fieldname")
        self.fieldname = fieldname
        self.label = label

    def __repr__(self):
        return f"FieldValue({self.fieldname!r})"

    def generate(self, instance) -> str:
        value = getattr(instance, self.fieldname, None)
        if hasattr(value, "pk"):
            value = value.pk
        value = ("" if value is None else str(value)).strip()
        if not value:
            label = self.label or _field_label(instance, self.fieldname)
            raise exceptions.ValidationError(f"{label} is required")
        return value


class Hash(NameStrategy):
    def __init__(self, length: int = 10):
        self.length = length

    def __repr__(self):
        return f"Hash({self.length})"

    def generate(self, instance) -> str:
        return secrets.token_hex((self.length + 1) // 2)[: self.length]


class Format(NameStrategy):
    def __init__(self, template: str):
        if not template:
            raise ValueError("Format requires a template")
        self.template = template

    def __repr__(self):
        return f"Format({self.template!r})"

    def generate(self, instance) -> str:
        def substitute(match):
            value = getattr(instance, match.group(1), None)
            if hasattr(value, "pk"):
                value = value.pk
            return "" if value is None else str(value)

        return _FORMAT_TOKEN.sub(substitute, self.template).strip()


class Prompt(NameStrategy):
    requires_client_name = True

    def generate(self, instance) -> str:
        value = "" if instance.pk is None else str(instance.pk).strip()
        if not value:
            raise exceptions.ValidationError("Please set the document name")
        return value


class AutoIncrement(NameStrategy):
    db_assigned = True

    def generate(self, instance):
        return None


def next_series_value(prefix: str) -> int:
    counter_model = apps.get_model("core", "NamingSeriesCounter")
    with transaction.atomic():
        counter_model.objects.get_or_create(prefix=prefix)
        row = counter_model.objects.select_for_update().get(prefix=prefix)
        row.current += 1
        row.save(update_fields=["current"])
        return row.current
