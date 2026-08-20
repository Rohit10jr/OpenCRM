# The frappe-ui patches — JWT (phase 0) and realtime (phase 6)

**Read this before upgrading `frappe-ui`.** An upgrade that resets `main.js` will
silently revert the patch and every request will go out unauthenticated.

There are exactly **two** sanctioned frontend deviations from upstream. The JWT
interceptor is the first and is documented immediately below; the WebSocket client is the
second and has its own section at the end. Nothing else in `frontend/` differs.

## Why

`PORT_PLAN.md` section 10 and `specs/PHASE_0_FOUNDATION.md` section 7: the Django port
authenticates with JWT bearer tokens, not Frappe's `sid` session cookie. This is the
**only** sanctioned deviation from the Frappe wire protocol - the 225 `createResource` /
`createListResource` / `createDocumentResource` call sites are untouched, and every URL,
parameter name and response envelope is unchanged.

## What changed - four files, ~20 lines

| File | Change |
|---|---|
| `src/auth/tokens.js` | **New.** Token storage + `user_id` claim decode |
| `src/auth/jwtRequest.js` | **New.** Wraps `frappeRequest`: attaches the header, refreshes once on 401 |
| `src/main.js` | `setConfig('resourceFetcher', frappeRequest)` -> `jwtRequest`; same for the dev boot call |
| `src/stores/session.js` | `sessionUser()` reads the token instead of the `user_id` cookie; `login` stores the pair; `logout` clears it |

The integration point is one line, because frappe-ui centralises HTTP:

```js
setConfig('resourceFetcher', jwtRequest)   // was: frappeRequest
```

## Backend contract

| Endpoint | Returns |
|---|---|
| `POST /api/method/login` (`usr`, `pwd`) | `{"message": {"access", "refresh", "user", "full_name", ...}}` |
| `POST /api/method/token/refresh` (`refresh`) | `{"message": {"access", "refresh"}}` |
| `POST /api/method/logout` | `{"message": {"message": "Logged Out"}}` |
| `GET /api/method/frappe.auth.get_logged_user` | `{"message": "user@example.com"}` |

Implemented in `backend/frappe_core/api/auth.py`; covered by `backend/tests/test_auth.py`.

## Deliberate omissions

- **No CSRF token handling.** It protected cookie auth; there are no cookies now.
- **`logout` does not revoke the access token.** With stateless JWTs it stays valid
  until it expires (60 min by default, `JWT_ACCESS_TOKEN_LIFETIME_MINUTES`). Add
  `rest_framework_simplejwt.token_blacklist` if that window is unacceptable - the
  backend already calls `.blacklist()` when the app is installed.

## Not done in phase 0

This SPA has **no login page** - upstream redirects to the Frappe desk's
(`session.js:35`, `window.location.href = '/login?redirect-to=/crm'`). Something has to
serve that page and call `login`, and it is not in any phase 0-4 spec. Flagged in
`PROGRESS.md`.

Concurrent 401s collapse into a single refresh (`refreshInFlight`), because a list
screen can fire a dozen requests at once and each must not spend a refresh token.

---

# The realtime patch (phase 6)

`PHASE_6_REALTIME.md` section 1: Frappe pushes over **socket.io**, Django Channels speaks
**raw WebSocket**, and no configuration makes one talk to the other. This is the second
and last sanctioned frontend deviation.

## What changed - two files

| File | Change |
|---|---|
| `src/socket.js` | **Rewritten.** A raw `WebSocket` client with socket.io's `on` / `off` / `emit` surface |
| `src/auth/tokens.js` | `refreshAccessToken` moved here from `jwtRequest.js` - the socket needs it too, and the single-flight guard is only a guarantee if there is one of it |

**No component changed.** All seven `$socket` call sites - `Notifications.vue`,
`MobileNotification.vue`, `Activities.vue`, `ERPNextSettings.vue`, `ExotelCallUI.vue`,
`Deal.vue` - use `on` / `off` / `emit` and are untouched, because the replacement
reproduces that surface exactly:

```js
$socket.on('crm_notification', handler)
$socket.off('crm_notification')             // every handler for the event
$socket.off('docinfo_update', handler)      // just that one
$socket.emit('doc_subscribe', doctype, docname)
```

Event names and payloads are the backend's, which are upstream's - see
`backend/crm_app/realtime.py`.

## Wire protocol

Endpoint `GET /ws/realtime?token=<access token>`, one connection per tab.

| Direction | Frame |
|---|---|
| client -> server | `{"event": "doc_subscribe", "args": ["CRM Lead", "CRM-LEAD-2024-00001"]}` |
| client -> server | `{"event": "doc_unsubscribe", "args": [...]}`, `{"event": "ping"}` |
| server -> client | `{"event": "crm_notification", "message": {}}` |
| server -> client | `{"event": "docinfo_update", "message": {"doc": {...}, "key": "comments", "action": "add"}}` |
| server -> client | `{"event": "error", "message": "..."}`, `{"event": "pong"}` |

A missing message body is `{}`, never `null` - `frappe.publish_realtime` normalises it,
and `Activities.vue:590` destructures its argument.

## Authentication

The token rides in the **query string**, because a browser cannot set headers on a
WebSocket handshake. It therefore appears in server access logs; access tokens are
five-minute (`SIMPLE_JWT.ACCESS_TOKEN_LIFETIME`) and the client reconnects with a fresh
one rather than holding a long-lived credential in a URL.

An unauthenticated connect is **rejected**, not downgraded to anonymous. The server closes
with code **4001**; the client treats that as "the token is bad" rather than "the network
blinked", refreshes once, and gives up if the refresh fails - so a logged-out tab does not
spin.

## Two things socket.io did for free

- **Reconnect with backoff.** Exponential with full jitter, capped at 30 s. Without the
  jitter every tab in every browser reconnects on the same tick after a backend restart.
- **Re-subscribe on reconnect.** Server-side group membership dies with the connection, so
  `doc_subscribe` calls are remembered and replayed on open. Skip this and a reconnected
  client looks live and silently receives nothing.

Both are covered by `tests/unit/socket.test.js`.

## Deployment

The backend must be served by an **ASGI** server (`daphne`, in `requirements.txt`) - WSGI
cannot carry a WebSocket. `/ws/` has to be proxied to it alongside `/api/`; set
`VITE_WS_ORIGIN` only if the dev server is not proxying `ws`.

`ENABLE_REALTIME=0` on the backend removes the route entirely. Nothing breaks: the client
fails to connect, retries with backoff, and the app is exactly as functional as it was
before phase 6.
