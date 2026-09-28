"""``python manage.py seed_defaults [--force]``: upstream's install step, for this port.

Frappe CRM writes its reference rows when ``bench install-app`` runs ``after_install``;
this port has no install step, so the same rows are written here, once, after
``migrate`` (docs/FINDINGS.md 43). ``crm_app.setup`` holds the data and the rules.
"""

from django.core.management.base import BaseCommand

from crm_app.setup import after_install
from frappe_core.session import session_user


class Command(BaseCommand):
    help = (
        "Write the reference rows Frappe CRM's install step writes: lead, deal and "
        "communication statuses, field layouts, industries, lead sources, lost reasons, "
        "quick filters, the user menu, the standard form scripts and the manager "
        "dashboard. Rows that exist are kept, so it is safe to run again."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="rewrite the field layouts and the dashboard even where they exist, "
            "as upstream's restore_defaults does",
        )

    def handle(self, *args, **options):
        # As Administrator, which is who bench runs the install as: every row is
        # stamped with that owner rather than Guest.
        with session_user("Administrator"):
            counts = after_install(force=options["force"])
        for key, count in counts.items():
            self.stdout.write(f"{key}: {count}")
        self.stdout.write(self.style.SUCCESS(f"{sum(counts.values())} row(s) written"))
