"""The named seam where `frappe_whatsapp` would take over.

Phase 5's `_reconcile_products` is the pattern: a real function with a real signature that
raises when the flag is on and nothing is behind it, so the control flow around it can be
tested without the provider existing.

**Why raise rather than return quietly.** A flag that is on with no provider is a
configuration error. Returning success would mean a user sees their message in the timeline,
marked as sent, and the recipient never receives it — a silent failure at the worst possible
place. The same reasoning phase 5 applied to the lead-sync tasks.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    """`whatsapp.py:91-102` — upstream asks whether a default outgoing account is Active.

    There is no `WhatsApp Settings` doctype here, so the deployment flag is the whole
    answer. It is the outer gate in every other integration too (divergence #22); WhatsApp
    simply has no inner one to `and` with.
    """
    from django.conf import settings

    return bool(getattr(settings, "ENABLE_WHATSAPP", False))


def is_installed() -> bool:
    """`whatsapp.py:105-109` — upstream checks whether the `frappe_whatsapp` app exists.

    Here it means "is a provider configured", which is the same question the frontend is
    asking: it uses this to decide whether to render the WhatsApp tab at all.
    """
    return is_enabled()


def send_message(message) -> dict:
    """Hand one `WhatsApp Message` to the provider. **The seam.**

    A real implementation posts to Meta's Cloud API and writes back the provider's
    `message_id` and `status`. Phase 7 has no provider, so this refuses loudly when the
    flag is on.
    """
    raise NotImplementedError(
        "WhatsApp sending needs a provider; ENABLE_WHATSAPP is on but none is configured"
    )


def render_template(template_name: str, parameters: list | None = None) -> str | None:
    """`whatsapp.py:186-215` — the other half of what `frappe_whatsapp` owns.

    Templates are stored in that app. Returning ``None`` means "no rendered body available",
    and `get_whatsapp_messages` leaves the message unenriched rather than inventing one.
    """
    return None


def parse_template_parameters(string: str, parameters: list) -> str:
    """`whatsapp.py:344-349`.

    Ported even though templates are not, because it is pure string substitution with no
    dependency on the provider — and it is what a future provider implementation will need.
    """
    for index, parameter in enumerate(parameters or [], start=1):
        string = string.replace("{{" + str(index) + "}}", str(parameter))
    return string
