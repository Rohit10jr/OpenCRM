"""C1c - the deal-only lifecycle: forecasting fields and the primary contact.

Ports ``update_closed_date``, ``update_default_probability``,
``update_expected_deal_value``, ``validate_forecasting_fields``, ``set_primary_contact``
and ``set_primary_email_mobile_no`` (``crm_deal.py:114-149,220-253``), plus the Won
``closed_date`` branch at ``crm_deal.py:91-93``.
"""

import pytest

from crm_app.models import (
    CRMContacts,
    CRMDeal,
    CRMDealStatus,
    CRMLostReason,
)
from crm_app.models.metadata import FCRMSettings
from frappe_core.exceptions import MandatoryError, ValidationError
from frappe_core.session import session_user
from frappe_platform.models import Contact

pytestmark = pytest.mark.django_db


@pytest.fixture
def statuses(administrator):
    with session_user(administrator.name):
        return {
            "qualification": CRMDealStatus.objects.create(
                deal_status="Qualification", type="Open", probability=20
            ),
            "negotiation": CRMDealStatus.objects.create(
                deal_status="Negotiation", type="Open", probability=60
            ),
            "won": CRMDealStatus.objects.create(deal_status="Won", type="Won", probability=100),
            "lost": CRMDealStatus.objects.create(deal_status="Lost", type="Lost", probability=0),
        }


@pytest.fixture
def settings_flags(administrator):
    def _set(**flags):
        with session_user(administrator.name):
            settings = FCRMSettings.load()
            for key, value in flags.items():
                setattr(settings, key, value)
            settings.save()

    return _set


# --- probability -----------------------------------------------------------------


def test_probability_is_inherited_from_the_status(alice, statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["negotiation"])
    assert deal.probability == 60


def test_an_explicit_probability_is_kept(alice, statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["negotiation"], probability=35)
    assert deal.probability == 35


def test_a_status_without_a_probability_yields_zero(alice, administrator):
    with session_user(administrator.name):
        blank = CRMDealStatus.objects.create(deal_status="Fresh", type="Open")
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=blank)
    assert deal.probability == 0


# --- closed_date ------------------------------------------------------------------


def test_moving_to_a_Won_status_sets_the_closed_date(alice, statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["qualification"])
    assert deal.closed_date is None

    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.status = statuses["won"]
        reloaded.save()

    assert reloaded.closed_date is not None


def test_a_non_won_status_leaves_the_closed_date_alone(alice, statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["qualification"])
    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.status = statuses["negotiation"]
        reloaded.save()

    assert reloaded.closed_date is None


def test_a_won_status_by_a_different_name_still_closes(alice, administrator):
    """The two upstream paths differ: ``update_closed_date`` compares the status *name*
    to "Won", while ``validate`` compares the status *type*. Renaming the status leaves
    only the type check firing - which is the one that matters."""
    with session_user(administrator.name):
        open_status = CRMDealStatus.objects.create(deal_status="Open", type="Open")
        closed_won = CRMDealStatus.objects.create(deal_status="Closed Won", type="Won")

    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=open_status)
    reloaded = CRMDeal.objects.get(pk=deal.pk)
    with session_user(alice.name):
        reloaded.status = closed_won
        reloaded.save()

    assert reloaded.closed_date is not None


# --- expected deal value -----------------------------------------------------------


def test_expected_value_tracks_the_total_when_already_set(alice, statuses, settings_flags):
    settings_flags(auto_update_expected_deal_value=True)
    with session_user(alice.name):
        deal = CRMDeal.objects.create(
            status=statuses["qualification"], total=5000, expected_deal_value=1
        )
    assert deal.expected_deal_value == 5000


def test_an_empty_expected_value_is_not_populated(alice, statuses, settings_flags):
    """Faithful to ``crm_deal.py:238-243``, which requires ``expected_deal_value`` to be
    truthy *before* it will overwrite it. So this never fills a blank - it only keeps a
    non-empty value in step. Reads like an oversight; reproduced because the behaviour is
    user-visible either way."""
    settings_flags(auto_update_expected_deal_value=True)
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["qualification"], total=5000)
    assert not deal.expected_deal_value


def test_net_total_wins_over_total(alice, statuses, settings_flags):
    settings_flags(auto_update_expected_deal_value=True)
    with session_user(alice.name):
        deal = CRMDeal.objects.create(
            status=statuses["qualification"], total=5000, net_total=4500, expected_deal_value=1
        )
    assert deal.expected_deal_value == 4500


def test_the_flag_switches_it_off(alice, statuses, settings_flags):
    settings_flags(auto_update_expected_deal_value=False)
    with session_user(alice.name):
        deal = CRMDeal.objects.create(
            status=statuses["qualification"], total=5000, expected_deal_value=1
        )
    assert deal.expected_deal_value == 1


