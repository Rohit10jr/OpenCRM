"""Remove only rows written by :mod:`seed_dev_data`."""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.translation import gettext as _

from accounts.models import User
from accounts.roles import ADMINISTRATOR
from core.dev_data import STEPS


class Command(BaseCommand):
    help = _("Remove only rows written by seed_dev_data.")

    @transaction.atomic
    def handle(self, *args, **options):
        actor = User.objects.get(name=ADMINISTRATOR)
        counts = {step.key: step.clear(actor, False) for step in reversed(STEPS)}
        for key, count in counts.items():
            self.stdout.write(_("{0}: {1}").format(key, count))
        self.stdout.write(
            self.style.SUCCESS(
                _("{0} row(s) removed").format(sum(counts.values()))
            )
        )
