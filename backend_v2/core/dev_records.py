"""Which rows the development seed created (owner, DECISIONS 9).

`seed_dev_data` records each row it creates; `clear_dev_data` deletes only recorded rows,
then forgets them. A row that existed before the seed is never on the record, so it is
never deleted. A future setup wizard loading demo data on a real site needs exactly this.
"""

from __future__ import annotations

from core.models import DevDataRecord


def record_created(step: str, instance) -> None:
    DevDataRecord.objects.get_or_create(
        model_label=instance._meta.label,
        object_pk=str(instance.pk),
        defaults={"step": step},
    )


def recorded_pks(step: str, model) -> list[str]:
    return list(
        DevDataRecord.objects.filter(step=step, model_label=model._meta.label).values_list(
            "object_pk", flat=True
        )
    )


def forget(step: str, model) -> None:
    DevDataRecord.objects.filter(step=step, model_label=model._meta.label).delete()
