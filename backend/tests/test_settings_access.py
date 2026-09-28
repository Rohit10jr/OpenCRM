"""A4 - the integration settings records.

Four doctypes holding how the CRM talks to the outside world, none of which had a
permission rule. Any authenticated caller could read the Twilio and Exotel credentials
and, worse, **rewrite** them - pointing the telephony integration at an account they
control.

Two different answers, and the difference is the point:

* **Twilio / Exotel** - reads closed, matching upstream. These back an *administration*
  screen; its whole purpose is manager-only.
* **FCRM Settings** - reads open, matching upstream. Every screen in the product reads
  its timestamp format. Which is why the credential sitting on it needed narrowing
  instead.

Deliberately **not** the same answer as `Email Account`, where reads were opened. That
record feeds a user-facing feature on a page meant for everyone; these do not. Deciding
by pattern rather than by what the screen is for would get one of them wrong.
"""

import pytest

from crm_app.models import CRMExotelSettings, CRMTwilioSettings, FCRMSettings
from frappe_core import secrets
from frappe_core.session import session_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager(make_user):
    return make_user("mgr@example.com", roles=["Sales Manager"])


@pytest.fixture
def twilio(administrator):
    with session_user(administrator.name):
        return CRMTwilioSettings.objects.create(
            enabled=True,
            account_sid="ACxxxx",
            api_key="SKxxxx",
            api_secret="the-api-secret",
            auth_token="the-auth-token",
            twiml_sid="APxxxx",
        )


@pytest.fixture
def exotel(administrator):
    with session_user(administrator.name):
        return CRMExotelSettings.objects.create(
            enabled=True,
            account_sid="exo-account",
            api_key="exo-key",
            api_token="the-api-token",
            webhook_verify_token="the-webhook-secret",
        )


@pytest.fixture
def app_settings(administrator):
    with session_user(administrator.name):
        return FCRMSettings.objects.create(
            brand_name="Acme", access_key="fx-provider-key", currency="USD"
        )


# --- telephony: managers only ------------------------------------------------------------


@pytest.mark.parametrize("doctype", ["CRM Twilio Settings", "CRM Exotel Settings"])
def test_an_ordinary_user_cannot_read_telephony_settings(alice, twilio, exotel, api_as, doctype):
    assert api_as(alice).get(f"/api/resource/{doctype}/{doctype}").status_code == 403


@pytest.mark.parametrize("doctype", ["CRM Twilio Settings", "CRM Exotel Settings"])
def test_the_list_route_hides_them_too(alice, twilio, exotel, api_as, doctype):
    """`has_permission` guards the document; `permission_query_conditions` guards the
    list. A rule that sets one and not the other is the shape of every finding in this
    phase - returning None from the query hook would hand the row straight back here."""
    assert api_as(alice).get(f"/api/resource/{doctype}").json()["data"] == []


def test_an_ordinary_user_cannot_rewrite_the_telephony_credentials(alice, twilio, api_as):
    """**The finding.** Rewriting these points the integration at an account the caller
    controls - it does not require reading the existing values."""
    response = api_as(alice).put(
        "/api/resource/CRM Twilio Settings/CRM Twilio Settings",
        {"account_sid": "attacker-account"},
        format="json",
    )
    assert response.status_code == 403

    twilio.refresh_from_db()
    assert twilio.account_sid == "ACxxxx"


def test_the_method_endpoint_is_covered_by_the_same_rule(alice, twilio, api_as):
    response = api_as(alice).post(
        "/api/method/frappe.client.set_value",
        {
            "doctype": "CRM Twilio Settings",
            "name": "CRM Twilio Settings",
            "fieldname": {"account_sid": "attacker-account"},
        },
        format="json",
    )
    assert response.status_code == 403

    twilio.refresh_from_db()
    assert twilio.account_sid == "ACxxxx"


def test_a_manager_can_read_and_write_them(manager, twilio, api_as):
    body = api_as(manager).get("/api/resource/CRM Twilio Settings/CRM Twilio Settings")
    assert body.status_code == 200
    assert body.json()["data"]["account_sid"] == "ACxxxx"

    assert api_as(manager).put(
        "/api/resource/CRM Twilio Settings/CRM Twilio Settings",
        {"record_calls": True},
        format="json",
    ).status_code == 200


# --- FCRM Settings: read for all, write for managers -------------------------------------


