"""``python manage.py refresh_exchange_rates``: give saved deals and organizations their rate.

Upstream sets a deal's and an organization's ``exchange_rate`` on every save from the day
the record is created (``crm_deal.py:102,273-280``, ``crm_organization.py:31-41``), so no
upstream row is without one. This port did not until docs/FINDINGS.md 63: a deal saved
before then holds 1 whatever its currency, and an organization holds nothing. The rule
recomputes only when the currency changes or no rate is held, so those deals would count
at face value on the dashboard for good.

This writes the rate upstream would have written: 1 for a record in the dashboard
currency (FCRM Settings, USD when none is set), the provider's rate today otherwise, one
call per currency. It writes the column alone, as upstream's ``db_set`` does, so nothing
else about the record changes. Run it once after ``migrate``. With
``ENABLE_EXCHANGE_RATE_API`` off every rate is 1, as on save.

A migration does not do this because it would call the internet during ``migrate``.
"""

from django.core.management.base import BaseCommand

from crm_app.api.exchange_rate import get_exchange_rate
from crm_app.models import CRMDeal, CRMOrganization, FCRMSettings
from frappe_core.exceptions import FrappeError
from frappe_core.session import session_user


class Command(BaseCommand):
    help = (
        "Set exchange_rate on every deal and organization from its currency and the "
        "dashboard currency, as upstream sets it on save."
    )

    def handle(self, *args, **options):
        system_currency = (
            FCRMSettings._default_manager.values_list("currency", flat=True).first() or "USD"
        )
        rates: dict[str, float] = {}
        failed: set[str] = set()
        with session_user("Administrator"):
            for model in (CRMDeal, CRMOrganization):
                manager = model._default_manager
                currencies = set(
                    manager.exclude(currency="").values_list("currency", flat=True).distinct()
                )
                written = manager.filter(currency="").exclude(exchange_rate=1).update(exchange_rate=1)
                for currency in sorted(currencies):
                    if currency == system_currency:
                        rate = 1
                    elif currency in rates:
                        rate = rates[currency]
                    elif currency in failed:
                        continue
                    else:
                        try:
                            rate = rates[currency] = get_exchange_rate(currency, system_currency)
                        except FrappeError as error:
                            failed.add(currency)
                            self.stderr.write(f"{currency} -> {system_currency}: {error}")
                            continue
                    written += manager.filter(currency=currency).update(exchange_rate=rate)
                self.stdout.write(f"{model.get_doctype()}: {written} row(s) written")
        if failed:
            self.stderr.write(
                self.style.WARNING(f"no rate for {', '.join(sorted(failed))}; those rows are unchanged")
            )
        self.stdout.write(self.style.SUCCESS(f"dashboard currency {system_currency}"))
