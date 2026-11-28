"""`manage.py restore_defaults [--force]` (specs/CONFIGURATION.md §10.3).

Upstream's `FCRMSettings.restore_defaults(force)`. Puts back every default row that is
missing, as Administrator, in one transaction; never touches a row that is not a default
or a business record. Not gated by `DEV_DATA_ALLOWED`: these rows are not dev data. No
route serves it (§10.4). Output as the old `seed_defaults`
(`backend/crm_app/management/commands/seed_defaults.py:35-37`): one `key: count` line per
writer, then the total; any error rolls everything back and exits non-zero.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.translation import gettext as _

from accounts.models import User
from accounts.roles import ADMINISTRATOR
from core.defaults import RESTORERS


class Command(BaseCommand):
    help = _(
        "Put back the default rows that are missing. --force also rewrites the 14 "
        "default field layouts."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help=_("Delete and write again the 14 default field layouts."),
        )

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                actor = User._default_manager.get(pk=ADMINISTRATOR)
                counts = [
                    (key, writer(actor, bool(options["force"]))) for key, writer in RESTORERS
                ]
        except Exception as exc:  # noqa: BLE001 - every failure rolls back and exits non-zero
            raise CommandError(str(exc) or type(exc).__name__) from exc
        for key, count in counts:
            self.stdout.write(f"{key}: {count}")
        self.stdout.write(
            self.style.SUCCESS(_("{0} row(s) written").format(sum(n for _key, n in counts)))
        )
