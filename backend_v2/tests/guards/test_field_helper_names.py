"""Every name a field helper offers is accepted by the served list route
(specs/CONFIGURATION.md section 4.5; A-35).

The helpers build their lists from the metadata file and the model, not from a
resource's allowlists; a name offered for filtering, grouping or sorting that the list
route then refuses would be a dropdown option that answers 417. Checked for Administrator,
who sees every readable field, on every served non-child doctype.
"""

from __future__ import annotations

import pytest

from configuration import field_helpers
from core.doctypes import declared_doctypes, is_child_table
from core.resources import routed_rule_map

pytestmark = pytest.mark.django_db

#: Standard fields a helper offers on a model that lacks the column, as backend/ offers
#: them (its helpers append the standard lists to every doctype,
#: frappe_core/metadata.py:123-125, :166-171; crm_app/api/doc.py:99-100). User is not a
#: document model, so it has no owner, modified_by or _-prefixed columns; choosing one of
#: these on the User list fails in both backends. Parity until decided otherwise.
REVIEWED_STANDARD_ON_USER = {
    ("User", "filter", name)
    for name in ("owner", "modified_by", "_user_tags", "_liked_by", "_comments", "_assign")
} | {
    ("User", "group by", name)
    for name in ("modified_by", "owner", "_liked_by", "_assign", "_comments")
} | {("User", "sort", name) for name in ("modified_by", "owner")}


def _served():
    rules = routed_rule_map()
    for doctype, model in sorted(declared_doctypes().items()):
        viewset = rules.get(model)
        if viewset is not None and not is_child_table(model):
            yield doctype, model, viewset


def test_every_offered_name_is_accepted_by_the_list_route(administrator):
    refused = []
    for doctype, model, viewset in _served():
        filterable = set(viewset.filterable_fields)
        sortable = set(viewset.sortable_fields)
        for row in field_helpers.get_filterable_fields(doctype, model, administrator):
            if row["fieldname"] not in filterable:
                refused.append((doctype, "filter", row["fieldname"]))
        for row in field_helpers.get_group_by_fields(doctype, model, administrator):
            if row["fieldname"] not in filterable:
                refused.append((doctype, "group by", row["fieldname"]))
        for row in field_helpers.sort_options(doctype, model, administrator):
            if row["fieldname"] not in sortable:
                refused.append((doctype, "sort", row["fieldname"]))
    unexpected = sorted(set(refused) - REVIEWED_STANDARD_ON_USER)
    assert not unexpected, f"Offered but refused by the list route: {unexpected}"
    assert REVIEWED_STANDARD_ON_USER <= set(refused), "a reviewed exception no longer applies"
