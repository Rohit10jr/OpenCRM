"""A1 - brute-force protection on the auth endpoints.

Ports the two mechanisms upstream applies and phase 3 left out:
``LoginAttemptTracker`` (``frappe/auth.py:519-613``) and ``rate_limit``
(``frappe/rate_limiter.py:105-171``).

They are not interchangeable, which is why upstream uses both on ``change_password``:
the tracker asks "is this account under attack?", the limiter asks "is this endpoint
being hammered?". A caller who never guesses wrong trips the limiter and not the tracker.
"""

import time

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from frappe_core.security import (
    ClientIPMiddleware,
    LoginAttemptTracker,
    RateLimitExceededError,
    SecurityException,
    check_login_allowed,
    get_client_ip,
    rate_limit,
    record_login_failure,
)

pytestmark = pytest.mark.django_db

LOGIN = "/api/method/login"
CHANGE_PW = "/api/method/crm.api.user.change_password"


# --- LoginAttemptTracker ------------------------------------------------------------


def test_a_fresh_key_is_allowed():
    assert LoginAttemptTracker("nobody@example.com").is_user_allowed() is True


def test_lockout_needs_more_than_the_threshold():
    """Upstream compares ``count > max`` (``auth.py:610``), so the limit is the number of
    failures *tolerated*, and the one after it locks."""
    tracker = LoginAttemptTracker("victim@example.com", max_consecutive_login_attempts=3)

    for _ in range(3):
        tracker.add_failure_attempt()
    assert tracker.is_user_allowed() is True, "locked one attempt too early"

    tracker.add_failure_attempt()
    assert tracker.is_user_allowed() is False


def test_success_clears_the_count():
    tracker = LoginAttemptTracker("victim@example.com", max_consecutive_login_attempts=2)
    for _ in range(3):
        tracker.add_failure_attempt()
    assert tracker.is_user_allowed() is False

    tracker.add_success_attempt()
    assert tracker.is_user_allowed() is True


def test_failures_outside_the_window_do_not_accumulate():
    """The counter is for *consecutive* failures inside the interval.

    Without this, one wrong password an hour would eventually lock a legitimate user out
    permanently - and would let an attacker lock someone out cheaply.
    """
    tracker = LoginAttemptTracker(
        "victim@example.com", max_consecutive_login_attempts=2, lock_interval=1
    )
    tracker.add_failure_attempt()
    tracker.add_failure_attempt()
    time.sleep(1.1)

    tracker.add_failure_attempt()
    assert tracker.is_user_allowed() is True, "a stale window was counted"


def test_check_login_allowed_raises_for_a_locked_key(settings):
    """``check_login_allowed`` reads the configured threshold, not one passed to a
    tracker instance - so the setting is what the endpoints actually enforce."""
    settings.LOGIN_MAX_CONSECUTIVE_ATTEMPTS = 1

    record_login_failure("locked@example.com")
    record_login_failure("locked@example.com")

    with pytest.raises(SecurityException, match="locked"):
        check_login_allowed("locked@example.com")


def test_keys_are_independent():
    record_login_failure("a@example.com")
    assert LoginAttemptTracker("b@example.com").is_user_allowed() is True


# --- the login endpoint --------------------------------------------------------------


def test_login_succeeds_normally(api, alice):
    response = api.post(LOGIN, {"usr": alice.name, "pwd": "secret123"}, format="json")
    assert response.status_code == 200


def test_repeated_wrong_passwords_lock_the_account(api, alice, settings):
    """The gap phase 3 missed entirely. ``login`` needs no session to reach, so it is the
    endpoint an attacker actually hammers."""
    settings.LOGIN_MAX_CONSECUTIVE_ATTEMPTS = 3

    for _ in range(4):
        api.post(LOGIN, {"usr": alice.name, "pwd": "wrong"}, format="json")

    # Even the correct password is now refused.
    response = api.post(LOGIN, {"usr": alice.name, "pwd": "secret123"}, format="json")
    assert response.status_code == 403
    assert response.json()["exc_type"] == "SecurityException"


def test_a_successful_login_resets_the_count(api, alice, settings):
    settings.LOGIN_MAX_CONSECUTIVE_ATTEMPTS = 3

    for _ in range(2):
        api.post(LOGIN, {"usr": alice.name, "pwd": "wrong"}, format="json")
    assert api.post(LOGIN, {"usr": alice.name, "pwd": "secret123"}, format="json").status_code == 200

    for _ in range(2):
        api.post(LOGIN, {"usr": alice.name, "pwd": "wrong"}, format="json")
    # Still under the threshold because the success cleared the earlier pair.
    assert api.post(LOGIN, {"usr": alice.name, "pwd": "secret123"}, format="json").status_code == 200


def test_the_account_key_is_case_insensitive(api, alice, settings):
    """The User PK is the lowercased email, so the tracker key must be too - otherwise
    "Alice@x" and "alice@x" are two budgets for one account."""
    settings.LOGIN_MAX_CONSECUTIVE_ATTEMPTS = 2

    for _ in range(2):
        api.post(LOGIN, {"usr": alice.name, "pwd": "wrong"}, format="json")
    api.post(LOGIN, {"usr": alice.name.upper(), "pwd": "wrong"}, format="json")

    response = api.post(LOGIN, {"usr": alice.name, "pwd": "secret123"}, format="json")
    assert response.status_code == 403


