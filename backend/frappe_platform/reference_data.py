"""The two lookup lists every site has: salutations and genders.

The framework's setup wizard writes them when a site is created
(``frappe/desk/page/setup_wizard/install_fixtures.py:20-49``), before any app installs,
so upstream code can rely on ``Mr`` and ``Male`` existing. Here a migration writes them
(``0014``), for the same reason: a Link to either is validated on save
(:mod:`frappe_core.links`), so a database without the rows would refuse every lead that
carries a salutation. ``manage.py seed_defaults`` calls the same functions, which puts
back a row someone deleted.
"""

from __future__ import annotations

#: ``install_fixtures.py:20-49``, in upstream's order.
GENDERS = (
    "Male",
    "Female",
    "Other",
    "Transgender",
    "Genderqueer",
    "Non-Conforming",
    "Prefer not to say",
)
SALUTATIONS = ("Mr", "Ms", "Mx", "Dr", "Mrs", "Madam", "Miss", "Master", "Prof")


def add_genders() -> int:
    """``install_fixtures.py:update_genders``. Returns how many rows were written."""
    from frappe_platform.models import Gender

    existing = set(Gender._default_manager.values_list("pk", flat=True))
    written = 0
    for gender in GENDERS:
        if gender not in existing:
            Gender(gender=gender).save()
            written += 1
    return written


def add_salutations() -> int:
    """``install_fixtures.py:update_salutations``. Returns how many rows were written."""
    from frappe_platform.models import Salutation

    existing = set(Salutation._default_manager.values_list("pk", flat=True))
    written = 0
    for salutation in SALUTATIONS:
        if salutation not in existing:
            Salutation(salutation=salutation).save()
            written += 1
    return written


def ensure_reference_rows() -> None:
    """Both lists, written only when a table is empty. One cheap query each otherwise."""
    from frappe_platform.models import Gender, Salutation

    if not Gender._default_manager.exists():
        add_genders()
    if not Salutation._default_manager.exists():
        add_salutations()
