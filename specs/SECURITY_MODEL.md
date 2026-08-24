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

## `CRM Sales Hierarchy` — the worst of the phase-4 findings

**The org tree is an input to the permission engine, so writing it is writing your own
permissions.** `org_hierarchy` resolves "records owned by anyone in my subtree" against
this table on every Lead and Deal read.

| | Upstream | Before | Now |
|---|---|---|---|
| Read | all three roles | anyone | **anyone** — match |
| Create / write / delete | **System Manager only** | **anyone** | **System Manager only** — match |

Observed end to end as a plain Sales User:

```
GET  /api/resource/CRM Deal/<bob's deal>     → 403
POST /api/resource/CRM Sales Hierarchy       → 201   (alice adds herself)
PUT  .../CRM Sales Hierarchy/<bob's node>    → 200   (reports_to = alice)
GET  /api/resource/CRM Deal/<bob's deal>     → 200   deal_value: 777777
```

Worse than the `ToDo` escalation it resembles: that took one named record at a time, this
takes a **whole subtree in one call**, and the nested-set maintenance rebuilds `lft`/`rgt`
for the attacker on the way through. Nothing errors — it reads as an ordinary org-chart
edit.

**Only the feature flag kept it from being live.** `enable_sales_hierarchy` is off by
default and `org_hierarchy` skips the tree entirely when it is; any organisation using the
feature was exposed. A4 had already made that flag manager-writable, so it could not be
turned on by the caller.

**Note the tighter role set.** System Manager only — not the manager pair used elsewhere
in this port. A Sales Manager may not restructure the chart, because the chart is what
decides what a Sales Manager can see. Upstream agrees.

---

## `Version` — un-routed

| | Upstream | Before | Now |
|---|---|---|---|
| Read | System Manager only | **anyone** | route withheld |
| Create | `in_create: 1` — never via API | anyone | route withheld |
| Delete | Administrator | anyone | route withheld |

Rows carry the old and new values, so the audit trail leaked the money on records the
caller is refused. Introduced by A2 and closed by A5 — full write-up in
`specs/UNROUTED_DOCTYPES.md`.

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

## Phase 7 — the integration doctypes

Ten new routable doctypes, all ruled **manager-only, reads closed**, matching the telephony
settings above and for the same reason: they back administration screens.

| Doctype | Holds | Upstream | Us |
|---|---|---|---|
| `ERPNext CRM Settings` | API key + secret for the remote site | System Manager | managers — match |
| `Lead Sync Source` | Meta access token (`Password`) | role table | managers |
| `Facebook Page` | Meta **page** access token, plain `Data` upstream | role table | managers, and **encrypted** — bug #28 |
| `Facebook Lead Form` | form metadata, no secret | role table | managers — ruled anyway, see below |
| `Failed Lead Sync Log` | **the raw Graph payload** | role table | managers |
| `WhatsApp Message` | conversation content | `frappe_whatsapp`'s role table | **defers to its referenced document** |

**`Failed Lead Sync Log` is the one to notice.** Everything else in that group is
configuration; this holds `lead_data`, the raw Facebook payload for a lead that *failed* to
import — a real person's name, email and phone number, for a record that never became a CRM
document and therefore has no row rule of its own protecting it. It is personal data in a
table nobody would think to look at.

**`Facebook Lead Form` holds no secret and is ruled anyway.** Leaving one doctype of a
four-doctype feature open reads to the next person as intent rather than as an oversight.

**`WhatsApp Message` joins `Comment` / `Communication` / `File`** in
`crm_app/permissions/attachments.py` rather than getting a rule of its own — it is a row
*about* a lead or deal that carries which one, which is exactly that shape. The reason is
sharper than for the others: a deal row leaks a number, a WhatsApp thread leaks the
negotiation.

### The second door the phase-7 review found

`frappe.client.get_single_value` rejected `SENSITIVE_FIELDS` and checked **nothing else** —
no row rule, no `RESTRICTED_FIELDS`. So every manager-only singleton above answered to any
authenticated caller, including `CRM Exotel Settings.webhook_verify_token`, which is the
entire authentication on a public webhook.

The hole is phase 3's and there were no tests for that endpoint at all. Phase 7 is what made
it serious. It now applies the row rule and routes the field name through
`field_security.is_hidden`, like the four field-naming routes.

> **The pattern, one layer along.** It was not the generic `/api/resource/` route this time.
> It was a second, older *method* endpoint doing the same job unguarded — which is the same
> mistake wearing its sixth disguise. When a mechanism protects a doctype, ask what else can
> read that doctype.

### Known gap: `CRM Exotel Settings.webhook_verify_token` is plaintext at rest

`RESTRICTED_FIELDS` but **not** `ENCRYPTED_FIELDS`. It is not encrypted because
`ExotelSettings.vue:66` binds it with `v-model` — an editable input the administrator types
into and reads back — so encrypting it would show them ciphertext and saving would
re-encrypt that.

Closing it needs either a decrypt-on-read path for permitted users, which does not exist, or
a frontend change so the screen shows the callback URL instead of the token. Both are
mechanisms rather than fixes, so phase 7 recorded it instead of inventing one. The serious
half — that any authenticated user could read it — is closed above.

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

