"""CONTACTS' restore writers for `restore_defaults` (specs/CONFIGURATION.md §10.3).

The salutations, genders and industries the table lacks, by name, on live models; an
existing row is never changed. Upstream's `after_install` writes none of the three
reference lists; the old backend's seed does (`backend/crm_app/setup.py:557-564`).
"""

from __future__ import annotations

from contacts.reference_rows import GENDERS, INDUSTRIES, SALUTATIONS


def _missing(model, fieldname: str, values, user) -> int:
    existing = set(model._default_manager.values_list("pk", flat=True))
    written = 0
    for value in values:
        if value in existing:
            continue
        model(**{fieldname: value}).save(user=user)
        written += 1
    return written


def salutations(user, force: bool = False) -> int:
    from contacts.models import Salutation

    del force
    return _missing(Salutation, "salutation", SALUTATIONS, user)


def genders(user, force: bool = False) -> int:
    from contacts.models import Gender

    del force
    return _missing(Gender, "gender", GENDERS, user)


def industries(user, force: bool = False) -> int:
    from contacts.models import CRMIndustry

    del force
    return _missing(CRMIndustry, "industry", INDUSTRIES, user)
