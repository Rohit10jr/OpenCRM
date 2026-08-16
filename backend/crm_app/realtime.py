"""The realtime publish seam — ``frappe.publish_realtime``'s counterpart.

Created in **phase 5** because the product-reconciliation task has to emit
``crm_product_sync_complete`` and needed somewhere to emit it *to*. **Phase 6** fills in
the transport (`PHASE_6_REALTIME.md` §3: *"one function mirroring
`frappe.publish_realtime(event, user=...)` so Celery tasks and model signals call the
same thing"*).

Until then this records the call and drops it. That is deliberate: the app must work
with Channels switched off (`PHASE_6_REALTIME.md` §4's last criterion), so publishing
can never be load-bearing.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def publish(event: str, user: str | None = None, message=None) -> bool:
    """Publish ``event``, to ``user`` if given, otherwise broadcast.

    Returns True when a transport actually delivered it. Phase 5 always returns False —
    there is no transport yet — which is why no caller may depend on the return value
    for correctness.
    """
    logger.debug("realtime event %s (user=%s) dropped: no transport", event, user)
    return False
