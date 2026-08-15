# Phase 6 — Realtime (Django Channels)

> **PROVISIONAL** — flip this header to Authoritative when your gate passes.
>
> **Read `specs/AS_BUILT.md` first.** It lists what phases 0-2 actually built; where it
> and this spec disagree, it wins.

**Fan out.** Needs phase 5. Not blocking — the app is usable without it.

Settled decision (`PORT_PLAN.md` §10): Django Channels, not polling. Redis is already
required by Celery, so no new infrastructure.

---

## 1. Protocol change — this one is unavoidable

Frappe pushes over **socket.io**; Channels speaks **raw WebSocket**. There is no way to
keep the frontend socket client unchanged. Replace `frappe-ui`'s socket layer with a
plain WebSocket client and keep the **event names and payload shapes identical**, so
only the transport changes and no component code moves.

This is the second sanctioned frontend change, after the JWT interceptor
(`PORT_PLAN.md` §3). Document it in the same place — phase 0 created that place:
**`frontend/JWT_PATCH.md`**, which lists every touched file and why. Add a matching
section there rather than starting a new document, and update
`frontend/src/socket.js` (currently the socket.io client, reading
`window.socketio_port`).

---

## 2. Events — verified publish sites

| Event | Target | Source |
|---|---|---|
| `crm_notification` | single user (`to_user`) | `crm_notification.py:32` |
| `crm_product_sync_complete` | single user (session user) | `reconcile_job.py:35` |
| `crm_customer_created` | broadcast | `erpnext_crm_settings.py:632` — phase 7 |
| `exotel_call` | call payload | `integrations/exotel/handler.py:41` — phase 7 |
| WhatsApp message | reference doc subscribers | `api/whatsapp.py:50` — phase 7 |

Only the **first two are in scope** for phase 6. The rest arrive with phase 7 — build
the publish helper so they need no new plumbing.

---

## 3. Design

- **Groups**: one per user (`user_<email_hash>`), plus one per open document
  (`doc_<doctype>_<name>`) for live document refresh
- **Auth**: JWT in the connect query string or first message — Channels has no cookie
  to lean on. **Reject unauthenticated connects**; do not fall back to anonymous.
  The token is the same one `frontend/src/auth/tokens.js` stores; validate it with
  SimpleJWT and resolve the `user_id` claim (the email PK) exactly as
  `frappe_core/views.py:FrappeAPIView.initial` does for HTTP
- **Bind the session user.** Consumers run outside the request cycle, so
  `frappe_core.session.get_current_user()` is `"Guest"` unless you set it. Wrap handler
  bodies in `with session_user(user):` — `@me` resolution, `owner` stamping and the
  phase-2 hooks all read that contextvar. It is a `ContextVar`, so it is async-safe
- **Publish helper**: one function mirroring `frappe.publish_realtime(event, user=...)`
  so Celery tasks and model signals call the same thing
- **Permission on subscribe**: a client may only join a doc group for a document it can
  read. Call `frappe_core.permissions.check_object_permission(doc, "read", user)` on
  subscribe, not just on the initial fetch — otherwise realtime becomes a permission
  bypass. Do not re-implement the rule; that function is the one the HTTP detail route
  uses, so the two cannot drift

---

## 4. Acceptance criteria

- [ ] A notification created for user A reaches only user A
- [ ] Unauthenticated WebSocket connects are rejected
- [ ] Joining a doc group runs the phase-2 permission check
- [ ] Event names and payloads match upstream exactly
- [ ] Celery tasks can publish (channel layer reachable from workers)
- [ ] Client reconnects with backoff and re-subscribes on reconnect
- [ ] Nothing in the app breaks when Channels is switched off — realtime is an
      enhancement, never a correctness dependency
