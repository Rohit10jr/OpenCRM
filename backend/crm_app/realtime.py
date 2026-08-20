"""The realtime publish seam — ``frappe.publish_realtime``'s counterpart.

Created in **phase 5** because the product-reconciliation task had to emit
``crm_product_sync_complete`` and needed somewhere to emit it *to*. **Phase 6** filled in
the transport (`PHASE_6_REALTIME.md` §3: *"one function mirroring
`frappe.publish_realtime(event, user=...)` so Celery tasks and model signals call the
same thing"*).

**Publishing is never load-bearing** (`PHASE_6_REALTIME.md` §4, last criterion: *"Nothing
in the app breaks when Channels is switched off — realtime is an enhancement, never a
correctness dependency"*). Every failure path here returns ``False`` and logs; none
raises. A caller that branched on the return value to decide whether a write happened
would be reintroducing exactly the dependency that criterion forbids.

Group naming is in one place, :func:`user_group` / :func:`doc_group`, because the
publisher and the consumer have to agree and there is no way to notice that they do not:
a mismatched name is not an error, it is silence.
"""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

#: The message type the consumer handles. Channels turns ``{"type": "realtime.event"}``
#: into a call to ``RealtimeConsumer.realtime_event``.
MESSAGE_TYPE = "realtime.event"

#: Everyone connected. ``crm_customer_created`` (phase 7) is the broadcast case.
BROADCAST_GROUP = "crm_broadcast"


def user_group(user: str) -> str:
    """`PHASE_6_REALTIME.md` §3 — ``user_<email_hash>``.

    Hashed, not because the email is a secret, but because Channels group names are
    restricted to ASCII alphanumerics, hyphens, underscores and periods and are capped at
    100 characters. ``o'brien+crm@example.co.uk`` is a legal Frappe user PK and an illegal
    group name.
    """
    return "user_" + hashlib.sha256(user.encode("utf-8")).hexdigest()[:32]


def doc_group(doctype: str, name: str) -> str:
    """``doc_<doctype>_<name>``, hashed for the same reason as :func:`user_group`.

    Document names contain spaces and slashes routinely (``CRM Lead``, ``CRM-LEAD-2024-
    00001``), and the doctype half always contains a space.
    """
    digest = hashlib.sha256(f"{doctype}\x00{name}".encode("utf-8")).hexdigest()[:32]
    return "doc_" + digest


def get_channel_layer():
    """The configured layer, or ``None`` when realtime is off or Channels is absent.

    Importing ``channels`` at module scope would make this module — which phase 5 code
    imports unconditionally — fail to import in a deployment that has removed the
    package. Hence the local import.

    ``ENABLE_REALTIME`` is checked *here* rather than only in ``config/asgi.py``. Dropping
    the WebSocket route makes the layer unreachable by clients, but every publisher would
    still open a Redis connection and time out on it — turning "realtime is off" into "every
    comment write pauses". One gate, at the point where the transport is actually reached.
    """
    from django.conf import settings

    if not getattr(settings, "ENABLE_REALTIME", True):
        return None
    try:
        from channels.layers import get_channel_layer as _get
    except ImportError:  # pragma: no cover - channels is in requirements.txt
        return None
    try:
        return _get()
    except Exception:  # pragma: no cover - malformed CHANNEL_LAYERS
        logger.warning("realtime: channel layer misconfigured", exc_info=True)
        return None


def publish(event: str, message=None, user: str | None = None) -> bool:
    """Publish ``event``, to ``user`` if given, otherwise broadcast.

    The parameter order is ``frappe.publish_realtime(event, message, user=...)``'s, and
    that is the whole reason it is not ``(event, user, message)``. Several publish sites
    still to be ported pass the payload positionally — ``crm/api/whatsapp.py:50``,
    ``crm/integrations/exotel/handler.py:41`` — and under the other order
    ``publish("exotel_call", payload)`` would quietly route the payload into ``user``,
    hash it into a group name nobody is in, and return True.

    Returns True when the event was handed to the channel layer — **not** that a client
    received it. Nobody may depend on either fact for correctness.

    Safe to call from a Celery worker, a model signal, or a request: it uses the
    synchronous entry point, so it does not need an event loop of its own.
    """
    layer = get_channel_layer()
    if layer is None:
        logger.debug("realtime: %s dropped, no channel layer", event)
        return False

    group = user_group(user) if user else BROADCAST_GROUP

    try:
        from asgiref.sync import async_to_sync

        async_to_sync(layer.group_send)(group, _frame(event, message))
    except Exception:
        # Redis down, event loop already running, layer misbehaving — all the same to a
        # caller who is only trying to make a list refresh a little sooner.
        logger.warning("realtime: %s could not be published", event, exc_info=True)
        return False
    return True


def _frame(event: str, message) -> dict:
    """The channel-layer message.

    ``message`` defaults to ``{}``, not ``None``, because that is what
    ``frappe.publish_realtime`` puts on the wire for an event with no body. It matters:
    the frontend's ``docinfo_update`` handler destructures its argument
    (``Activities.vue:590``), and destructuring ``null`` is a TypeError.
    """
    return {"type": MESSAGE_TYPE, "event": event, "message": {} if message is None else message}


async def _asend(group: str, event: str, message) -> bool:
    layer = get_channel_layer()
    if layer is None:
        return False
    try:
        await layer.group_send(group, _frame(event, message))
    except Exception:
        logger.warning("realtime: %s could not be published", event, exc_info=True)
        return False
    return True


async def apublish(event: str, message=None, user: str | None = None) -> bool:
    """:func:`publish` from inside a coroutine.

    ``async_to_sync`` raises if it is called from a thread that already has a running
    event loop, so a consumer — or an async test — needs this door instead.
    """
    return await _asend(user_group(user) if user else BROADCAST_GROUP, event, message)


async def apublish_to_doc(doctype: str, name: str, event: str, message=None) -> bool:
    """:func:`publish_to_doc` from inside a coroutine."""
    return await _asend(doc_group(doctype, name), event, message)


def publish_to_doc(doctype: str, name: str, event: str, message=None) -> bool:
    """Publish to everyone watching one document.

    Upstream's ``frappe.publish_realtime(..., doctype=..., docname=...)`` — the shape
    ``docinfo_update`` uses.

    **Not** the shape ``whatsapp_message`` uses: ``crm/api/whatsapp.py:49-56`` broadcasts
    it with ``{reference_doctype, reference_name}`` in the body and no room at all, and
    ``Activities.vue:572-578`` filters client-side on those two fields. Phase 7 should
    call :func:`publish` for it, not this.
    """
    layer = get_channel_layer()
    if layer is None:
        return False
    try:
        from asgiref.sync import async_to_sync

        async_to_sync(layer.group_send)(doc_group(doctype, name), _frame(event, message))
    except Exception:
        logger.warning("realtime: %s could not be published", event, exc_info=True)
        return False
    return True
