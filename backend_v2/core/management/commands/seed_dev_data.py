"""Seed the development rows needed by browser and HTTP tests."""

from django.core.management.base import BaseCommand
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

    @transaction.atomic
    def handle(self, *args, **options):
        actor = User.objects.get(name=ADMINISTRATOR)
        counts = {step.key: step.seed(actor, options["force"]) for step in STEPS}
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
