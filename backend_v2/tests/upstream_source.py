"""Where the tests find upstream Frappe CRM's source (as `backend/tests/upstream_source.py:21-28`).

Some tests compare backend_v2 against upstream's code (the doctype JSONs) and skip when
it is not there. Locally that is the owner's checkout; in CI
(`.github/workflows/backend_v2.yml`) the workflow checks out frappe/crm at the commit the
port follows and sets `CRM_UPSTREAM_DIR`.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Upstream Frappe CRM's Python package (`<checkout>/crm`).
CRM_SOURCE = Path(
    os.environ.get(
        "CRM_UPSTREAM_DIR", r"D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm"
    )
)

#: Upstream's doctype folders.
CRM_DOCTYPE_DIR = CRM_SOURCE / "fcrm" / "doctype"