**The standing test now exists** — `tests/test_route_surface.py`. It does not decide
whether a doctype is safe; it makes the *absence of a decision* fail:

```
route surface: 36 routable | 12 ruled | 10 reviewed-open | 14 awaiting review (A7)
```

Registering a doctype breaks the build until somebody records which of three things it is:
ruled, reviewed-and-open with the reason, or not-yet-reviewed with the question. The third
list is allowed to be non-empty on purpose — a test demanding 24 rules on the day it was
written would have been suppressed by the next person in a hurry; one demanding a
*sentence* gets kept, and the sentences are what turn "audit the route surface" into a
finite list of named work.

It also asserts one invariant with no exceptions list: **a doctype declaring secrets must
have a rule.** That one would have caught A3 and A4 on the day they were written.

**`tests/test_credential_fields.py` closes the other half.** The route test forces a
decision about *who can reach* a doctype; nothing forced one about *what is inside it*. It
matches on field names — `*_token`, `*_secret`, `password`, `api_key`, `auth` — and fails
unless each is declared in `SENSITIVE_FIELDS`, `ENCRYPTED_FIELDS` or `RESTRICTED_FIELDS`,
or excused in writing.

A name is a heuristic, deliberately: it is what a reviewer scans for, and what the author
chose while thinking about the credential. Two exception lists carry the judgement —
`REVIEWED_NOT_CREDENTIALS` for fields that only look like one (`ascii_encode_password` is
a boolean flag), and `REVIEWED_RESTRICTED_ONLY` for real secrets deliberately left
manager-readable. They are kept separate on purpose: conflating them would let a genuine
secret hide behind "not a credential".

It found an undeclared field on its first run, and a gap in **itself** on its second: a
field that is encrypted but not sensitive is served over the API as ciphertext and stays
filterable. Better than plaintext, and not the same as protected. True secrets now need
both declarations.

---

## Phase 8 — the front door

Three `allow_guest` endpoints, which is rarer here than anywhere else in the port: they are
the only ones an unauthenticated stranger can reach *and* that write something.

| Endpoint | What stands in for a permission check |
|---|---|
| `reset_password` | Nothing to check — and it never reveals whether the address exists |
| `update_password` | The reset key, or the old password. Both are proofs |
| `accept_invitation` | The invitation key, which arrives **by email** |

None enumerates: each is a lookup by key or primary key, with no list read. That is why
`auth_pages.py` is on `test_no_endpoint_bypasses_the_permission_layer`'s allowlist — the
phase-2 hook answers "what may this user see", and the whole point of these three is that
the caller is not yet a user.

### The reset key

Hashed with SHA-256, never encrypted. Encryption is reversible, so an encrypted key is
still a working key to whoever holds the encryption key; a hash is not, and the server only
ever needs to *compare*. Both reset columns are `SENSITIVE_FIELDS` — the second one,
`last_reset_password_key_generated_on`, is not a credential but is hidden anyway, because
`User` reads are open to every authenticated caller (divergence #5) and a visible issue time
tells a colleague which accounts have a live link right now.

Single use is a **compare-and-swap**, not a read-then-clear. The phase-8 review found the
two-statement version: two requests arriving together could both resolve and both set a
password, the second winning silently — and whoever holds a forwarded copy of the link *is*
that second request.

### The lockout is not login's private business

`update_password`'s old-password path checks a password on an `allow_guest` endpoint. Until
the phase-8 review it did so without `check_login_allowed`, which made it an online password
oracle that sidestepped the tracker protecting `login` entirely.

> **The rule this generalises to:** anywhere a password is verified, the attempt tracker
> applies. A second door that checks credentials without it makes the first door's
> protection decorative — the same shape as `get_single_value` reading singleton fields
> without the row rule (phase 7), one layer along.

### And one that only the flow catches

The invitation email linked to `/api/method/crm.api.accept_invitation`. Upstream can link to
its endpoint because that one answers a GET with an HTTP redirect into the Desk; ours
answers with JSON, so an invitee clicking the link landed on a JSON blob. Every unit test
passed, because they tested the endpoint. Gate step 5 exists for this, and even walking the
flow missed it once — the walk followed the endpoint rather than the URL.

---

## ~~Known gap: `accept_invitation` is not implemented~~ — closed in phase 8

**Implemented** in `crm_app/api/auth_pages.py`, with the protections that were put in place
before it existed left exactly as they were: `CRM Invitation` is manager-only and its `key`
is `SENSITIVE_FIELDS`. Redemption reads the key from the email, never from the API.

The original write-up is kept below, because it is the record of a hole being disarmed
*before* the endpoint that could open it was built — which is the only reason building it
was a small change rather than a risky one.

### Original entry

`crm_app/tasks.py:214` emails an invitation link pointing at
`/api/method/crm.api.accept_invitation`. **Nothing implements that endpoint** — upstream
has it at `crm/api/__init__.py:83`. So invitations send a link that 404s, and the flow is
broken end to end.

It is also latent security. `CRM Invitation` holds `role` and `key` and is currently
world-writable (it is on the A7 list). Forging an invitation that grants System Manager is
possible today but cannot be redeemed, because there is nothing to redeem it with. **That
becomes critical the moment the endpoint is implemented** — so whoever builds it must give
`CRM Invitation` a rule in the same change.
