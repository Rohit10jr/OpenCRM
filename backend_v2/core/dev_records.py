"""Which rows the development seed created (owner, DECISIONS 9).

`seed_dev_data` records each row it creates; `clear_dev_data` deletes only recorded rows,
then forgets them. A row that existed before the seed is never on the record, so it is
never deleted. A future setup wizard loading demo data on a real site needs exactly this.
"""

from __future__ import annotations

from django.utils import timezone

from core.models import DevDataRecord


def record_created(step: str, instance) -> None:
    DevDataRecord.objects.get_or_create(
        model_label=instance._meta.label,
        object_pk=str(instance.pk),
        defaults={"step": step},
    )


def refresh_record(step: str, instance) -> None:
    """The seed replaced a row on its record (a forced rewrite): the record now
    describes the new row, so `still_seeded` keeps counting it as the seed's."""
    DevDataRecord.objects.filter(
        step=step, model_label=instance._meta.label, object_pk=str(instance.pk)
    ).update(creation=timezone.now())


def recorded_pks(step: str, model) -> list[str]:
    return list(
        DevDataRecord.objects.filter(step=step, model_label=model._meta.label).values_list(
            "object_pk", flat=True
        )
    )


def still_seeded(step: str, model, rows):
    """The rows whose record still describes them. A row created after its record (the
    seeded row was deleted by hand and a new one made under the same name) is not the
    seed's any more and is never deleted (A-26)."""
    recorded = dict(
        DevDataRecord.objects.filter(step=step, model_label=model._meta.label).values_list(
            "object_pk", "creation"
        )
    )
    return [
        row
        for row in rows
        if str(row.pk) in recorded and row.creation <= recorded[str(row.pk)]
    ]


def forget(step: str, model) -> None:
    DevDataRecord.objects.filter(step=step, model_label=model._meta.label).delete()
