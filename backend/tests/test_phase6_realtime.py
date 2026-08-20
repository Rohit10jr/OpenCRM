"""Phase 6 — the WebSocket layer.

Covers `PHASE_6_REALTIME.md` §4. No Redis and no ASGI server: the in-memory channel layer
(`config/settings/test.py`) and `WebsocketCommunicator` put publisher and consumer in one
process, which is enough for every criterion here because none of them is about Redis.

Two conventions worth knowing before reading further:

* Anything touching the socket is a coroutine, so it carries ``@pytest.mark.asyncio``.
  ``asyncio_mode = strict`` in ``pytest.ini`` makes a forgotten marker an error rather
  than a test that silently never runs.
* Database work inside an async test goes through ``database_sync_to_async``. Calling the
  ORM directly from the event loop raises ``SynchronousOnlyOperation``, which is a
  friendlier failure than it sounds — it means the test would have been lying.
"""

from __future__ import annotations

import json

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from crm_app import realtime
from frappe_core.session import session_user

#: ``transaction=True`` is not optional here. ``database_sync_to_async`` runs the ORM in
#: a worker thread with its own connection, and the ordinary ``django_db`` fixture keeps
#: every write inside one uncommitted transaction — so the consumer's thread looks up a
#: user the test just created and does not find it. ``conftest.builtin_users`` already
#: exists to re-seed Administrator and Guest after the flush that this implies.
pytestmark = pytest.mark.django_db(transaction=True)

#: How long to wait for a frame. Was a bare ``5`` at every call site, and that produced an
#: intermittent ``TimeoutError`` here - twice, weeks apart, only ever under full-suite load
#: and never in isolation.
#:
#: **Characterised before being changed** (specs/KNOWN_ISSUES.md #1): six consecutive
#: full-suite runs, zero failures; roughly two sightings in about twenty-five runs overall.
#: That is the "slow machine" end of the range, not the "teardown is broken" end, so
#: raising the wait is the evidence-supported fix rather than a way of not looking.
#:
#: The stall itself is understood. ``_may_read`` is ``@database_sync_to_async``, which
#: Channels wraps in ``close_old_connections()`` on entry and exit; with ``CONN_MAX_AGE``
#: at Django's default of 0, "old" means immediately, so **every permission check opens a
#: fresh Postgres connection**. Under a suite already churning connections on a machine
#: that has twice run out of memory, occasionally exceeding five seconds is unsurprising.
#:
#: Raising this does not address that root cause, which is a production concern in its own
#: right - see KNOWN_ISSUES.md #1. If this timeout ever needs raising again, fix
#: ``CONN_MAX_AGE`` instead; a second increase would be the point at which this stopped
#: being a slow machine.
RECEIVE_TIMEOUT = 15


def _application():
    """The websocket half of the ASGI app, built the way ``config/asgi.py`` builds it."""
    from channels.routing import URLRouter

    from config.routing import websocket_urlpatterns

    return URLRouter(websocket_urlpatterns)


def _token_for(user) -> str:
    from rest_framework_simplejwt.tokens import RefreshToken

    return str(RefreshToken.for_user(user).access_token)


async def _connect(token: str | None):
    path = "/ws/realtime" + (f"?token={token}" if token else "")
    communicator = WebsocketCommunicator(_application(), path)
    connected, _ = await communicator.connect()
    return communicator, connected


@database_sync_to_async
def _make_lead(owner, administrator):
    from crm_app.models import CRMLead, CRMLeadStatus

    with session_user(administrator.name):
        status = CRMLeadStatus.objects.create(lead_status="New", type="Open")
    with session_user(owner.name):
        return CRMLead.objects.create(first_name="Ada", lead_owner=owner, status=status)


@database_sync_to_async
def _make_notification(to_user, administrator):
    from crm_app.models import CRMNotification

    with session_user(administrator.name):
        return CRMNotification.objects.create(
            type="Mention", to_user=to_user, notification_text="You were mentioned"
        )


