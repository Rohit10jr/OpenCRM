"""CONTACTS' development data (specs/CONTACTS.md §4 "Reference rows"; REBUILD_PLAN S20).

Two `seed_dev_data` steps, recorded in `DevDataRecord` so `clear_dev_data` removes only
what they made:

- **reference rows**: the salutations and genders the data migration writes, put back
  when someone deleted one, as the old `seed_defaults` does
  (`backend/crm_app/setup.py:563-564`). A restored row is not recorded, so
  `clear_dev_data` never removes it: every database is promised these rows;
- **industries**: the 51 of `backend/crm_app/setup.py:159` (DECISIONS 44 stays parked,
  as for CONFIGURATION's default rows).
"""

from __future__ import annotations

from contacts.models import CRMIndustry, Gender, Salutation
from contacts.reference_rows import GENDERS, INDUSTRIES, SALUTATIONS
from core import dev_records

REFERENCE_STEP = "reference_rows"
INDUSTRIES_STEP = "industries"


def _write_missing(step, model, fieldname: str, values, user) -> int:
    """Writes the values the table lacks; records each in `step` unless `step` is None."""
    existing = set(model.objects.values_list("pk", flat=True))
    created = 0
    for value in values:
        if value in existing:
            continue
        row = model(**{fieldname: value})
        row.save(user=user)
        if step is not None:
            dev_records.record_created(step, row)
        created += 1
    return created


def _clear(step: str, model) -> int:
    """Deletes only the rows this step created and recorded."""
    recorded = dev_records.recorded_pks(step, model)
    seeded = dev_records.still_seeded(step, model, model.objects.filter(pk__in=recorded))
    model.objects.filter(pk__in=[row.pk for row in seeded]).delete()
    dev_records.forget(step, model)
    return len(seeded)


def add_reference_rows(user, force: bool = False) -> int:
    """The salutations and genders the table lacks, not recorded."""
    del force
    return _write_missing(None, Salutation, "salutation", SALUTATIONS, user) + (
        _write_missing(None, Gender, "gender", GENDERS, user)
    )


def clear_reference_rows(user, force: bool = False) -> int:
    """Nothing: the restored rows stay (they are promised to every database)."""
    del user, force
    return 0


def write_industries(user, force: bool = False) -> int:
    """The 51 industries the table lacks."""
    del force
    return _write_missing(INDUSTRIES_STEP, CRMIndustry, "industry", INDUSTRIES, user)


def clear_industries(user, force: bool = False) -> int:
    del user, force
    return _clear(INDUSTRIES_STEP, CRMIndustry)
