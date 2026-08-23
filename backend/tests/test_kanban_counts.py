"""B5 - the kanban badge counts, and whether they leak.

`get_counts` counts related rows **without a permission filter**, deliberately: upstream
uses `frappe.db.count`, and a badge reading "3 comments" that shows a different number to
each viewer would be stranger than an accurate one. Phase 4 reproduced that and recorded
the reasoning, but never tested the thing that would make it dangerous.

The concern was concrete: a count is a fact about a record. If you can obtain the comment
count of a deal you cannot open, you learn that the deal exists and how much activity it
has - the kind of leak that reads as harmless until someone iterates over sequential
document names.

**It does not happen, and the reason is structural rather than careful.** `get_counts`
takes a row, and the only caller feeds it rows from `fetch_rows` / `get_records_based_on_order`,
both permission-filtered. An invisible deal never becomes a row, so it never gets a count.

That is worth a test rather than a paragraph, because it is a property of the *caller*, not
of `get_counts` - and a future refactor that hands it an unfiltered queryset would restore
the leak without touching the function these comments live on.
"""

import pytest

from frappe_core.api.doc import get_data
from crm_app.models import CRMDeal, CRMDealStatus
from frappe_core.session import session_user
from frappe_platform.models import Comment, Communication

pytestmark = pytest.mark.django_db


def _kanban(user, doctype="CRM Deal"):
    with session_user(user):
        return get_data(
            doctype=doctype,
            filters={},
            order_by="modified desc",
            view={"view_type": "kanban"},
            column_field="status",
        )


@pytest.fixture
def deals(administrator, alice, bob):
    """One deal each, both with activity on them."""
    with session_user(administrator.name):
        status = CRMDealStatus.objects.create(deal_status="Qualification", type="Open")
        made = {}
        for owner, key in ((alice, "mine"), (bob, "theirs")):
            deal = CRMDeal.objects.create(status=status, deal_owner=owner, deal_value=1000)
            made[key] = deal
            for i in range(3):
                Comment.objects.create(
                    comment_type="Comment",
                    content=f"{key} comment {i}",
                    reference_doctype="CRM Deal",
                    reference_name=deal.name,
                )
            Communication.objects.create(
                subject=f"{key} email",
                content="body",
                communication_type="Communication",
                reference_doctype="CRM Deal",
                reference_name=deal.name,
            )
    return made


def test_an_invisible_deal_never_reaches_the_counts(alice, deals):
    """**The leak, tested from the outside.** Alice sees her own board; bob's deal is not
    on it, so no badge about it is computed or returned."""
    result = _kanban(alice.name)

    names = [row["name"] for entry in result["data"] for row in entry["data"]]
    assert deals["mine"].name in names
    assert deals["theirs"].name not in names


def test_the_counts_that_do_appear_are_correct(alice, deals):
    """The other half: filtering must not have broken the numbers. Upstream's badge is a
    true total, and a viewer-dependent one would be the actual bug."""
    result = _kanban(alice.name)

    row = next(
        r for entry in result["data"] for r in entry["data"] if r["name"] == deals["mine"].name
    )
    assert row["_comment_count"] == 3
    assert row["_email_count"] == 1


def test_the_column_total_is_permission_filtered_too(alice, deals):
    """`all_count` is the number above the column, computed separately from the rows. It
    goes through `count_rows(..., user=user)`, so it must agree with what is visible -
    a column reading "2" over one card would leak the existence of the other."""
    result = _kanban(alice.name)

    for entry in result["data"]:
        assert entry["column"]["all_count"] == len(entry["data"])


def test_an_administrator_sees_both(administrator, deals):
    """Proves the fixture really did create two deals with activity, so the assertions
    above are about permissions rather than about nothing being there."""
    result = _kanban(administrator.name)

    names = [row["name"] for entry in result["data"] for row in entry["data"]]
    assert {deals["mine"].name, deals["theirs"].name} <= set(names)


def test_counts_are_not_computed_for_rows_the_caller_cannot_see(alice, deals):
    """The structural claim, stated as a cost.

    `get_counts` runs two queries per row, so counting before filtering would be both a
    leak and a cost. Asserting the visible row count pins the property directly: if a
    refactor starts counting first and filtering afterwards, this number grows.
    """
    with session_user(alice.name):
        result = get_data(
            doctype="CRM Deal",
            filters={},
            order_by="modified desc",
            view={"view_type": "kanban"},
            column_field="status",
        )

    visible = sum(len(entry["data"]) for entry in result["data"])
    assert visible == 1, "alice owns one deal; if this grows, the filter moved"
