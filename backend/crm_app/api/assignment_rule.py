"""``crm.api.assignment_rule.*``. Ported from ``crm/api/assignment_rule.py``.

``Assignment Rule`` and ``Assignment Rule User`` are **framework** doctypes
(``frappe/automation/doctype/assignment_rule``), not CRM ones, and this port does not
model them - they are outside `PHASE_1_MODELS.md` section 1's list of nine platform
doctypes.

So the list endpoint returns ``[]`` (a site with no rules configured, which is what
upstream returns too) and duplication raises rather than pretending to succeed. The
frontend renders an empty rules list, which is honest; silently returning a fake
duplicate would not be.
"""

from __future__ import annotations

from frappe_core.exceptions import throw
from frappe_core.whitelist import whitelist


@whitelist("crm.api.assignment_rule.get_assignment_rules_list")
def get_assignment_rules_list():
    """``crm/api/assignment_rule.py:4-24``. Empty - see the module docstring."""
    return []


@whitelist("crm.api.assignment_rule.duplicate_assignment_rule")
def duplicate_assignment_rule(docname: str, new_name: str):
    """``crm/api/assignment_rule.py:27-32``.

    Raises rather than returning a stub: the caller expects a persisted rule back, and
    handing it a fabricated one would leave the UI showing a rule that does not exist.
    """
    throw("Assignment Rule is not available in this deployment")
