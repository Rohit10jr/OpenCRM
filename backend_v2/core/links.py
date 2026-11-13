"""Validation for Link fields represented by plain text columns."""

from django.apps import apps

from core.exceptions import LinkValidationError


def validate_text_links(instance) -> None:
    missing = []
    allowed_dangling = frozenset(
        getattr(type(instance), "ALLOW_DANGLING_LINK_FIELDS", ()) or ()
    )
    for fieldname, (model_label, label) in instance.TEXT_LINK_FIELDS.items():
        value = getattr(instance, fieldname, None)
        if value in (None, ""):
            continue
        manager = apps.get_model(model_label)._default_manager
        if manager.filter(pk=value).exists():
            continue
        if fieldname in allowed_dangling:
            continue
        spellings = list(
            manager.filter(pk__iexact=str(value)).values_list("pk", flat=True)[:2]
        )
        if len(spellings) == 1:
            setattr(instance, fieldname, spellings[0])
            continue
        if getattr(instance, "parentfield", None):
            missing.append(f"Row #{getattr(instance, 'idx', 0)}: {label}: {value}")
        else:
            missing.append(f"{label}: {value}")
    if missing:
        raise LinkValidationError("Could not find " + ", ".join(missing))
