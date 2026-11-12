# NOTIFICATIONS — in-app notifications and the realtime WebSocket

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

App `notifications`. The `PORT_MAP.md` rows under **NOTIFICATIONS**:

- **Doctype:** CRM Notification
- **Method paths (2):** `crm.api.notifications.get_notifications`, `mark_as_read`
- **Route:** `ws/realtime?token=<access token>`, which FOUNDATION wired to a placeholder
- **A publishing function** every other app calls to send a live event — the port of
  `frappe.publish_realtime`

It comes early — before SALES — because comments, assignments and WhatsApp messages all
create notifications, and those units need the model to exist.

## 2. Depends on

ACCOUNTS.

## 3. Read in `backend/` first

- `crm_app/models/metadata.py` (CRM Notification), `crm_app/permissions/notification.py`
- `crm_app/api/notifications.py`
- `crm_app/realtime.py`, `crm_app/consumers.py`, `config/routing.py`, `config/asgi.py`
- `specs/KNOWN_ISSUES.md` §1 (a flaky subscription test whose root cause is a
  production concern) and §5 (realtime verified across processes)
- `docs/PORT_PLAN.md` section 10 — why Channels and not polling
- Tests: `test_phase6_realtime.py`, and the notification tests in
  `test_assignment_notifications.py`

## 4. Must not be lost

- **A user may not create a notification for someone else.** CRM Notification's create
  rule refuses — the old generic create route was open until that check existed.
- **A user reads and marks only their own notifications.**
- **The socket closes with code 4001** on a missing or invalid token, and the route does
  not exist at all when `ENABLE_REALTIME=0`.
- **`doc_subscribe` is permission-checked** with the same rules as reading the document.
- **An event with no payload carries `{}`, never `null`.**
- **Publishing never fails the request that publishes**: Redis down, no channel layer
  — the event is dropped and logged, and the save still succeeds.
- **The event names on the wire are unchanged** (`API_CONTRACT.md` section 10).

## 5. Acceptance

- pytest, including a WebSocket test that authenticates, subscribes to a readable and an
  unreadable document, and receives an event — with the async test plugin actually
  running the coroutine.
- The notification blocks of `docs/http/08_activities_comments_notifications.http`; the
  whole file turns green with ACTIVITIES.
- Realtime checked across two processes, not only in-process.

## 6. Open questions

None yet.
