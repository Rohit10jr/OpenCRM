"""Timezones, OAuth providers and the user signature (specs/ACCOUNTS.md section 4.10).

The two timezone cases are ported from ``backend/tests/test_desk_plumbing.py:108, :125``
(`frappe.core.doctype.user.user.get_timezones` → `GET /api/v1/users/timezones/`). The
rest are new: no old test covers them.
"""

import pytest

pytestmark = pytest.mark.django_db
TIMEZONES = "/api/v1/users/timezones/"


def test_get_timezones_is_a_sorted_list_of_common_zones(auth_api):
    response = auth_api.get(TIMEZONES)
    assert response.status_code == 200
    zones = response.json()["message"]["timezones"]

    assert isinstance(zones, list)
    assert "Asia/Kolkata" in zones
    assert "Europe/Berlin" in zones
    assert "UTC" in zones
    assert not [zone for zone in zones if zone.startswith("Etc/")]
    assert zones == sorted(zones)


def test_get_timezones_answers_the_same_list_every_time(auth_api):
    from accounts.services import timezones

    first = auth_api.get(TIMEZONES).json()["message"]["timezones"]
    second = auth_api.get(TIMEZONES).json()["message"]["timezones"]
    assert first == second
    assert timezones() is timezones()


def test_oauth_providers_is_an_empty_list_for_a_guest(api):
    response = api.get("/api/v1/auth/oauth-providers/")
    assert response.status_code == 200
    assert response.json() == {"message": []}


def test_the_signature_is_null_without_one(auth_api):
    assert auth_api.get("/api/v1/users/signature/").json() == {"message": None}


def test_the_signature_wraps_the_users_own(auth_api, alice):
    alice.email_signature = "-- Alice"
    alice.save(update_fields=["email_signature"])
    assert auth_api.get("/api/v1/users/signature/").json() == {
        "message": '<br><p class="signature">-- Alice</p>'
    }


# --- the Email Account fallback (CONFIGURATION milestone 4, spec section 4.4) -------------


def _default_account(user, **fields):
    from configuration.models import EmailAccount

    values = {
        "email_account_name": "Default",
        "email_id": "default@example.com",
        "default_outgoing": True,
        "add_signature": True,
        "signature": "The Team",
        **fields,
    }
    EmailAccount(**values).save(user=user)


def test_the_signature_falls_back_to_the_default_outgoing_account(auth_api, administrator):
    _default_account(administrator)
    assert auth_api.get("/api/v1/users/signature/").json() == {
        "message": '<br><p class="signature">The Team</p>'
    }


def test_the_users_own_signature_wins_over_the_account(auth_api, alice, administrator):
    _default_account(administrator)
    alice.email_signature = "-- Alice"
    alice.save(update_fields=["email_signature"])
    assert auth_api.get("/api/v1/users/signature/").json() == {
        "message": '<br><p class="signature">-- Alice</p>'
    }


def test_no_fallback_without_add_signature(auth_api, administrator):
    _default_account(administrator, add_signature=False)
    assert auth_api.get("/api/v1/users/signature/").json() == {"message": None}
