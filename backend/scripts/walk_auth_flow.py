"""Gate step 5 — walk the onboarding flow end to end, as a stranger would.

`RUNBOOK_PHASE_8.md`: *"Invite an address, read the link out of the outbox, redeem it, set
a password, log in with it. A green unit suite over a flow nobody walked is exactly what
phase 7 shipped with the Twilio signature — correct, tested, and unreachable in production."*

So this deliberately does **not** import the endpoint functions. It drives real HTTP through
Django's test client, reads the link out of `django.core.mail.outbox` by parsing the email
body, and never touches a key it did not receive by mail. If any URL, parameter name or
status code is wrong, this fails where the unit tests would not.

Run:  backend/.venv/Scripts/python.exe scripts/walk_auth_flow.py

It builds and drops its own test database, so it is safe to run at any time and needs
nothing set up. Committed rather than left in `scratch/` so the check is repeatable by
whoever changes any of this next — the gate step is "walk it and say how", and a script that
only ever existed on one machine says nothing.
"""

import os
import re
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from django.core import mail  # noqa: E402
from django.test.utils import setup_test_environment, teardown_test_environment  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402

STEPS = []


def step(label, ok, detail=""):
    STEPS.append((label, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f"  -- {detail}" if detail else ""))
    return ok


def walk():
    from django.test import Client

    from crm_app.models import CRMInvitation
    from frappe_core.session import session_user
    from frappe_platform.models import User

    client = Client()
    invitee = "newstarter@example.com"

    def post(path, payload):
        return client.post(
            f"/api/method/{path}", payload, content_type="application/json"
        )

    print("\n1. A manager invites an address")
    admin = User.objects.get(name="Administrator")
    # Cleared *before* the create: phase 5 wired `send_invitation_email` to a post_save
    # signal, so the mail goes out as part of creating the row, not as a later step. A
    # first version of this script cleared the outbox afterwards and then called the task
    # by hand — which found an empty outbox, because the real send had already happened and
    # been wiped. The walk is meant to follow what the system does, not what I assumed.
    mail.outbox.clear()
    with session_user("Administrator"):
        invitation = CRMInvitation.objects.create(
            email=invitee, role="Sales User", status="Pending", key="walk-key-001",
            invited_by=admin,
        )
    step("invitation created", CRMInvitation.objects.filter(pk=invitation.pk).exists())

    print("\n2. The invitation email went out on create")
    sent = len(mail.outbox) == 1
    step("one email sent", sent, mail.outbox[0].to[0] if sent else "none")
    if not sent:
        return

    body = mail.outbox[0].body
    invite_match = re.search(r"key=([^\s]+)", body)
    step("email contains an accept link", bool(invite_match))
    if not invite_match:
        print(body)
        return
    invite_key = invite_match.group(1)
    step("the key came from the email, not the API", invite_key == "walk-key-001")

    # The phase-8 review caught this and this walk did not: the link went to
    # `/api/method/crm.api.accept_invitation`, which answers with JSON, so an invitee
    # clicking it landed on raw JSON. The walk followed the *endpoint* rather than the
    # *URL a person clicks*, which is the same gap in a smaller frame.
    step("the link is a page, not the JSON API", "/api/method/" not in body, body.strip())
    step("the link points at the SPA accept page", "/crm/accept-invitation?key=" in body)

    print("\n3. The invitee redeems it")
    response = post("crm.api.accept_invitation", {"key": invite_key})
    ok = response.status_code == 200
    step("accept_invitation answers 200", ok, f"status {response.status_code}")
    if not ok:
        print(response.content[:400])
        return

    payload = response.json()["message"]
    step("a new account is asked to set a password", payload.get("status") == "set_password")
    step("the account now exists", User.objects.filter(pk=invitee).exists())
    account = User.objects.get(pk=invitee)
    step("the account has no usable password yet", not account.has_usable_password())
    step("the role was granted", "Sales User" in account.get_roles())

    print("\n4. The set-password link points into the app")
    redirect_to = payload.get("redirect_to", "")
    step("link is a frontend route", "/crm/update-password?key=" in redirect_to, redirect_to)
    reset_key = redirect_to.split("key=")[1] if "key=" in redirect_to else ""

    print("\n5. They choose a password")
    response = post(
        "frappe.core.doctype.user.user.update_password",
        {"key": reset_key, "new_password": "W4lkThe!Flow99"},
    )
    ok = response.status_code == 200
    step("update_password answers 200", ok, f"status {response.status_code}")
    if not ok:
        print(response.content[:400])
        return
    tokens = response.json()["message"]
    step("it returns a token pair", bool(tokens.get("access") and tokens.get("refresh")))
    step("the token names the invitee", tokens.get("user") == invitee)

    print("\n6. They log in with it")
    response = post("login", {"usr": invitee, "pwd": "W4lkThe!Flow99"})
    ok = response.status_code == 200
    step("login answers 200", ok, f"status {response.status_code}")
    if ok:
        step("login returns the same shape", set(tokens) == set(response.json()["message"]))

    print("\n7. The token actually works against a real endpoint")
    access = response.json()["message"]["access"] if ok else ""
    whoami = client.get(
        "/api/method/frappe.auth.get_logged_user", HTTP_AUTHORIZATION=f"Bearer {access}"
    )
    step(
        "get_logged_user recognises them",
        whoami.status_code == 200 and whoami.json().get("message") == invitee,
        f"status {whoami.status_code}",
    )

    print("\n8. The links are dead now")
    again = post("crm.api.accept_invitation", {"key": invite_key})
    step("the invitation cannot be redeemed twice", again.status_code != 200,
         f"status {again.status_code}")
    again = post(
        "frappe.core.doctype.user.user.update_password",
        {"key": reset_key, "new_password": "An0ther!Passw0rd"},
    )
    step("the reset key cannot be reused", again.status_code == 410,
         f"status {again.status_code}")

    print("\n9. Forgot password, for the account we just made")
    from django.core.cache import cache

    cache.clear()
    mail.outbox.clear()
    response = post("frappe.core.doctype.user.user.reset_password", {"user": invitee})
    step("reset_password answers 200", response.status_code == 200)
    step("an email was sent", len(mail.outbox) == 1)
    if mail.outbox:
        link = re.search(r"key=([^\s]+)", mail.outbox[0].body)
        step("it carries a reset link", bool(link))
        if link:
            response = post(
                "frappe.core.doctype.user.user.update_password",
                {"key": link.group(1), "new_password": "S3condTime!Round"},
            )
            step("the emailed reset link works", response.status_code == 200,
                 f"status {response.status_code}")
            response = post("login", {"usr": invitee, "pwd": "S3condTime!Round"})
            step("the new password logs in", response.status_code == 200)

    print("\n10. An unknown address answers identically")
    cache.clear()
    mail.outbox.clear()
    known = post("frappe.core.doctype.user.user.reset_password", {"user": invitee})
    cache.clear()
    unknown = post(
        "frappe.core.doctype.user.user.reset_password", {"user": "ghost@example.com"}
    )
    step(
        "same status and body for known and unknown",
        (known.status_code, known.content) == (unknown.status_code, unknown.content),
    )


def main():
    setup_test_environment()
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old_config = runner.setup_databases()
    try:

        # `builtin_users` is a pytest fixture, so seed the two rows by hand here.
        from frappe_platform.models import User

        for name in ("Administrator", "Guest"):
            User.objects.get_or_create(
                name=name,
                defaults={
                    "email": f"{name.lower()}@example.com",
                    "first_name": name,
                    "full_name": name,
                    "enabled": True,
                    "user_type": "System User",
                },
            )
        walk()
    finally:
        runner.teardown_databases(old_config)
        teardown_test_environment()

    failed = [s for s in STEPS if not s[1]]
    print(f"\n{len(STEPS) - len(failed)} of {len(STEPS)} steps passed")
    if failed:
        print("FAILED:")
        for label, _, detail in failed:
            print(f"  - {label} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
