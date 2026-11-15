"""Remove only rows written by :mod:`seed_dev_data`."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.translation import gettext as _

from accounts.models import User
from accounts.roles import ADMINISTRATOR
from core.dev_data import STEPS


class Command(BaseCommand):
    help = _("Remove only rows written by seed_dev_data.")

    def handle(self, *args, **options):
        if not getattr(settings, "DEV_DATA_ALLOWED", False):
            raise CommandError(
                _(
                    "clear_dev_data refuses to run: DEV_DATA_ALLOWED is not set. "
                    "These commands reset and delete users; enable it only for a "
                    "development database."
                )
            )
        with transaction.atomic():
            actor = User.objects.get(name=ADMINISTRATOR)
            counts = {
                step.key: step.clear(actor, False) for step in reversed(STEPS)
            }
            for key, count in counts.items():
                self.stdout.write(_("{0}: {1}").format(key, count))
            self.stdout.write(
                self.style.SUCCESS(
                    _("{0} row(s) removed").format(sum(counts.values()))
                )
            )
