"""C1b - status defaults and the status change log.

Ports ``validate_status`` (``crm_lead.py:103-108``, ``crm_deal.py:107-112``) and
``add_status_change_log`` (``crm_status_change_log.py:45-83``).

Each log row records a **period spent in** a status: ``from`` is the status held and
``from_date`` when it began; ``to``/``to_date`` are filled when the record leaves it.
A transition therefore closes the open row and opens a new one. The naming reads
backwards at first glance, which is why every assertion below spells out the shape.
"""

import pytest

from crm_app.models import (
    CRMDeal,
    CRMDealStatus,
    CRMLead,
    CRMLeadStatus,
    CRMLostReason,
    CRMStatusChangeLog,
)
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def lead_statuses(administrator):
    with session_user(administrator.name):
        return {
            "new": CRMLeadStatus.objects.create(lead_status="New", type="Open"),
            "contacted": CRMLeadStatus.objects.create(lead_status="Contacted", type="Open"),
            "junk": CRMLeadStatus.objects.create(lead_status="Junk", type="Lost"),
        }


@pytest.fixture
def lost_reason(administrator):
    """A Lost status needs one - ``validate_lost_reason`` is already ported."""
    with session_user(administrator.name):
        return CRMLostReason.objects.create(lost_reason="Budget")


@pytest.fixture
def deal_statuses(administrator):
    with session_user(administrator.name):
        return {
            "qualification": CRMDealStatus.objects.create(
                deal_status="Qualification", type="Open"
            ),
            "won": CRMDealStatus.objects.create(deal_status="Won", type="Won"),
        }


def _log(doc):
    return list(
        CRMStatusChangeLog.objects.filter(
            parenttype=doc.get_doctype(), parent=str(doc.pk)
        ).order_by("idx")
    )


# --- validate_status: the default on create --------------------------------------


def test_a_new_lead_defaults_to_New(alice, lead_statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada")
    assert lead.status_id == "New"


def test_a_new_deal_defaults_to_Qualification(alice, deal_statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create()
    assert deal.status_id == "Qualification"


def test_the_default_falls_back_to_the_first_open_status(alice, administrator):
    """``crm_lead.py:105-108`` - when "New" does not exist, take any Open status."""
    with session_user(administrator.name):
        CRMLeadStatus.objects.create(lead_status="Fresh", type="Open")
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada")
    assert lead.status_id == "Fresh"


def test_an_explicit_status_is_not_overridden(alice, lead_statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", status=lead_statuses["contacted"])
    assert lead.status_id == "Contacted"


def test_the_default_does_not_apply_on_update(alice, lead_statuses):
    """``is_new()`` guards it - clearing the status later must not silently reset it."""
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", status=lead_statuses["contacted"])

    reloaded = CRMLead.objects.get(pk=lead.pk)
    with session_user(alice.name):
        reloaded.first_name = "Ada B"
        reloaded.save()

    assert reloaded.status_id == "Contacted"


# --- add_status_change_log --------------------------------------------------------


def test_creating_a_lead_opens_one_log_row(alice, lead_statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", status=lead_statuses["new"])

    rows = _log(lead)
    assert len(rows) == 1
    assert getattr(rows[0], "from") == "New"
    assert getattr(rows[0], "to") == ""
    assert rows[0].from_date is not None
    assert rows[0].to_date is None
    assert rows[0].log_owner_id == alice.name


def test_a_transition_closes_the_open_row_and_opens_a_new_one(alice, lead_statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", status=lead_statuses["new"])

    reloaded = CRMLead.objects.get(pk=lead.pk)
    with session_user(alice.name):
        reloaded.status = lead_statuses["contacted"]
        reloaded.save()

    rows = _log(reloaded)
    assert len(rows) == 2

    closed, open_row = rows
    assert getattr(closed, "from") == "New"
    assert getattr(closed, "to") == "Contacted"
    assert closed.to_date is not None
    assert closed.duration is not None and closed.duration >= 0

    assert getattr(open_row, "from") == "Contacted"
    assert getattr(open_row, "to") == ""
    assert open_row.to_date is None


def test_saving_without_a_status_change_adds_no_row(alice, lead_statuses):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", status=lead_statuses["new"])

    reloaded = CRMLead.objects.get(pk=lead.pk)
    with session_user(alice.name):
        reloaded.first_name = "Ada B"
        reloaded.save()

    assert len(_log(reloaded)) == 1


def test_several_transitions_chain(alice, lead_statuses, lost_reason):
    with session_user(alice.name):
        lead = CRMLead.objects.create(first_name="Ada", status=lead_statuses["new"])

    for status in ("contacted", "junk"):
        reloaded = CRMLead.objects.get(pk=lead.pk)
        with session_user(alice.name):
            reloaded.status = lead_statuses[status]
            if status == "junk":
                reloaded.lost_reason = lost_reason
            reloaded.save()

    rows = _log(CRMLead.objects.get(pk=lead.pk))
    assert [getattr(r, "from") for r in rows] == ["New", "Contacted", "Junk"]
    assert [getattr(r, "to") for r in rows] == ["Contacted", "Junk", ""]


def test_deals_log_transitions_too(alice, deal_statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=deal_statuses["qualification"])

    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.status = deal_statuses["won"]
        reloaded.save()

    rows = _log(reloaded)
    assert getattr(rows[0], "to") == "Won"
    assert getattr(rows[-1], "from") == "Won"


# --- the deliberate divergence ----------------------------------------------------


def test_a_lead_log_records_the_lead_status_type(alice, lead_statuses, lost_reason):
    """**Diverges from upstream, on purpose.**

    ``crm_status_change_log.py:46,51`` resolves the type against ``"CRM Deal Status"``
    unconditionally, even though ``crm_lead.py:92`` calls it for leads - whose statuses
    live in ``CRM Lead Status``. Upstream therefore writes an empty ``from_type`` on
    every lead log row. Nothing reads these fields today, so correcting the lookup is
    invisible and makes the data usable.
    """
    with session_user(alice.name):
        lead = CRMLead.objects.create(
            first_name="Ada", status=lead_statuses["junk"], lost_reason=lost_reason
        )

    assert _log(lead)[0].from_type == "Lost"


def test_a_deal_log_records_the_deal_status_type(alice, deal_statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=deal_statuses["won"])

    assert _log(deal)[0].from_type == "Won"