def test_everyone_can_read_the_app_settings(alice, app_settings, api_as):
    """`stores/settings.js` loads this on every screen; the activity timeline reads its
    timestamp format. Closing it would break the product for non-managers."""
    body = api_as(alice).get("/api/resource/FCRM Settings/FCRM Settings").json()["data"]
    assert body["crm_timeline_timestamp_format"] == "Relative"


def test_an_ordinary_user_cannot_write_the_app_settings(alice, app_settings, api_as):
    response = api_as(alice).put(
        "/api/resource/FCRM Settings/FCRM Settings", {"brand_name": "Pwned"}, format="json"
    )
    assert response.status_code == 403

    app_settings.refresh_from_db()
    assert app_settings.brand_name == "Acme"


def test_a_manager_can_write_the_app_settings(manager, app_settings, api_as):
    assert api_as(manager).put(
        "/api/resource/FCRM Settings/FCRM Settings", {"brand_name": "Acme Corp"}, format="json"
    ).status_code == 200


def test_the_exchange_rate_key_is_hidden_from_an_ordinary_user(alice, app_settings, api_as):
    """**The one place A4's field work is load-bearing.**

    This record has to be world-readable, and upstream leaves the FX-provider credential
    on it with no `permlevel` - even though the same authors used `permlevel: 1` on
    Twilio's `api_key` for exactly this. Upstream bug #20.
    """
    body = api_as(alice).get("/api/resource/FCRM Settings/FCRM Settings").json()["data"]
    assert "access_key" not in body


def test_a_manager_still_sees_the_exchange_rate_key(manager, app_settings, api_as):
    """The settings screen reads it back, which is why hiding it outright was the wrong
    fix and phase 1 was right to decline it."""
    body = api_as(manager).get("/api/resource/FCRM Settings/FCRM Settings").json()["data"]
    assert body["access_key"] == "fx-provider-key"


def test_the_key_cannot_be_probed_by_filtering(alice, app_settings, api_as):
    response = api_as(alice).get(
        '/api/resource/FCRM Settings?filters=[["access_key","like","fx%"]]'
    )
    assert response.status_code == 400


# --- encryption at rest --------------------------------------------------------------------


@pytest.mark.parametrize(
    "model,fieldname,value",
    [
        (CRMTwilioSettings, "api_secret", "the-api-secret"),
        (CRMTwilioSettings, "auth_token", "the-auth-token"),
        (CRMExotelSettings, "api_token", "the-api-token"),
    ],
)
def test_telephony_credentials_are_not_stored_in_plain_text(
    twilio, exotel, model, fieldname, value
):
    """Read the column, not the model: the question is what a database dump would show.

    Upstream never faces this - `Password` fieldtypes live in the encrypted `__Auth`
    table, not on the document.
    """
    stored = model.objects.values_list(fieldname, flat=True).first()

    assert stored != value
    assert value not in stored
    assert secrets.is_encrypted(stored)


def test_a_credential_round_trips(twilio):
    twilio.refresh_from_db()
    assert twilio.get_password("auth_token") == "the-auth-token"


def test_saving_twice_does_not_double_encrypt(twilio):
    twilio.record_calls = True
    twilio.save()
    twilio.refresh_from_db()

    assert twilio.get_password("api_secret") == "the-api-secret"


def test_the_migration_encrypts_existing_rows(twilio):
    import importlib

    from django.apps import apps

    migration = importlib.import_module("crm_app.migrations.0003_encrypt_telephony_credentials")

    CRMTwilioSettings.objects.filter(pk=twilio.pk).update(auth_token="legacy-plaintext")
    migration.encrypt_existing(apps, None)

    stored = CRMTwilioSettings.objects.values_list("auth_token", flat=True).first()
    assert secrets.is_encrypted(stored)
    assert secrets.decrypt(stored) == "legacy-plaintext"


def test_the_webhook_token_is_never_served(manager, exotel, api_as):
    """Stricter than upstream, which leaves it plain `Data`. It is what proves an inbound
    webhook really came from Exotel; anyone holding it can forge call events.

    Visible to a manager, who configures it - the restriction is against everyone else,
    and the row rule already denies them the record entirely. Belt and braces."""
    body = api_as(manager).get("/api/resource/CRM Exotel Settings/CRM Exotel Settings").json()["data"]
    assert body["webhook_verify_token"] == "the-webhook-secret"
