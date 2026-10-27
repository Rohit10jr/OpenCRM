"""Where the tests find upstream's source, and the port's own frontend.

Some tests compare the port against upstream Frappe CRM's code (the doctype JSONs, the
dashboard defaults) and skip when it is not there. Locally that is the owner's checkout;
in CI (.github/workflows/backend.yml) the workflow checks out frappe/crm at the commit
the port follows and sets ``CRM_UPSTREAM_DIR``. The port's own frontend is always in this
repository, so it is found relative to it.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The repository root (``backend/tests/`` is two levels down).
REPO_ROOT = Path(__file__).resolve().parents[2]

#: The port's Vue source, in this repository.
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

#: Upstream Frappe CRM's Python package (``<checkout>/crm``).
CRM_SOURCE = Path(
    os.environ.get(
        "CRM_UPSTREAM_DIR", r"D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm"
    )
)

#: Upstream's doctype folders.
CRM_DOCTYPE_DIR = CRM_SOURCE / "fcrm" / "doctype"
