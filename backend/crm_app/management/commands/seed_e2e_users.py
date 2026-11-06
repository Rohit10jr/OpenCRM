"""``python manage.py seed_e2e_users``: the accounts the Playwright suite signs in with.

Port only: upstream has no equivalent; its browser tests run against a site whose users
already exist. The suite (``frontend/tests/e2e/users.js``) signs in as Administrator
and as ``ada@example.com``, a Sales User, with the passwords in ``ADMIN_PWD`` and
``SALES_PWD``. A fresh database has neither: migration 0002 creates Administrator with
an unusable password, and nothing creates ada. The CI workflow
(``.github/workflows/e2e.yml``) runs this after ``migrate`` and ``seed_defaults``.

It sets passwords from the environment, so run it only against a database whose
Administrator password you mean to replace.
"""

import os

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from frappe_platform.models import User

SALES_USER = "ada@example.com"


class Command(BaseCommand):
    help = (
        "Give Administrator the password in ADMIN_PWD and create or reset "
        f"{SALES_USER} as a Sales User with the password in SALES_PWD, for the "
        "Playwright suite. Safe to run again."
    )

    def handle(self, *args, **options):
        missing = [key for key in ("ADMIN_PWD", "SALES_PWD") if not os.environ.get(key)]
        if missing:
            raise CommandError(f"Set {' and '.join(missing)} in the environment first.")

        admin = User.objects.get(name="Administrator")
        admin.set_password(os.environ["ADMIN_PWD"])
        admin.save()

        ada = User.objects.filter(name=SALES_USER).first()
        if ada is None:
            ada = User.objects.create_user(
                name=SALES_USER, email=SALES_USER, first_name="Ada", enabled=True
            )
        ada.enabled = True
        ada.set_password(os.environ["SALES_PWD"])
        ada.save()
        # Sales User only: with Sales Manager or System Manager as well, the session's
        # role is the higher one and roles.spec.js would see the Edit button.
        sales_user, _ = Group.objects.get_or_create(name="Sales User")
        ada.groups.set([sales_user])

        self.stdout.write(self.style.SUCCESS(f"Administrator and {SALES_USER} are ready"))
