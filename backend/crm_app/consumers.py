"""The WebSocket endpoint — phase 6.

`PHASE_6_REALTIME.md` §1: Frappe pushes over **socket.io**, Channels speaks **raw
WebSocket**, and there is no way to keep the frontend's socket client unchanged. What
*is* kept is everything above the transport — the event names, the payload shapes, and
the ``on`` / ``off`` / ``emit`` surface the components already call. So this consumer
speaks a deliberately socket.io-shaped protocol:

    client -> {"event": "doc_subscribe",   "args": ["CRM Lead", "CRM-LEAD-2024-00001"]}
    client -> {"event": "doc_unsubscribe", "args": ["CRM Lead", "CRM-LEAD-2024-00001"]}
    server -> {"event": "crm_notification", "message": null}

Two rules here are security-relevant, and both are easy to get wrong in a way no test
notices unless you write the test for it:

**Unauthenticated connects are rejected.** Not downgraded to anonymous, not accepted and
filtered later — closed. An accepted anonymous socket is a socket that can ask to join
groups, and every guard after that point becomes the only thing standing between a
stranger and other people's leads.

**Joining a document group runs the phase-2 permission check.** ``doc_subscribe`` names a
document, and the client chooses that name. Without the check, realtime is a permission
bypass with a nice API: subscribe to a lead you cannot read and wait for its updates to
arrive. The check calls
:func:`frappe_core.permissions.check_object_permission`, the same function the HTTP detail
route uses, so the two cannot drift apart (`PHASE_6_REALTIME.md` §3).
"""

from __future__ import annotations

import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from crm_app import realtime

logger = logging.getLogger(__name__)

#: Close codes. 4001 is in the private range; the client uses it to tell "your token is
#: bad, stop retrying" apart from "the network blinked, back off and retry".
CLOSE_UNAUTHENTICATED = 4001


@database_sync_to_async
def _resolve_token(raw_token: str):
    """The JWT to a user PK, or ``None``.

    Deliberately the SimpleJWT path `frappe_core/views.py:FrappeAPIView.initial` ends up
    on, via the same ``USER_ID_CLAIM``/``USER_ID_FIELD`` settings, so a token that works
    for HTTP works here and one that has been revoked works for neither.
    """
    from django.conf import settings
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

    if not raw_token:
        return None
    try:
        validated = JWTAuthentication().get_validated_token(raw_token)
        user = JWTAuthentication().get_user(validated)
    except (InvalidToken, TokenError, KeyError):
        return None
    except Exception:
        # An unexpected failure here must still close the socket, never open it.
        logger.warning("realtime: token validation failed", exc_info=True)
        return None
    if user is None or not user.is_active:
        return None
    claim = settings.SIMPLE_JWT.get("USER_ID_FIELD", "name")
    return str(getattr(user, claim, user.pk))


@database_sync_to_async
def _may_read(doctype: str, name: str, user: str) -> bool:
    """``True`` if ``user`` may read that document *right now*.

    Both halves matter. ``base_queryset`` applies the row-level list filter and the
    object hook can be stricter still, exactly as on the HTTP detail route — a doctype
    with neither is readable, which is the framework's existing convention and not
    something to tighten here.
    """
    from frappe_core import permissions, registry
    from frappe_core.query import base_queryset
    from frappe_core.session import session_user

    if not registry.has_doctype(doctype):
        return False
    entry = registry.get_entry(doctype)
    if entry.is_child_table:
        # A child row has no standalone identity on the wire (frappe_core/views.py),
        # so it has none here either.
        return False

    with session_user(user):
        instance = base_queryset(doctype, user).filter(pk=name).first()
        if instance is None:
            return False
        return permissions.check_object_permission(instance, "read", user)


