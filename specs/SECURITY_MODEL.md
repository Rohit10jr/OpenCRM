# Security model — upstream vs. this port

Upstream protects most doctypes with **DocType role permissions**: a table on the doctype
saying which role may create, read, write and delete, plus an optional `permlevel` for
per-field restriction. **This port does not model that layer at all.**

That single fact is the origin of nearly every security finding in phase 4. Upstream can
leave a doctype without a permission *hook* because the role table is still standing
behind it. Here, no hook means **no protection** — any authenticated caller gets full
CRUD through `/api/resource/` and through the `frappe.client.*` endpoints.

This file records, per doctype, what upstream does, what we do, and where we deliberately
differ. Read it before changing a permission rule, and add to it when you add one.

---

## The tools we have instead

Three field-level tools plus the row rule. They are not interchangeable and the difference
matters — picking the wrong one is how A2 nearly shipped a hole.

| Tool | Read | Write | Use when |
|---|---|---|---|
| `SENSITIVE_FIELDS` | **nobody** | nobody | Credentials. `User.groups`, `EmailAccount.password` |
| `READONLY_FIELDS` | everybody | **nobody** | Must be visible, must not be set by its subject. `User.enabled` |
| `RESTRICTED_FIELDS` | **managers** | (row rule) | Visible to admins, not to ordinary users. `EmailAccount.smtp_server` |
| `has_permission` | per row | per row | Who may touch the document at all |

`RESTRICTED_FIELDS` is applied **per request**, not baked into the serializer class —
those are built once per model and cached, so they cannot know who is asking.

### Where a field name is checked

Four entry points name a field, and **all four must agree**. Only `group_by` was guarded
before phase 4's review; the other three let a hidden value be recovered one question at
a time.

`fields=` · `filters=` · `or_filters=` · `order_by=` · `group_by=`

All now route through `field_security.is_hidden`. A sensitive field answers without
touching the database; only a *restricted* field needs the caller's roles.

---

## `Email Account`

The fullest example, and the one that turned up two defects worse than the one being
investigated.

### Who can do what

| | Upstream | This port **before** | This port **now** |
|---|---|---|---|
| Read | System Manager only¹ | Anyone | **Anyone** — diverge |
| Create | System Manager | Managers² | Managers |
| Write | System Manager | **Anyone** | **Managers** — fixed |
| Delete | System Manager | **Anyone** | **Managers** — fixed |
| Enforced by | DocType role table | *nothing* | `has_permission` row rule |
| Covers `frappe.client.set_value`? | yes | — | **yes** — shares `_get_checked` |

¹ `Inbox User` also holds read upstream, but **Frappe CRM never grants that role** — zero
references in the repo. In practice: System Manager only.
² System Manager or Sales Manager, per phase 3's decision D5.

### The password

| | Upstream | Before | Now |
|---|---|---|---|
| Storage | Encrypted, separate `__Auth` table | **Plaintext in the row** | Encrypted in the row |
| Column on the doc table | **none exists** | yes | yes (ciphertext) |
| In API output | absent | hidden | hidden |
| **Filterable** | **impossible — no column** | **yes → recovered** | rejected |
| Encryption key | site key | — | `FIELD_ENCRYPTION_KEY` |

**The structural lesson.** Upstream is not safe there because it checks something. It is
safe because *the value is not in the table*. Anything that merely filters **output** can
be probed through another door — which is exactly what happened:

```
stored:    'Sw0rdfish!'
recovered: 'sw0rdfish!'   ← ["password","like","<prefix>%"], one character per request
```

### Field visibility to a non-manager

| Field | Upstream | Now |
|---|---|---|
| `name`, `email_id`, `enable_outgoing` | not visible | **visible** — the Profile picker reads these |
| `smtp_server`, `email_server`, ports | not visible | restricted |
| `login_id`, `domain`, `api_key` | not visible | restricted |
| `signature`, `frappe_mail_site` | not visible | restricted |
| `password`, `api_secret` | not visible | never on the wire, encrypted |

---

## `User`

| | Upstream | Before | Now |
|---|---|---|---|
| Read | System Manager³ | Anyone | **Anyone but the built-ins** — diverge |
| Write | System Manager | **Anyone → any row** | **Your own row only** |
| Create / delete | System Manager | Anyone | Managers |
| `groups`, `is_superuser`, `is_staff` | permlevel 1 | **writable → escalation** | off the wire entirely |
| `enabled`, `user_type` | permlevel 1 | writable | readable, not writable |
| Built-ins hidden | yes (`user.py:1173`) | no | **yes** — ported verbatim |

³ `Desk User` holds `select` — the permission to appear in a link dropdown, not to read.

**Why reads stay open.** A first version narrowed reads to self, and **broke kanban**: a
board grouped by a Link-to-User builds one column per user, and upstream builds that list
with `frappe.get_all` (`crm_view_settings.py:187`), which **ignores permissions by
design**. The board collapsed to a single column. `crm.api.session.get_users` already
serves the same people to any caller, so nothing secret was being withheld.

The cost, stated plainly: this route also carries `mobile_no`, `phone`, `language`,
`time_zone` and `email_signature`, which `get_users` does not. Tightening it later means
auditing every path that enumerates users through the permission layer.

---

## Integration settings — `Twilio`, `Exotel`, `FCRM Settings`, `Global Settings`

