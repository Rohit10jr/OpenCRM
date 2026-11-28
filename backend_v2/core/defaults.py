"""The ordered list of restore writers `restore_defaults` runs (specs/CONFIGURATION.md
§10.3), as `core.dev_data.STEPS` lists the dev-data steps.

Each writer takes `(user, force)` and returns the rows it added plus the rows it
rewrote. A later unit that writes default rows by migration appends its writer here
(AS_BUILT §2, "Adding a default row").
"""

from __future__ import annotations

from typing import Callable

from accounts.models import User
from configuration import restore as configuration_restore
from contacts import restore as contacts_restore

RestoreWriter = Callable[[User, bool], int]

#: `(key, writer)`, in the output's order.
RESTORERS: tuple[tuple[str, RestoreWriter], ...] = (
    ("fields_layouts", configuration_restore.fields_layouts),
    ("quick_filters", configuration_restore.quick_filters),
    ("form_scripts", configuration_restore.form_scripts),
    ("countries", configuration_restore.countries),
    ("currencies", configuration_restore.currencies),
    ("languages", configuration_restore.languages),
    ("system_settings", configuration_restore.system_settings),
    ("fcrm_settings", configuration_restore.fcrm_settings),
    ("dropdown_items", configuration_restore.dropdown_items),
    ("salutations", contacts_restore.salutations),
    ("genders", contacts_restore.genders),
    ("industries", contacts_restore.industries),
)
