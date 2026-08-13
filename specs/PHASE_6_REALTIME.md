# Phase 6 — Realtime (Django Channels)

> **PROVISIONAL** — the phase-0 agent must revise and flip to Authoritative.

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
(`PORT_PLAN.md` §3). Document it in the same place.

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
  to lean on. **Reject unauthenticated connects**; do not fall back to anonymous
- **Publish helper**: one function mirroring `frappe.publish_realtime(event, user=...)`
  so Celery tasks and model signals call the same thing
- **Permission on subscribe**: a client may only join a doc group for a document it can
  read. Run the phase-2 `has_permission` check on subscribe, not just on the initial
  fetch — otherwise realtime becomes a permission bypass

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