| Doctype | Upstream read | Upstream write | Before | Now |
|---|---|---|---|---|
| `CRM Twilio Settings` | SysMgr + SalesMgr | SysMgr + SalesMgr | anyone | **managers** — match |
| `CRM Exotel Settings` | SysMgr + SalesMgr | SysMgr + SalesMgr | anyone | **managers** — match |
| `FCRM Settings` | **+ Sales User** | SysMgr + SalesMgr | anyone | **all read, managers write** — match |
| `CRM Global Settings` | all three roles | all three roles | anyone | unchanged — match (no secrets) |

### Where the credentials live

| Field | Upstream | Before | Now |
|---|---|---|---|
| `Twilio.api_secret`, `auth_token` | `Password` → `__Auth`, encrypted | hidden, **plaintext in row** | hidden, **encrypted** |
| `Exotel.api_token` | `Password` → `__Auth`, encrypted | hidden, **plaintext in row** | hidden, **encrypted** |
| `Twilio.api_key`, `twiml_sid` | `permlevel 1` | **exposed** | restricted |
| `Exotel.webhook_verify_token` | plain `Data` | **exposed** | restricted — **stricter** |
| **`FCRM.access_key`** | plain `Data`, **Sales User reads it** | **exposed** | restricted — **stricter**, bug #20 |

### Two decisions worth keeping straight

**Reads are closed here and open for `Email Account` — deliberately.** The Email Account
*list* feeds a user-facing feature ("which address do I send from?") on a Profile page
meant for everyone. Telephony is an **administration screen**; its whole purpose is
manager-only. Opening credentials so an admin screen renders for non-admins would be
backwards. Upstream's Telephony entry is missing the `isManager()` condition eleven of its
siblings carry (bug #19) — that is a UI defect, and we reproduce the behaviour rather than
weaken the permission to hide it.

**`FCRM Settings` is where A4's field work actually bites.** Everything else here is
manager-only anyway, so `RESTRICTED_FIELDS` on Twilio and Exotel is currently **inert** —
kept because it stops being inert the moment reads widen, which is exactly what happened
to `Email Account`. `FCRM Settings` cannot be closed (the timeline reads it on every
screen), so restricting `access_key` is the only thing standing between an FX credential
and every user.

---

## `ToDo`

| | Upstream | Before | Now |
|---|---|---|---|
| Doctype role | **`All`** — full CRUD | Anyone | route withheld |
| Row rule | own ToDos only (`todo.py:148`) | none | n/a |
| Reference document checked? | **never** | never | n/a |
| `/api/resource/ToDo` | exists | exists | **`routable=False`** |

The only case so far where **upstream has the same hole** — see `UPSTREAM_BUGS` #16. Full
write-up in `specs/UNROUTED_DOCTYPES.md`.

---

## Where we deliberately differ, and why

| # | Divergence | Direction | Reason |
|---|---|---|---|
| 1 | Non-managers may read `Email Account` | **looser** | Upstream shows them nothing, which leaves its own Profile "send from" picker empty (bug #17). We keep the screen working. |
| 2 | `Sales Manager` may write email accounts | **looser** | Matches D5. Otherwise a manager could create an account but not fix a typo in it. |
| 3 | Row rules instead of a role table | **different** | This port does not model DocType role permissions. |
| 4 | Filters rejected on hidden fields | **stricter** | Upstream needs no such check for `password` (no column) — and **fails to make it for `permlevel` fields**, bug #18. |
| 5 | Non-managers may read `User` | **looser** | Kanban builds a column per user; `get_users` serves the same data anyway. |
| 6 | `/api/resource/ToDo` withheld | **stricter** | Upstream ships the escalation. Bug #16. |
| 7 | 10-second mail timeout | **stricter** | Bug #15 — upstream hangs the save. |
| 8 | `FCRM.access_key` restricted to managers | **stricter** | Upstream leaves an FX credential on a record every user reads. Bug #20. |
| 9 | `Exotel.webhook_verify_token` restricted | **stricter** | Plain `Data` upstream; it authenticates inbound webhooks, so holding it means forging call events. |
| 10 | Telephony reads stay manager-only | **match** | Upstream's screen errors for non-managers (bug #19). Reproduced — the defect is a missing UI condition, not the permission. |
| 11 | Telephony credentials encrypted at rest | **match the property** | Upstream keeps `Password` fields in `__Auth`; we keep the column and encrypt it. |

---

## The recurring pattern

Five findings across four phases, all the same shape:

> **A doctype's endpoints are not its attack surface — the generic route is.**

Each phase gated the endpoints it wrote; each time the generated route stood open beside
them, doing the same job unguarded. Every agent's tests passed, because they tested the
endpoint just written.

Two questions settle each case, and they are cheaper than designing a rule:

1. **Does anything actually call this route?** If no → withhold it (`routable=False`).
   Smaller surface than any rule, and nothing to maintain.
2. **Do the method endpoints share the check?** `frappe.client.set_value`, `delete` and
   `rename_doc` resolve through `_get_checked`. If they do, a row rule covers every door
   at once — and withholding the route would fix **nothing**.

`ToDo` answered no to (1) → withheld. `Email Account` answered yes to (2) → rule.
**Deciding by pattern rather than by evidence would have got both wrong.**

**Still unwritten:** the standing test that enumerates every routable doctype and asserts
each is either ruled or *deliberately* world-readable. It is what stops the next one.