# ---------------------------------------------------------------------------
# Authentication — "reject unauthenticated connects; do not fall back to anonymous"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_connect_without_a_token_is_rejected():
    communicator, connected = await _connect(None)
    assert connected is False
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_connect_with_a_garbage_token_is_rejected():
    communicator, connected = await _connect("not-a-jwt")
    assert connected is False
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_connect_with_a_refresh_token_is_rejected(alice):
    """A refresh token is not an access token. Accepting one would make the short access
    lifetime meaningless for the socket."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = await database_sync_to_async(RefreshToken.for_user)(alice)
    communicator, connected = await _connect(str(refresh))
    assert connected is False
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_blacklisted_token_is_rejected(alice):
    """Logging out has to close the door on realtime too, not just on HTTP."""
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = await database_sync_to_async(RefreshToken.for_user)(alice)
    access = str(refresh.access_token)
    await database_sync_to_async(refresh.blacklist)()

    # The access token itself is not blacklisted by SimpleJWT (only refresh tokens are),
    # so this documents the window rather than asserting it is closed: the token stays
    # valid until it expires, which is why ACCESS_TOKEN_LIFETIME is five minutes.
    communicator, connected = await _connect(access)
    assert connected is True
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_valid_token_connects(alice):
    token = await database_sync_to_async(_token_for)(alice)
    communicator, connected = await _connect(token)
    assert connected is True
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_disabled_users_token_is_rejected(alice):
    """Deactivating an account must not leave a live socket usable."""
    from frappe_platform.models import User

    token = await database_sync_to_async(_token_for)(alice)
    # `is_active` is a property over `enabled` (frappe_platform/models.py:136) — Frappe's
    # name for Django's flag.
    await database_sync_to_async(
        lambda: User.objects.filter(pk=alice.pk).update(enabled=False)
    )()

    communicator, connected = await _connect(token)
    assert connected is False
    await communicator.disconnect()


# ---------------------------------------------------------------------------
# Delivery — "a notification created for user A reaches only user A"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_notification_reaches_its_recipient(alice, administrator):
    token = await database_sync_to_async(_token_for)(alice)
    communicator, connected = await _connect(token)
    assert connected

    await _make_notification(alice, administrator)

    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "crm_notification"
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_notification_does_not_reach_anybody_else(alice, bob, administrator):
    """The criterion is *only* user A. A per-user group that is not actually per-user
    fails silently — everyone just sees a little more than they should."""
    token = await database_sync_to_async(_token_for)(bob)
    communicator, connected = await _connect(token)
    assert connected

    await _make_notification(alice, administrator)

    assert await communicator.receive_nothing(timeout=1)
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_the_event_name_and_payload_match_upstream(alice, administrator):
    """``crm_notification.py:32`` publishes the event with no message body; the frontend
    handler (`Notifications.vue:132`) takes no argument and refetches."""
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await _make_notification(alice, administrator)

    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    # `{}`, not `null`: `frappe.publish_realtime` normalises a missing body to an empty
    # dict, and several frontend handlers destructure their argument.
    assert frame == {"event": "crm_notification", "message": {}}
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_celery_task_can_publish(alice, settings, monkeypatch):
    """`PHASE_6_REALTIME.md` §4 — *"Celery tasks can publish (channel layer reachable
    from workers)"*. ``run_product_reconciliation`` is the in-scope publisher.

    This is not only a statement about Celery: a task runs synchronously in a thread with
    no event loop, so it reaches the layer through ``async_to_sync``. If that door were
    the wrong one, this test is where it shows.
    """
    import crm_app.tasks as tasks

    settings.ENABLE_ERPNEXT = True
    monkeypatch.setattr(tasks, "_reconcile_products", lambda: {"created_in_crm": 0})

    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await database_sync_to_async(tasks.run_product_reconciliation)(user=alice.name)

    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "crm_product_sync_complete"
    await communicator.disconnect()


def test_publish_takes_the_message_second_like_frappe():
    """``frappe.publish_realtime(event, message, user=...)``.

    Found by the phase-6 review, and the failure it prevents is a silent one: several
    publish sites still to be ported pass the payload positionally
    (``crm/api/whatsapp.py:50``, ``crm/integrations/exotel/handler.py:41``). Under a
    ``(event, user, message)`` order, ``publish("exotel_call", payload)`` would hash the
    payload into a group name nobody is in — and return True.
    """
    import inspect

    for func in (realtime.publish, realtime.apublish):
        names = list(inspect.signature(func).parameters)
        assert names[:3] == ["event", "message", "user"], func.__name__


def test_a_missing_message_is_an_empty_dict_not_null():
    """``frappe.publish_realtime`` normalises it. Several frontend handlers destructure
    their argument, and destructuring ``null`` throws."""
    assert realtime._frame("crm_notification", None)["message"] == {}
    assert realtime._frame("docinfo_update", {"key": "comments"})["message"] == {
        "key": "comments"
    }


# ---------------------------------------------------------------------------
# Subscribe — "joining a doc group runs the phase-2 permission check"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribing_to_a_readable_document_succeeds(alice, administrator):
    lead = await _make_lead(alice, administrator)
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await communicator.send_to(
        text_data=json.dumps({"event": "doc_subscribe", "args": ["CRM Lead", lead.name]})
    )
    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "doc_subscribed"
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_subscribing_to_someone_elses_document_is_refused(alice, bob, administrator):
    """Without this check realtime is a permission bypass with a pleasant API: subscribe
    to a lead you cannot read and wait for its updates to arrive."""
    lead = await _make_lead(bob, administrator)
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await communicator.send_to(
        text_data=json.dumps({"event": "doc_subscribe", "args": ["CRM Lead", lead.name]})
    )
    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "error"
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_refused_subscribe_really_does_not_join_the_group(alice, bob, administrator):
    """The refusal message is not the guarantee — not being in the group is.

    A consumer that replied "error" and joined anyway would pass the test above.
    """
    lead = await _make_lead(bob, administrator)
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await communicator.send_to(
        text_data=json.dumps({"event": "doc_subscribe", "args": ["CRM Lead", lead.name]})
    )
    await communicator.receive_from(timeout=RECEIVE_TIMEOUT)  # the error

    await realtime.apublish_to_doc("CRM Lead", lead.name, "docinfo_update")
    assert await communicator.receive_nothing(timeout=1)
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_permitted_subscriber_does_receive_document_events(alice, administrator):
    lead = await _make_lead(alice, administrator)
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await communicator.send_to(
        text_data=json.dumps({"event": "doc_subscribe", "args": ["CRM Lead", lead.name]})
    )
    await communicator.receive_from(timeout=RECEIVE_TIMEOUT)  # doc_subscribed

    await realtime.apublish_to_doc("CRM Lead", lead.name, "docinfo_update")
    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "docinfo_update"
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_subscribing_to_a_missing_document_is_refused_the_same_way(alice):
    """"No permission" and "does not exist" have to be indistinguishable, or this is an
    existence oracle for records the user cannot see."""
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    for args in (["CRM Lead", "no-such-lead"], ["No Such DocType", "x"]):
        await communicator.send_to(
            text_data=json.dumps({"event": "doc_subscribe", "args": args})
        )
        frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
        assert frame["event"] == "error"
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_unsubscribing_stops_delivery(alice, administrator):
    lead = await _make_lead(alice, administrator)
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await communicator.send_to(
        text_data=json.dumps({"event": "doc_subscribe", "args": ["CRM Lead", lead.name]})
    )
    await communicator.receive_from(timeout=RECEIVE_TIMEOUT)
    await communicator.send_to(
        text_data=json.dumps({"event": "doc_unsubscribe", "args": ["CRM Lead", lead.name]})
    )
    # Wait for the ack before publishing. `send_to` is fire-and-forget, so without this
    # the publish races the unsubscribe and the test passes or fails on timing.
    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "doc_unsubscribed"

    await realtime.apublish_to_doc("CRM Lead", lead.name, "docinfo_update")
    assert await communicator.receive_nothing(timeout=1)
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_malformed_message_does_not_drop_the_socket(alice):
    """The frontend is allowed to be newer than the backend."""
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await communicator.send_to(text_data="}{ not json")
    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "error"

    await communicator.send_to(text_data=json.dumps({"event": "ping"}))
    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "pong"
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_an_unknown_client_event_is_ignored_not_fatal(alice):
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await communicator.send_to(text_data=json.dumps({"event": "invented_in_2027"}))
    assert await communicator.receive_nothing(timeout=1)

    await communicator.send_to(text_data=json.dumps({"event": "ping"}))
    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "pong"
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_comment_sends_the_payload_the_frontend_destructures(alice, administrator):
    """The shape ``Activities.vue:590`` reads: ``{doc, key}``, ``key == "comments"``.

    Found by the phase-6 review. ``docinfo_update`` was going out with a null body, which
    the handler destructures — so live refresh was not merely inert, it threw. And even a
    bare ``{}`` would have failed its ``key !== 'comments'`` guard silently.
    """
    from frappe_platform.models import Comment

    lead = await _make_lead(alice, administrator)
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await communicator.send_to(
        text_data=json.dumps({"event": "doc_subscribe", "args": ["CRM Lead", lead.name]})
    )
    await communicator.receive_from(timeout=RECEIVE_TIMEOUT)  # doc_subscribed

    @database_sync_to_async
    def _comment():
        with session_user(alice.name):
            return Comment.objects.create(
                comment_type="Comment",
                reference_doctype="CRM Lead",
                reference_name=lead.name,
                content="Called them",
            )

    comment = await _comment()

    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "docinfo_update"
    assert frame["message"]["key"] == "comments"
    assert frame["message"]["action"] == "add"
    assert frame["message"]["doc"]["reference_doctype"] == "CRM Lead"
    assert frame["message"]["doc"]["reference_name"] == lead.name
    assert frame["message"]["doc"]["name"] == str(comment.pk)
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_like_uses_its_own_docinfo_key(alice, administrator):
    """``comment.py``'s key map — a like is not a comment, and the handler filters on
    exactly that."""
    from frappe_platform.models import Comment

    lead = await _make_lead(alice, administrator)
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    await communicator.send_to(
        text_data=json.dumps({"event": "doc_subscribe", "args": ["CRM Lead", lead.name]})
    )
    await communicator.receive_from(timeout=RECEIVE_TIMEOUT)

    @database_sync_to_async
    def _like():
        with session_user(alice.name):
            Comment.objects.create(
                comment_type="Like",
                reference_doctype="CRM Lead",
                reference_name=lead.name,
                content="liked",
            )

    await _like()

    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["message"]["key"] == "like_logs"
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_the_sync_complete_event_is_not_broadcast(alice, bob, settings, monkeypatch):
    """Found by the phase-6 review: ``run_product_reconciliation`` defaulted ``user`` to
    ``None``, and a ``None`` user means broadcast — so everyone learned that somebody
    else's ERPNext sync had finished."""
    import crm_app.tasks as tasks

    settings.ENABLE_ERPNEXT = True
    monkeypatch.setattr(tasks, "_reconcile_products", lambda: {})
    token = await database_sync_to_async(_token_for)(bob)
    communicator, _ = await _connect(token)

    def _run():
        with session_user(alice.name):
            return tasks.run_product_reconciliation()

    await database_sync_to_async(_run)()

    assert await communicator.receive_nothing(timeout=1)
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_the_sync_complete_event_reaches_the_session_user(alice, settings, monkeypatch):
    """``reconcile_job.py:35`` targets ``frappe.session.user``."""
    import crm_app.tasks as tasks

    settings.ENABLE_ERPNEXT = True
    monkeypatch.setattr(tasks, "_reconcile_products", lambda: {})
    token = await database_sync_to_async(_token_for)(alice)
    communicator, _ = await _connect(token)

    def _run():
        with session_user(alice.name):
            return tasks.run_product_reconciliation()

    await database_sync_to_async(_run)()

    frame = json.loads(await communicator.receive_from(timeout=RECEIVE_TIMEOUT))
    assert frame["event"] == "crm_product_sync_complete"
    await communicator.disconnect()