def test_a_disabled_account_does_not_count_as_a_failure(api, make_user, settings):
    """Deliberate: counting it would let anyone lock out a colleague by repeatedly
    "logging in" as them with the right password."""
    settings.LOGIN_MAX_CONSECUTIVE_ATTEMPTS = 2
    user = make_user("off@example.com")
    user.enabled = False
    user.save()

    for _ in range(4):
        response = api.post(LOGIN, {"usr": user.name, "pwd": "secret123"}, format="json")

    assert response.json()["exc_type"] == "AuthenticationError"
    assert LoginAttemptTracker("off@example.com").is_user_allowed() is True


def test_an_unknown_user_still_counts(api, settings):
    """Otherwise username enumeration is free: guessing accounts costs nothing."""
    settings.LOGIN_MAX_CONSECUTIVE_ATTEMPTS = 2
    for _ in range(3):
        api.post(LOGIN, {"usr": "ghost@example.com", "pwd": "x"}, format="json")

    assert LoginAttemptTracker("ghost@example.com").is_user_allowed() is False


# --- change_password -----------------------------------------------------------------


def _auth(api, user):
    tokens = api.post(LOGIN, {"usr": user.name, "pwd": "secret123"}, format="json").json()["message"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return api


def test_change_password_works(api, alice):
    client = _auth(api, alice)
    response = client.post(
        CHANGE_PW, {"old_password": "secret123", "new_password": "N3wPassw0rd!x"}, format="json"
    )
    assert response.status_code == 200


def test_wrong_current_password_eventually_locks(api, alice, settings):
    settings.LOGIN_MAX_CONSECUTIVE_ATTEMPTS = 2
    client = _auth(api, alice)

    for _ in range(3):
        client.post(
            CHANGE_PW, {"old_password": "wrong", "new_password": "N3wPassw0rd!x"}, format="json"
        )

    response = client.post(
        CHANGE_PW, {"old_password": "secret123", "new_password": "N3wPassw0rd!x"}, format="json"
    )
    assert "Too many failed attempts" in str(response.json())


def test_the_endpoint_is_capped_at_five_calls(api, alice):
    """``@rate_limit(5, 300)`` - ``crm/api/user.py:9``.

    Distinct from the lockout: this counts *calls*, not failures, so a caller who always
    sends the right password still trips it.
    """
    client = _auth(api, alice)

    codes = [
        client.post(
            CHANGE_PW,
            {"old_password": "secret123", "new_password": "same-as-before"},
            format="json",
        ).status_code
        for _ in range(7)
    ]

    assert 429 in codes, f"never rate limited: {codes}"


# --- the rate_limit decorator ---------------------------------------------------------


def test_rate_limit_allows_up_to_the_limit(rf):
    calls = []

    @rate_limit(limit=3, seconds=60)
    def endpoint():
        calls.append(1)

    with _ip("10.0.0.1"):
        for _ in range(3):
            endpoint()
    assert len(calls) == 3


def test_rate_limit_raises_past_the_limit(rf):
    @rate_limit(limit=2, seconds=60)
    def endpoint():
        return "ok"

    with _ip("10.0.0.2"):
        endpoint()
        endpoint()
        with pytest.raises(RateLimitExceededError):
            endpoint()


def test_rate_limit_buckets_are_per_ip():
    @rate_limit(limit=1, seconds=60)
    def endpoint():
        return "ok"

    with _ip("10.0.0.3"):
        endpoint()
    with _ip("10.0.0.4"):
        endpoint()  # a different caller must not inherit the first one's count


def test_rate_limit_is_inert_outside_a_request():
    """Direct calls - management commands, tasks, tests - have no IP and must not 500."""

    @rate_limit(limit=1, seconds=60)
    def endpoint():
        return "ok"

    for _ in range(5):
        assert endpoint() == "ok"


# --- client IP resolution -------------------------------------------------------------


def _run_middleware(**meta):
    seen = {}

    def view(request):
        seen["ip"] = get_client_ip()
        return "response"

    request = RequestFactory().get("/", **meta)
    ClientIPMiddleware(view)(request)
    return seen["ip"]


def test_remote_addr_is_used_by_default():
    assert _run_middleware(REMOTE_ADDR="203.0.113.7") == "203.0.113.7"


def test_forwarded_header_is_ignored_when_no_proxy_is_configured(settings):
    """``TRUSTED_PROXY_COUNT = 0`` is the safe default: a client can send any
    ``X-Forwarded-For`` it likes, and honouring it would let an attacker pick a fresh
    rate-limit bucket per request."""
    settings.TRUSTED_PROXY_COUNT = 0
    ip = _run_middleware(REMOTE_ADDR="203.0.113.7", HTTP_X_FORWARDED_FOR="1.2.3.4")
    assert ip == "203.0.113.7"


def test_forwarded_header_is_honoured_behind_one_proxy(settings):
    settings.TRUSTED_PROXY_COUNT = 1
    ip = _run_middleware(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.9")
    assert ip == "203.0.113.9"


# --- helpers ---------------------------------------------------------------------------


class _ip:
    """Bind a client IP for a block, as the middleware does per request."""

    def __init__(self, value):
        self.value = value

    def __enter__(self):
        from frappe_core import security

        self.token = security._client_ip.set(self.value)

    def __exit__(self, *exc):
        from frappe_core import security

        security._client_ip.reset(self.token)
        cache.clear()
