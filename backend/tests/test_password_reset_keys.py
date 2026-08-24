"""Password-reset keys — the mechanism, before any endpoint uses it.

Ports `frappe/core/doctype/user/user.py:383`, `:945` and `:828`. These tests are written
against the *semantics* upstream defines, not against my implementation of them, so a
rewrite that keeps the semantics keeps the tests.

The three properties that matter, and why each has its own test:

* **Hashed at rest** — a database dump must yield nothing redeemable.
* **Single use** — redeemed once, dead.
* **Two messages, and only two** — "used" and "never existed" are deliberately merged, so a
  key cannot be probed for existence.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

import pytest
from django.utils import timezone

from frappe_core import password_reset

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Issuing
# ---------------------------------------------------------------------------


def test_the_raw_key_is_never_stored(alice):
    """`user.py:385-387` — `sha256_hash(key)` in the row, the raw value only in the link.

    The property a database dump has to run into.
    """
    from frappe_platform.models import User

    raw = password_reset.issue_key(alice)
    stored = User.objects.values_list("reset_password_key", flat=True).get(pk=alice.pk)

    assert stored != raw
    assert stored == hashlib.sha256(raw.encode()).hexdigest()


def test_the_key_has_real_entropy(alice):
    """A guessable key is a password reset for anyone who guesses it."""
    keys = {password_reset.issue_key(alice) for _ in range(20)}
    assert len(keys) == 20
    assert all(len(k) >= 32 for k in keys)


def test_issuing_a_second_key_kills_the_first(alice):
    """One column, so one live link — upstream's behaviour and the right one.

    "I didn't get the email, send another" must not leave two working links.
    """
    first = password_reset.issue_key(alice)
    second = password_reset.issue_key(alice)

    assert password_reset.resolve_key(first).message == password_reset.INVALID_MESSAGE
    assert password_reset.resolve_key(second).ok


def test_the_issue_time_is_recorded(alice):
    """Expiry is measured from it, so a key without one cannot be aged."""
    from frappe_platform.models import User

    password_reset.issue_key(alice)
    issued = User.objects.values_list(
        "last_reset_password_key_generated_on", flat=True
    ).get(pk=alice.pk)
    assert issued is not None


def test_issuing_does_not_run_the_user_save_path(alice):
    """It is called from an unauthenticated endpoint where the ambient user is Guest.

    Upstream uses `db_set` for the same reason; a full `save()` would re-stamp `modified`
    fields with whoever the request happens to be.
    """
    from frappe_platform.models import User

    before = User.objects.values_list("modified", flat=True).get(pk=alice.pk)
    password_reset.issue_key(alice)
    after = User.objects.values_list("modified", flat=True).get(pk=alice.pk)
    assert after == before


# ---------------------------------------------------------------------------
# Resolving — the two messages, and only two
# ---------------------------------------------------------------------------


def test_a_fresh_key_resolves_to_its_user(alice):
    raw = password_reset.issue_key(alice)
    result = password_reset.resolve_key(raw)

    assert result.ok
    assert result.user.pk == alice.pk
    assert result.message is None


def test_a_key_that_never_existed_is_invalid(db):
    result = password_reset.resolve_key("not-a-real-key")
    assert result.message == password_reset.INVALID_MESSAGE
    assert result.user is None


def test_an_empty_key_is_invalid(db):
    assert password_reset.resolve_key("").message == password_reset.INVALID_MESSAGE
    assert password_reset.resolve_key(None).message == password_reset.INVALID_MESSAGE


def test_an_expired_key_says_so(alice, settings):
    """The one case that gets its own message: a real user's real problem, and telling them
    to request another is the whole job."""
    from frappe_platform.models import User

    raw = password_reset.issue_key(alice)
    User.objects.filter(pk=alice.pk).update(
        last_reset_password_key_generated_on=timezone.now() - timedelta(minutes=61)
    )

    assert password_reset.resolve_key(raw).message == password_reset.EXPIRED_MESSAGE


def test_a_key_just_inside_the_window_still_works(alice):
    from frappe_platform.models import User

    raw = password_reset.issue_key(alice)
    User.objects.filter(pk=alice.pk).update(
        last_reset_password_key_generated_on=timezone.now() - timedelta(minutes=59)
    )

    assert password_reset.resolve_key(raw).ok


def test_a_used_key_is_indistinguishable_from_one_that_never_existed(alice):
    """**The point of merging the two messages.**

    If a redeemed key answered differently from a fabricated one, an attacker could ask the
    endpoint whether any given key had ever been issued. Clearing the key on use is what
    makes the two look the same, and the shared message is what keeps them that way.
    """
    raw = password_reset.issue_key(alice)
    password_reset.consume_key(alice)

    used = password_reset.resolve_key(raw)
    never_existed = password_reset.resolve_key("fabricated-key-value")

    assert used.message == never_existed.message == password_reset.INVALID_MESSAGE


def test_there_are_exactly_two_failure_messages():
    """A third message is a third thing an attacker can distinguish. Upstream has two; the
    spec says two; this fails if someone adds a helpful one."""
    import inspect

    source = inspect.getsource(password_reset)
    messages = [
        line for line in source.splitlines()
        if line.startswith(("EXPIRED_MESSAGE", "INVALID_MESSAGE"))
    ]
    assert len(messages) == 2


def test_the_messages_are_upstreams_wording():
    """User-facing copy — `CLAUDE.md` rule 4 keeps `frappe.throw` text verbatim."""
    assert password_reset.EXPIRED_MESSAGE == "The reset password link has been expired"
    assert password_reset.INVALID_MESSAGE == (
        "The reset password link has either been used before or is invalid"
    )


def test_a_key_with_no_issue_time_is_refused(alice):
    """Failure direction has to be "refuse".

    A row with a key and no timestamp cannot be aged, so treating it as valid would make it
    a permanent link — the exact thing the zero-means-an-hour rule exists to prevent.
    """
    from frappe_platform.models import User

    raw = password_reset.issue_key(alice)
    User.objects.filter(pk=alice.pk).update(last_reset_password_key_generated_on=None)

    assert password_reset.resolve_key(raw).message == password_reset.INVALID_MESSAGE


# ---------------------------------------------------------------------------
# Expiry configuration — zero means an hour
# ---------------------------------------------------------------------------


def test_the_default_is_one_hour(settings):
    assert password_reset.expiry_minutes() == 60


def test_zero_means_one_hour_not_forever(settings):
    """**Divergence #34.** Upstream's `reset_password_link_expiry_duration` treats 0 as
    "disable the expiry check", which makes a forwarded or archived email a permanent
    credential. Zero is redefined here rather than reproduced."""
    settings.PASSWORD_RESET_LINK_EXPIRY_MINUTES = 0
    assert password_reset.expiry_minutes() == 60


def test_a_zero_setting_still_expires_a_key(alice, settings):
    """The setting is one thing; the behaviour is the one that matters."""
    from frappe_platform.models import User

    settings.PASSWORD_RESET_LINK_EXPIRY_MINUTES = 0
    raw = password_reset.issue_key(alice)
    User.objects.filter(pk=alice.pk).update(
        last_reset_password_key_generated_on=timezone.now() - timedelta(hours=2)
    )

    assert password_reset.resolve_key(raw).message == password_reset.EXPIRED_MESSAGE


def test_a_negative_or_junk_setting_falls_back(settings):
    settings.PASSWORD_RESET_LINK_EXPIRY_MINUTES = -5
    assert password_reset.expiry_minutes() == 60

    settings.PASSWORD_RESET_LINK_EXPIRY_MINUTES = "not a number"
    assert password_reset.expiry_minutes() == 60


def test_a_custom_expiry_is_honoured(alice, settings):
    from frappe_platform.models import User

    settings.PASSWORD_RESET_LINK_EXPIRY_MINUTES = 5
    raw = password_reset.issue_key(alice)
    User.objects.filter(pk=alice.pk).update(
        last_reset_password_key_generated_on=timezone.now() - timedelta(minutes=6)
    )

    assert password_reset.resolve_key(raw).message == password_reset.EXPIRED_MESSAGE


# ---------------------------------------------------------------------------
# Consuming
# ---------------------------------------------------------------------------


def test_a_consumed_key_is_dead_even_with_a_fresh_timestamp(alice):
    """Single use, isolated from the expiry guard.

    Mutation-checked, and the first attempt was not enough: clearing the *timestamp* alone
    already makes `resolve_key` refuse, so a mutation that left the key in place still
    looked correct. This restores a fresh timestamp after consuming, so the only thing that
    can refuse the key is the key having been cleared.
    """
    from frappe_platform.models import User

    raw = password_reset.issue_key(alice)
    password_reset.consume_key(alice)
    User.objects.filter(pk=alice.pk).update(
        last_reset_password_key_generated_on=timezone.now()
    )

    assert password_reset.resolve_key(raw).message == password_reset.INVALID_MESSAGE


def test_consuming_clears_both_columns(alice):
    from frappe_platform.models import User

    password_reset.issue_key(alice)
    password_reset.consume_key(alice)

    row = User.objects.values("reset_password_key", "last_reset_password_key_generated_on").get(
        pk=alice.pk
    )
    assert row["reset_password_key"] == ""
    assert row["last_reset_password_key_generated_on"] is None


# ---------------------------------------------------------------------------
# The key never reaches the wire
# ---------------------------------------------------------------------------


def test_the_stored_key_is_not_selectable():
    from frappe_core.field_security import sensitive_fields
    from frappe_platform.models import User

    assert "reset_password_key" in sensitive_fields(User)


def test_the_issue_time_is_hidden_too(alice, auth_api):
    """It is not a credential, and it is hidden anyway.

    `User` reads are open to every authenticated caller (`SECURITY_MODEL.md` divergence #5 —
    kanban builds a column per user). A visible issue timestamp would tell any colleague
    which accounts have a live reset link and when it was issued: the window an attacker
    with mailbox access wants, and nobody else's business.

    `test_credential_fields.py` flagged it on the name alone, which is the heuristic working
    — but the reason to hide it is not the name.
    """
    from frappe_core.field_security import sensitive_fields
    from frappe_platform.models import User

    assert "last_reset_password_key_generated_on" in sensitive_fields(User)

    password_reset.issue_key(alice)
    response = auth_api.get(f"/api/resource/User/{alice.pk}")
    assert "last_reset_password_key_generated_on" not in response.json()["data"]


def test_the_stored_key_cannot_be_filtered_on(alice, auth_api):
    """A filterable hash is a hash that can be probed one character at a time — the `like`
    attack that recovered a real SMTP password from this codebase."""
    password_reset.issue_key(alice)

    response = auth_api.get(
        "/api/resource/User",
        {"filters": '[["reset_password_key","like","a%"]]'},
    )

    # `FilterError` -> 400. Asserting the *rejection* rather than a status code I guessed:
    # the property is that the query never runs and the answer carries no information about
    # any key.
    assert response.status_code == 400, response.content[:300]
    assert "Cannot filter on" in response.json()["message"]
    assert "data" not in response.json()


def test_the_stored_key_is_absent_from_a_user_response(alice, auth_api):
    response = auth_api.get(f"/api/resource/User/{alice.pk}")
    assert response.status_code == 200
    assert "reset_password_key" not in response.json()["data"]


# ---------------------------------------------------------------------------
# The link
# ---------------------------------------------------------------------------


def test_the_link_points_into_the_vue_app(settings):
    """`PHASE_8_AUTH_AND_DESK.md`: the pages live inside the SPA. Upstream's
    `/update-password` is a Jinja page on the same origin; ours is a frontend route."""
    settings.FRONTEND_ORIGIN = "https://crm.example.com"
    link = password_reset.reset_link("abc123")

    assert link == "https://crm.example.com/crm/update-password?key=abc123"


def test_the_link_carries_the_raw_key_not_the_hash(alice, settings):
    settings.FRONTEND_ORIGIN = "https://crm.example.com"
    raw = password_reset.issue_key(alice)
    link = password_reset.reset_link(raw)

    assert raw in link
    assert hashlib.sha256(raw.encode()).hexdigest() not in link