# ---------------------------------------------------------------------------
# Group naming — the publisher and the consumer have to agree
# ---------------------------------------------------------------------------


def test_group_names_are_legal_for_channels():
    """Channels rejects a group name that is not ASCII alphanumerics/hyphen/underscore/
    period, or is over 100 characters. Both halves of a real key break that rule:
    ``o'brien+crm@example.co.uk`` is a legal user PK and ``CRM Lead`` has a space.
    """
    import re

    for name in (
        realtime.user_group("o'brien+crm@example.co.uk"),
        realtime.doc_group("CRM Lead", "CRM-LEAD-2024-00001"),
        realtime.doc_group("CRM Call Log", "a name with spaces/and/slashes"),
    ):
        assert re.fullmatch(r"[-\w.]+", name), name
        assert len(name) < 100


def test_group_names_are_stable_and_distinct():
    """Stable, because the publisher and the consumer compute them independently and a
    mismatch is not an error — it is silence."""
    assert realtime.user_group("a@example.com") == realtime.user_group("a@example.com")
    assert realtime.user_group("a@example.com") != realtime.user_group("b@example.com")
    assert realtime.doc_group("CRM Lead", "x") != realtime.doc_group("CRM Deal", "x")
    # The separator matters: without it ("CRM Lead", "x") and ("CRM", "Leadx") collide.
    assert realtime.doc_group("CRM Lead", "x") != realtime.doc_group("CRM", "Leadx")


