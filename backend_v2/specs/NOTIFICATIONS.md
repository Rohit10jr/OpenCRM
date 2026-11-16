# NOTIFICATIONS — in-app notifications and the realtime WebSocket

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

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
- `PORT_PLAN.md` section 10 — why Channels and not polling
- Tests to read and write again: `test_phase6_realtime.py`, and the notification tests in
  `test_assignment_notifications.py`
- **Tests to port** (REBUILD_PLAN S14): `test_notification_scope.py`, and this unit's
  routes in `test_phase3_endpoints.py`. The spec check confirms the list.

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

- pytest: every test in the port list passing with its expected answers unchanged, and new
  tests for each item in section 4 no old test covers — including a WebSocket test that authenticates, subscribes to a readable and an
  unreadable document, and receives an event — with the async test plugin actually
  running the coroutine.
- The notification blocks of `docs/http/08_activities_comments_notifications.http`; the
  whole file turns green with ACTIVITIES.
- Realtime checked across two processes, not only in-process.

## 6. Open questions

None yet.

## 7. Carried from FOUNDATION

- Port the WebSocket stale-token case.
- Replace `AS_BUILT.md`'s "Background work and live events" stub with the working recipe
  when this unit supplies the consumer and publisher.

## 8. Carried from SHARED_ACTIONS

Opt the resources below in to the `core/mixins/` actions (AS_BUILT §2, "Opting a
resource in to a shared action"), write each generated route's row in `PORT_MAP.md`,
and port the real-doctype cases SHARED_ACTIONS left (its §3 table). Their generic
mechanism is tested on `tests_support`; the cases below prove it on real records.

- CRM Notification's linked-document title (`message`, `doc.py:467-468`) through
  `linked_document_title`, and its reference clearing (the notification-type pair
  cleared only when it matches the reference, `doc.py:530-534`) through
  `clear_linked_document_reference`.
- From `test_rename.py`: the Notification case. From `test_delete_link_check.py`: a
  hidden notification blocking a Deal (with SALES).
