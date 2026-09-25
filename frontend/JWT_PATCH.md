# The frappe-ui patches — JWT (phase 0), realtime (phase 6) and boot (follow-up)

**Read this before upgrading `frappe-ui`.** An upgrade that resets `main.js` will
silently revert two of the patches: every request will go out unauthenticated, and the
boot values will be fetched only under `yarn dev`, leaving production without them.

There are exactly **three** sanctioned frontend deviations from upstream. The JWT
interceptor is the first and is documented immediately below; the WebSocket client is the
second and the boot-values call the third, each with its own section at the end. Nothing
else in `frontend/` differs.

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
| `src/auth/interceptor.js` | **New (23 Sep 2026).** Attaches the header at `fetch` / `XMLHttpRequest` for same-origin `/api/` URLs, for everything that does not go through `resourceFetcher` (see below) |
| `src/main.js` | `setConfig('resourceFetcher', frappeRequest)` -> `jwtRequest`; `installAuthInterceptor()`; same for the dev boot call |
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

## The second half: requests that never consult `resourceFetcher`

`docs/FINDINGS.md` 30, found the first time the frontend ran in a browser. frappe-ui's
`call()` (`utils/call.ts`) builds its own `fetch` and reads no config; its two upload
helpers (`useFileUpload.ts`, `fileUploadHandler.ts`) build their own `XMLHttpRequest`.
Thirty-two files under `src/` import `call` directly, the router guard among them, and
every attachment upload takes the XHR path. Upstream never notices, because the `sid`
cookie rides on every same-origin request whoever builds it; a bearer header does not.

`src/auth/interceptor.js` closes that at the two browser primitives instead of in 32
components: `window.fetch` and `XMLHttpRequest.prototype.open/send` add
`Authorization: Bearer` to same-origin `/api/` URLs when the caller has not set one.
`/api/method/login` and `/api/method/token/refresh` are excluded, because a stale access
token on the refresh call would be authenticated before the refresh ran. Refresh-on-401
stays in `jwtRequest`; a bare `call()` that meets an expired token fails, as it did
upstream with an expired session.

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
`docs/internal/PROGRESS.md`. Phase 8 added the page inside the SPA.

## What an in-app login changes (24-25 Sep 2026)

Upstream signs in and out through full page loads, so every Pinia store and resource
cache starts from nothing on each side of the boundary. With the login page inside the
SPA the app keeps running through both, and three things had to become explicit
(`docs/FINDINGS.md` 32-34): the login response is read from under `message`, because
frappe-ui returns the login body wrapped; the router guard decides "not logged in" before
it creates the users store, and re-fetches that store if an early fetch had failed; and
sign-out is a real page load to `/crm/login`, so the next user does not inherit the
previous one's stores.

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

**`app.use(FrappeUI, { socketio: false })`** (23 Sep 2026, `docs/FINDINGS.md` 31): the
plugin's default is `socketio: true`, which starts upstream's socket.io client against
port 9000 and retries forever. `$socket` is set once, in `main.js`'s `mount()`, to the
client below.

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

---

# The boot patch (phase 8 follow-up, 23 Sep 2026)

`docs/FINDINGS.md` 26. The page needs a few server-side facts before it can draw: the
date, time, number and currency formats (`window.sysdefaults`), the system and user
timezone, the translation tables, and three site flags. Upstream calls this set the
**boot** (`crm/www/crm.py:get_boot`) and delivers it two ways. In production the
Jinja-rendered `crm/www/crm.html` carries a `<script>` that writes every key onto
`window`, so the page arrives with them. Under `yarn dev` Vite serves the raw
`index.html`, no template runs, and `main.js` posts to `crm.www.crm.get_context_for_dev`
and copies the reply onto `window` before it mounts.

This port serves no HTML, so the endpoint is the only source, in every mode. This is the
third and last sanctioned deviation.

## What changed - one file

| File | Change |
|---|---|
| `src/main.js` | The fetch-then-mount step runs always, not only under `import.meta.env.DEV`; a failed call logs and mounts anyway |

The call, its URL and the keys it copies onto `window` are upstream's own; only the
condition around it went. Mounting on failure is deliberate: with the values missing the
list pages throw on their first date cell (`utils/index.js:82` reads
`window.sysdefaults.date_format` with no guard), but the login page renders and the
console names the cause, where the alternative was a blank page with no message at all.

## Backend contract

| Endpoint | Returns |
|---|---|
| `POST /api/method/crm.www.crm.get_context_for_dev` (guest-allowed) | `{"message": {"sysdefaults": {...seven format keys...}, "timezone": {"system", "user"}, "translated_messages": {}, "translated_doctypes": [], "state_options": {}, "is_demo_site": false, "demo_data_created": false, "is_fc_site": false}}` |

Implemented in `backend/crm_app/api/boot.py`; covered by `backend/tests/test_boot.py`.
The name is upstream's, "for_dev" included, so the guard test and the route inventory
match the string the frontend sends. Upstream's developer-mode gate is not reproduced,
because production is a caller here, and nothing in the answer is secret. The seven format
values come from `FRAPPE_SYSDEFAULTS` in `config/settings/base.py`, each overridable from
`.env`, since the port has no System Settings doctype; `currency` ships empty, as on a
fresh Frappe site, and the frontend shows USD until `FRAPPE_CURRENCY` is set.

## Deployment

The `yarn build` output is served as static files, with `index.html` returned for every
path under `/crm/`; the app then fetches the boot values itself. Nothing renders a
template. The `buildConfig.indexHtmlPath` in `vite.config.js` still points at upstream's
app folder and needs changing before the first production build - a deployment item
outside this patch.