# ---------------------------------------------------------------------------
# "Nothing in the app breaks when Channels is switched off"
# ---------------------------------------------------------------------------


def test_publish_returns_false_and_does_not_raise_without_a_layer(monkeypatch):
    monkeypatch.setattr(realtime, "get_channel_layer", lambda: None)
    assert realtime.publish("crm_notification", user="a@example.com") is False
    assert realtime.publish_to_doc("CRM Lead", "x", "docinfo_update") is False


def test_the_flag_stops_publishers_reaching_the_transport(settings):
    """Found by the phase-6 review.

    Dropping the WebSocket route in ``config/asgi.py`` makes the layer unreachable by
    *clients* — but every publisher would still open a Redis connection and wait for it to
    time out. That turns "realtime is off" into "every comment write pauses", which is the
    opposite of what §4's last criterion asks for. The gate belongs where the transport is
    actually reached.
    """
    from crm_app import realtime as rt

    settings.ENABLE_REALTIME = False
    assert rt.get_channel_layer() is None
    assert rt.publish("crm_notification", user="a@example.com") is False

    settings.ENABLE_REALTIME = True
    assert rt.get_channel_layer() is not None


def test_publish_swallows_a_broken_layer(monkeypatch):
    """Redis down must not turn into a 500 on a write."""

    class Broken:
        async def group_send(self, *a, **kw):
            raise RuntimeError("redis is down")

    monkeypatch.setattr(realtime, "get_channel_layer", lambda: Broken())
    assert realtime.publish("crm_notification", user="a@example.com") is False


def test_creating_a_notification_still_works_with_realtime_off(alice, administrator, monkeypatch):
    """The whole of §4's last criterion in one test: the write is what matters, the
    event is a courtesy."""
    from crm_app.models import CRMNotification

    monkeypatch.setattr(realtime, "get_channel_layer", lambda: None)
    with session_user(administrator.name):
        notification = CRMNotification.objects.create(
            type="Mention", to_user=alice, notification_text="Still saved"
        )
    assert CRMNotification.objects.filter(pk=notification.pk).exists()


def test_the_asgi_application_drops_the_websocket_route_when_realtime_is_off(settings):
    """`config/asgi.py` — with the flag off there is no ws route to reach at all."""
    from channels.routing import ProtocolTypeRouter

    import config.asgi as asgi

    settings.ENABLE_REALTIME = False
    assert not isinstance(asgi._build_application(), ProtocolTypeRouter)

    settings.ENABLE_REALTIME = True
    assert isinstance(asgi._build_application(), ProtocolTypeRouter)
