"""Walk the onboarding flow end to end, as a stranger would (ACCOUNTS spec section 5).

The equivalent of `backend/scripts/walk_auth_flow.py` for backend_v2: invite an address,
read the link out of the outbox, redeem it, set a password, log in with it, then forgot
password. It does not import the endpoint functions: it drives real HTTP through Django's
test client and never touches a key it did not receive by mail. The invitation is made the
only way one can be (PE-8): a System Manager's invite-by-email.

Run:  backend_v2/.venv/Scripts/python.exe scripts/walk_auth_flow.py
It builds and drops its own test database. `tests/test_walk_auth_flow.py` runs the same
walk under pytest.
"""

from __future__ import annotations

import os
import re
import sys

STEPS: list[tuple[str, bool, str]] = []
INVITEE = "newstarter@example.com"
MANAGER = "walk.manager@example.com"
MANAGER_PASSWORD = "W4lk!Manager-pass"


def step(label, ok, detail=""):
    STEPS.append((label, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {detail}" if detail else ""))
    return ok


def walk() -> list[tuple[str, bool, str]]:
    """Run the walk against the current database; answers the steps."""
    from django.core import mail
    from django.core.cache import cache
    from django.test import Client, override_settings

    from accounts.models import CRMInvitation, User

    STEPS.clear()
    client = Client()

    def post(path, payload, **extra):
        return client.post(path, payload, content_type="application/json", **extra)

    # A carrier for the two emails: the config account, sending to the locmem outbox.
    with override_settings(EMAIL_HOST="smtp.walk.test"):
        print("\n1. A System Manager invites an address through invite-by-email")
        from django.contrib.auth.models import Group

        manager = User.objects.create_user(MANAGER, password=MANAGER_PASSWORD)
        manager.groups.add(Group.objects.get_or_create(name="System Manager")[0])
        login = post("/api/v1/auth/login/", {"usr": MANAGER, "pwd": MANAGER_PASSWORD})
        manager_token = login.json()["message"]["access"] if login.status_code == 200 else ""
        mail.outbox.clear()
        response = post(
            "/api/v1/invitations/invite-by-email/",
            {"emails": INVITEE, "role": "Sales User"},
            HTTP_AUTHORIZATION=f"Bearer {manager_token}",
        )
        if not step("invite-by-email answers 200", response.status_code == 200, f"status {response.status_code}"):
            return list(STEPS)
        step("it invited the address", response.json()["message"]["to_invite"] == [INVITEE])

        print("\n2. The invitation email went out on create")
        if not step("one email sent", len(mail.outbox) == 1):
            return list(STEPS)
        body = mail.outbox[0].body
        invite_match = re.search(r"key=(\S+)", body)
        if not step("email contains an accept link", bool(invite_match)):
            return list(STEPS)
        invite_key = invite_match.group(1)
        stored = CRMInvitation.objects.get(email=INVITEE)
        step("the key came only from the email", invite_key == stored.key and invite_key not in response.content.decode())
        step("the link is a page, not the JSON API", "/api/" not in body)
        step("the link points at the SPA accept page", "/crm/accept-invitation?key=" in body)

        print("\n3. The invitee redeems it")
        response = post("/api/v1/auth/accept-invitation/", {"key": invite_key})
        if not step("accept answers 200", response.status_code == 200, f"status {response.status_code}"):
            return list(STEPS)
        payload = response.json()["message"]
        step("a new account is asked to set a password", payload.get("status") == "set_password")
        account = User.objects.get(pk=INVITEE)
        step("the account has no usable password yet", not account.has_usable_password())
        step("the role was granted", "Sales User" in account.get_roles())

        print("\n4. The set-password link points into the app")
        redirect_to = payload.get("redirect_to", "")
        step("link is a frontend route", "/crm/update-password?key=" in redirect_to, redirect_to)
        reset_key = redirect_to.split("key=")[1] if "key=" in redirect_to else ""

        print("\n5. They choose a password")
        response = post(
            "/api/v1/auth/update-password/", {"key": reset_key, "new_password": "W4lkThe!Flow99"}
        )
        if not step("update-password answers 200", response.status_code == 200, f"status {response.status_code}"):
            return list(STEPS)
        tokens = response.json()["message"]
        step("it returns a token pair", bool(tokens.get("access") and tokens.get("refresh")))
        step("the token names the invitee", tokens.get("user") == INVITEE)

        print("\n6. They log in with it")
        response = post("/api/v1/auth/login/", {"usr": INVITEE, "pwd": "W4lkThe!Flow99"})
        ok = step("login answers 200", response.status_code == 200, f"status {response.status_code}")
        if ok:
            step("login returns the same shape", set(tokens) == set(response.json()["message"]))

        print("\n7. The token works against a real endpoint")
        access = response.json()["message"]["access"] if ok else ""
        whoami = client.get("/api/v1/auth/me/", HTTP_AUTHORIZATION=f"Bearer {access}")
        step(
            "auth/me recognises them",
            whoami.status_code == 200 and whoami.json().get("message") == INVITEE,
            f"status {whoami.status_code}",
        )

        print("\n8. The links are dead now")
        again = post("/api/v1/auth/accept-invitation/", {"key": invite_key})
        step("the invitation cannot be redeemed twice", again.status_code != 200, f"status {again.status_code}")
        again = post(
            "/api/v1/auth/update-password/", {"key": reset_key, "new_password": "An0ther!Passw0rd"}
        )
        step("the reset key cannot be reused", again.status_code == 410, f"status {again.status_code}")

        print("\n9. Forgot password, for the account just made")
        cache.clear()
        mail.outbox.clear()
        response = post("/api/v1/auth/reset-password/", {"user": INVITEE})
        step("reset-password answers 200", response.status_code == 200)
        step("an email was sent", len(mail.outbox) == 1)
        if mail.outbox:
            link = re.search(r"key=(\S+)", mail.outbox[0].body)
            if step("it carries a reset link", bool(link)):
                response = post(
                    "/api/v1/auth/update-password/",
                    {"key": link.group(1), "new_password": "S3condTime!Round"},
                )
                step("the emailed reset link works", response.status_code == 200, f"status {response.status_code}")
                response = post("/api/v1/auth/login/", {"usr": INVITEE, "pwd": "S3condTime!Round"})
                step("the new password logs in", response.status_code == 200)

        print("\n10. An unknown address answers identically")
        cache.clear()
        known = post("/api/v1/auth/reset-password/", {"user": INVITEE})
        cache.clear()
        unknown = post("/api/v1/auth/reset-password/", {"user": "ghost@example.com"})
        step(
            "same status and body for known and unknown",
            (known.status_code, known.content) == (unknown.status_code, unknown.content),
        )
    return list(STEPS)


def main() -> int:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
    import django

    django.setup()
    from django.test.runner import DiscoverRunner
    from django.test.utils import setup_test_environment, teardown_test_environment

    setup_test_environment()
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old_config = runner.setup_databases()
    try:
        steps = walk()
    finally:
        runner.teardown_databases(old_config)
        teardown_test_environment()
    failed = [s for s in steps if not s[1]]
    print(f"\n{len(steps) - len(failed)} of {len(steps)} steps passed")
    for label, _, detail in failed:
        print(f"  - {label} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