class RealtimeConsumer(AsyncWebsocketConsumer):
    """One connection per browser tab."""

    async def connect(self):
        self.user = await self._authenticate()
        if not self.user:
            # Reject before accepting. `close()` without `accept()` produces an HTTP 403
            # on the handshake, so an unauthenticated client never has a socket at all.
            await self.close(code=CLOSE_UNAUTHENTICATED)
            return

        #: Doc groups this connection has joined, so `disconnect` can leave them and a
        #: repeated `doc_subscribe` is idempotent.
        self.doc_groups: set[str] = set()

        await self.channel_layer.group_add(realtime.user_group(self.user), self.channel_name)
        await self.channel_layer.group_add(realtime.BROADCAST_GROUP, self.channel_name)
        await self.accept()

    async def _authenticate(self):
        """Token from the query string. `PHASE_6_REALTIME.md` §3.

        A browser cannot set headers on a WebSocket handshake, which is why the token
        rides in the query string rather than in ``Authorization``. That puts it in
        server access logs, so access tokens are short-lived (five minutes,
        ``SIMPLE_JWT.ACCESS_TOKEN_LIFETIME``) and the client reconnects with a fresh one.
        """
        from urllib.parse import parse_qs

        query = parse_qs(self.scope.get("query_string", b"").decode())
        token = (query.get("token") or [""])[0]
        return await _resolve_token(token)

    async def disconnect(self, code):
        user = getattr(self, "user", None)
        if not user:
            return
        await self.channel_layer.group_discard(realtime.user_group(user), self.channel_name)
        await self.channel_layer.group_discard(realtime.BROADCAST_GROUP, self.channel_name)
        for group in list(getattr(self, "doc_groups", ())):
            await self.channel_layer.group_discard(group, self.channel_name)

    # -- client -> server ---------------------------------------------------

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or "")
        except (TypeError, ValueError):
            return await self._error("Malformed message")
        if not isinstance(payload, dict):
            return await self._error("Malformed message")

        event = payload.get("event")
        args = payload.get("args") or []
        if not isinstance(args, list):
            return await self._error("Malformed message")

        if event == "doc_subscribe":
            return await self._doc_subscribe(args)
        if event == "doc_unsubscribe":
            return await self._doc_unsubscribe(args)
        if event == "ping":
            return await self.send(json.dumps({"event": "pong"}))
        # Unknown events are ignored rather than fatal: the frontend is allowed to be
        # newer than the backend, and a stray emit should not drop a working socket.
        logger.debug("realtime: ignoring client event %r", event)

    async def _doc_subscribe(self, args):
        if len(args) < 2:
            return await self._error("doc_subscribe needs a doctype and a name")
        doctype, name = str(args[0]), str(args[1])

        if not await _may_read(doctype, name, self.user):
            # Same wording either way: "no permission" and "does not exist" must not be
            # distinguishable, or this becomes an existence oracle for records the user
            # cannot see.
            return await self._error(f"No permission to subscribe to {doctype}")

        group = realtime.doc_group(doctype, name)
        if group not in self.doc_groups:
            await self.channel_layer.group_add(group, self.channel_name)
            self.doc_groups.add(group)
        await self.send(
            json.dumps({"event": "doc_subscribed", "message": {"doctype": doctype, "name": name}})
        )

    async def _doc_unsubscribe(self, args):
        if len(args) < 2:
            return await self._error("doc_unsubscribe needs a doctype and a name")
        doctype, name = str(args[0]), str(args[1])
        group = realtime.doc_group(doctype, name)
        if group in self.doc_groups:
            await self.channel_layer.group_discard(group, self.channel_name)
            self.doc_groups.discard(group)
        # Acked even when the client was not subscribed. No permission check: leaving a
        # group you are not in is a no-op, and refusing to acknowledge it would only tell
        # the caller something about a document it cannot read.
        await self.send(
            json.dumps(
                {"event": "doc_unsubscribed", "message": {"doctype": doctype, "name": name}}
            )
        )

    async def _error(self, text: str):
        await self.send(json.dumps({"event": "error", "message": text}))

    # -- server -> client ---------------------------------------------------

    async def realtime_event(self, message):
        """Fan-out handler. ``realtime.publish`` sends ``{"type": "realtime.event"}``
        and Channels routes it here."""
        await self.send(
            json.dumps({"event": message["event"], "message": message.get("message")})
        )