# --- forecasting mandatory checks ---------------------------------------------------


def test_forecasting_requires_an_expected_value(alice, statuses, settings_flags):
    settings_flags(enable_forecasting=True)
    with session_user(alice.name), pytest.raises(
        MandatoryError, match="Expected deal value is required."
    ):
        CRMDeal.objects.create(status=statuses["qualification"])


def test_forecasting_requires_a_closure_date(alice, statuses, settings_flags):
    settings_flags(enable_forecasting=True)
    with session_user(alice.name), pytest.raises(
        MandatoryError, match="Expected closure date is required."
    ):
        CRMDeal.objects.create(status=statuses["qualification"], expected_deal_value=100)


def test_forecasting_off_requires_nothing(alice, statuses, settings_flags):
    settings_flags(enable_forecasting=False)
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["qualification"])
    assert deal.pk


def test_the_flag_is_read_from_settings_when_not_passed(alice, statuses, settings_flags):
    """Phase 1 made the flag a required parameter, which left the rule inert because
    nothing ever passed it. It now reads the singleton, as upstream does."""
    settings_flags(enable_forecasting=True)
    with session_user(alice.name):
        deal = CRMDeal(status=statuses["qualification"])
        with pytest.raises(MandatoryError):
            deal.validate_forecasting()


# --- primary contact ---------------------------------------------------------------


def _add_contact(deal, **kwargs):
    """Details go on the **Contact**, not the child row.

    ``CRM Contacts`` declares ``fetch_from`` for email/mobile/phone/full_name/gender
    (``crm_contacts.json``), so the child row mirrors the linked Contact on every save
    and anything written directly to it is overwritten. Setting them on the child was
    how these tests were originally written, and it only passed because fetch_from was
    not ported yet.
    """
    from frappe_platform.models import ContactEmail, ContactPhone

    email = kwargs.pop("email", "")
    mobile_no = kwargs.pop("mobile_no", "")
    contact = Contact.objects.create(
        first_name=kwargs.pop("first_name", "Jane"),
        last_name=kwargs.pop("last_name", "Doe"),
    )
    # The Contact's own columns mirror its rows on every save (contact.py:65-68), so
    # the details go on the rows.
    if email:
        ContactEmail.objects.create(parent_contact=contact, email_id=email, is_primary=True)
    if mobile_no:
        ContactPhone.objects.create(parent_contact=contact, phone=mobile_no, is_primary_mobile_no=True)
    contact.refresh_from_db()
    return CRMContacts.objects.create(parent_deal=deal, contact=contact, **kwargs)


def test_a_lone_contact_becomes_primary(alice, statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["qualification"])
        _add_contact(deal, email="jane@acme.com", mobile_no="555")
        deal.sync_contact_fields()

    deal.refresh_from_db()
    assert deal.email == "jane@acme.com"
    assert deal.mobile_no == "555"


def test_naming_a_contact_promotes_it_and_demotes_the_rest(alice, statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["qualification"])
        _add_contact(deal, email="jane@acme.com", first_name="Jane")
        second = _add_contact(deal, email="john@acme.com", first_name="John")
        deal.set_primary_contact(second.contact_id)
        deal.set_primary_email_mobile_no()

    assert deal.email == "john@acme.com"
    assert CRMContacts.objects.filter(parent_deal=deal, is_primary=True).count() == 1


def test_two_primaries_are_rejected(alice, statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["qualification"])
        _add_contact(deal, is_primary=True, first_name="Jane")
        _add_contact(deal, is_primary=True, first_name="John")

        with pytest.raises(ValidationError, match="Only one Contact can be set as primary."):
            deal.set_primary_email_mobile_no()


def test_no_contacts_clears_the_fields(alice, statuses):
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["qualification"])
        deal.email = "stale@acme.com"
        deal.set_primary_email_mobile_no()

    assert deal.email == ""


def test_contacts_with_no_primary_clear_the_fields(alice, statuses):
    """Upstream clears rather than guessing - stale values would be worse."""
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["qualification"])
        _add_contact(deal, email="jane@acme.com", first_name="Jane")
        _add_contact(deal, email="john@acme.com", first_name="John")
        deal.email = "stale@acme.com"
        deal.set_primary_email_mobile_no()

    assert deal.email == ""


def test_lost_reason_still_applies(alice, statuses):
    """Guards the ordering: forecasting runs before the lost-reason check in save()."""
    with session_user(alice.name), pytest.raises(ValidationError, match="losing the deal"):
        CRMDeal.objects.create(status=statuses["lost"])


def test_a_lost_deal_with_a_reason_saves(alice, statuses, administrator):
    with session_user(administrator.name):
        reason = CRMLostReason.objects.create(lost_reason="Budget")
    with session_user(alice.name):
        deal = CRMDeal.objects.create(status=statuses["lost"], lost_reason=reason)
    assert deal.pk
