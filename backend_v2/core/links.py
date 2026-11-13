"""Validation for Link fields represented by plain text columns."""

from django.apps import apps

from core.exceptions import LinkValidationError
from core.translate import _


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
            missing.append(
                _("Row #{0}: {1}: {2}").format(
                    getattr(instance, "idx", 0), label, value
                )
            )
        else:
            missing.append(_("{0}: {1}").format(label, value))
    if missing:
        raise LinkValidationError(_("Could not find {0}").format(", ".join(missing)))
