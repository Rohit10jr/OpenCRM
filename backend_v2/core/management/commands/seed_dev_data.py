"""Seed the development rows needed by browser and HTTP tests."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.translation import gettext as _

from accounts.models import User
from accounts.roles import ADMINISTRATOR
from core.dev_data import STEPS


class Command(BaseCommand):
    help = _(
        "Write development reference rows. Rows that exist are kept, so it is safe "
        "to run again."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help=_("Rewrite restorable upstream defaults where later units allow it."),
        )
        parser.add_argument(
            "--demo",
            action="store_true",
            help=_(
                "Add upstream's demo records from crm/demo/ once their units exist."
            ),
        )

    def handle(self, *args, **options):
        if not getattr(settings, "DEV_DATA_ALLOWED", False):
            raise CommandError(
                _(
                    "seed_dev_data refuses to run: DEV_DATA_ALLOWED is not set. "
                    "These commands reset and delete users; enable it only for a "
                    "development database."
                )
            )
        with transaction.atomic():
            actor = User.objects.get(name=ADMINISTRATOR)
            counts = {
                step.key: step.seed(actor, options["force"]) for step in STEPS
            }
            for step in STEPS:
                self.stdout.write(
                    _("{0}: {1} created, {2} reset").format(
                        step.key, counts[step.key], step.reset_count
                    )
                )
            if options["demo"]:
                self.stdout.write(_("Demo records are not available yet."))
            self.stdout.write(
                self.style.SUCCESS(
                    _("{0} row(s) created").format(sum(counts.values()))
                )
            )
