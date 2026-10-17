# Upstream bugs — Frappe CRM / Frappe framework

Defects found in **upstream** while porting. Not our bugs. One sequence, **1 to 49**, in
the order they were found: 1–9 in phases 0–2, 10–35 in phases 3–8, 36–38 appended during
the phase-4 review, 39–49 in the browser testing of the follow-up. (Until 7 Oct 2026 this
was two files, `UPSTREAM_BUGS_PHASE_0-2.md` and `UPSTREAM_BUGS_PHASE_3-6.md`; `git log
--follow` crosses the merge.)

Two reasons it exists:

1. **It records where our port deliberately differs from upstream.** Every entry marked
   *Diverge* is a place our behaviour will not match a real Frappe instance — which
   matters when diffing against a live install, and when deciding whether a difference is
   a port bug or a fix. *Reproduce* means the port behaves as upstream does, on purpose,
   because the bug is user-visible and a faithful port shows it.
2. **It is the shortlist if you ever upstream anything.** Entries 42 to 49 are the
   candidates for the first upstream pull request; 49 goes to frappe-ui, not CRM.

Source refs: `crm/` = `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm`
(branch `main`, pinned at `6583bfcdc`; `specs/KNOWN_ISSUES.md` 11 has what moved since),
`frappe/` = `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe` (branch `version-15` —
the pairing CRM's own CI uses).

| # | Bug | Our stance |
|---|---|---|
| 1 | Hidden column skips the next column | **Diverge** — fixed |
| 2 | Kanban blanks the whole board for operator filters | **Diverge** — fixed |
| 3 | `@me` resolution is internally inconsistent | **Diverge** — normalised |
| 4 | `frappe._dict(filters)` raises on the tuple form | **Diverge** — accept both |
| 5 | Notification permission rules disagree on blank `to_user` | **Diverge** — we deny |
| 6 | SLA policy Desk link is unencoded | Frontend — unfixed |
| 7 | Holiday list Desk link is unencoded | Frontend — unfixed |
| 8 | Lead status types resolved against the **deal** status table | **Diverge** — fixed |
| 9 | Three `fetch_from` values on CRM Deal have an empty link field | **Reproduce** — inert |
| 10 | `remove_assignments` lets any caller skip the permission check | **Diverge** — flag ignored |
| 11 | `get_assigned_users` leaks assignee emails for invisible records | **Diverge** — guarded |
| 12 | `get_linked_docs_of_document` never checks read on the source | **Diverge** — guarded |
| 13 | Dashboard baseline period is one day too short | **Diverge** — fixed |
| 14 | Saved views and form scripts reachable via the generic route | **Diverge** — rules added |
| 15 | Mail-server validation has no connection timeout | **Diverge** — 10s timeout |
| 16 | **Any user can self-assign into any Lead or Deal via `ToDo`** | **Diverge** — route withheld |
| 17 | Profile's "send from" picker is empty for every non-manager | **Diverge** — reads opened |
| 18 | `permlevel` guards sorting and grouping, but not filtering | **Diverge** — filters rejected |
| 19 | Telephony settings screen is reachable by users who cannot read it | **Reproduce** — behaviour matched |
| 20 | The FX-provider credential sits on a world-readable record | **Diverge** — restricted |
| 21 | **Any Sales User can read a pending invitation's key and redeem it** | **Diverge** — gated + key hidden |
| 22 | A settings checkbox is the only gate on outbound calling | **Diverge** — stricter |
| 23 | Provider credentials embedded in the request URL | **Diverge** — stricter |
| 24 | No timeout on any provider call | **Diverge** — stricter |
| 25 | Webhook token compared with `==` (timing oracle) | **Diverge** — constant-time |
| 26 | Exotel reports `busy` as `Ringing` | **Reproduce** — user-visible |
| 27 | **Twilio webhooks are authenticated by a value that is not a secret** | **Diverge** — signature verified |
| 28 | Facebook page access token stored in plain text | **Diverge** — encrypted |
| 29 | **Synced Facebook leads have no owner, so nobody can see them** | **Diverge** — owner set |
| 30 | The duplicate check crashes on an unanswered optional question | **Diverge** — guarded |
| 31 | Reconciliation issues accumulate on every run | **Diverge** — cleared |
| 32 | A provider outage rolls back a deal's status change | **Diverge** — decoupled |
| 33 | Meta access tokens travel in the query string | **Diverge** — header |
| 34 | **A password-reset link never expires by default** | **Diverge** — zero means one hour |
| 35 | Forgot-password is rate-limited per caller, not per target | **Diverge** — stricter |
| 36 | `crm_products` money fields are computed client-side only | **Diverge** — computed on save |
| 37 | `create_email_account` has no permission check | **Diverge** — restricted to managers |
| 38 | Metadata doctypes have no row-level protection | **Diverge** — rules added |
| 39 | One missing name aborts a whole bulk update, and loses its report | **Diverge** — fixed |
| 40 | The first onboarding update for a user with no status is a 500 | **Diverge** — fixed |
| 41 | frappe-ui's Vite proxy plugin never returns on Windows | **Diverge** — worked around |
| 42 | "Unlink" in the delete dialog does nothing for a document linked through a Link field | **Reproduce** — for the upstream PR |
| 43 | A notification with no lead or deal behind it breaks the notifications panel | **Reproduce** — for the upstream PR |
| 44 | The contacts list's "Phone" quick filter searches a column the contact screens never fill | **Reproduce** — for the upstream PR |
| 45 | The Create Deal dialog keeps the last deal's form, and the Convert dialog reads the same one | **Reproduce** — reload is the workaround |
| 46 | Clicking a currency cell in a list files the formatted amount as the filter | **Diverge** — the amount is parsed |
| 47 | Home Actions lets a standard entry be turned into a separator, and Settings is gone | **Reproduce** — `seed_defaults --force` restores |
| 48 | A wrong URL with more than one segment draws a blank page | **Diverge** — router patched |
| 49 | The Getting started panel opens empty for a finished user on a browser that has not seen them | **Reproduce** — frappe-ui's code; once per browser profile |
| 56 | SLA skips non-working days without resetting the time of day | **Reproduce** — user-visible deadlines |

## 1. A hidden column causes the *next* column to be skipped

**Where:** `crm/api/doc.py:350-352`

`get_data` iterates `columns` and calls `columns.remove(column)` inside the loop.
Mutating a list while iterating it shifts every later index down by one, so the column
immediately after a hidden one is silently dropped from the list view.

**Us:** *Diverge.* We iterate a copy. Reproducing the bug would drop visible columns at
random. Locked by `test_removing_a_hidden_column_does_not_skip_the_next_one`.

---

## 2. Kanban blanks every column when the filter uses the operator form

**Where:** `crm/api/doc.py`, kanban branch

Upstream compares `filters.get(column_field) != kc.name`. For the operator form the left
side is a **list** (`["!=", "Closed"]`) and the right a string, so the comparison is
always unequal and *every* column is blanked — a blank board.

**Us:** *Diverge.* An `=` condition may pre-select or blank a column, exactly as
upstream; any other operator is preserved and AND-ed with the column's own constraint.
Upstream's equality path is reproduced exactly.

---

## 3. `@me` resolution is internally inconsistent

**Where:** `crm/api/doc.py:283-293`

Three inconsistencies in one block:
- `@me` replaces only the **first** occurrence (`list.index()`), while `%@me%` replaces
  **every** occurrence (a loop).
- The two checks are joined by `elif`, so a value holding both tokens resolves only one.
- Only the top level is scanned; nested values are missed.

**Us:** *Diverge.* Both tokens replaced everywhere, at any depth. Identical to upstream
for every filter the product actually sends, and resolves the inconsistency in the
direction upstream already took for `%@me%`.

---

## 4. `frappe._dict(filters)` raises on the documented tuple form

**Where:** `crm/api/doc.py:get_data`

`get_data` casts `filters` through `frappe._dict`, which raises on a list of 3-tuples —
one of the filter shapes Frappe itself accepts elsewhere (`make_filter_tuple`).

Worth noting our port had the *same* area wrong in a worse way: it coerced the tuple form
to `{}` and returned an **unfiltered** list rather than an error. Upstream at least fails
loudly.

**Us:** *Diverge.* Both shapes pass through to the shared translator; a genuinely
unusable type raises.

---

## 5. Frappe CRM contradicts itself on a blank notification recipient

**Where:** `crm/fcrm/doctype/crm_notification/crm_notification.py`

The two halves of the same permission rule disagree:

```python
# get_permission_query_conditions (:43) — the LIST rule
return f"`tabCRM Notification`.`to_user` = {frappe.db.escape(user)}"
#   a blank to_user matches nobody  →  row hidden from every list

# has_permission (:55-56) — the OBJECT rule
if not doc.to_user:
    return True
#   a blank to_user is readable by ANYONE
```

So a notification with no recipient is **invisible in every list yet readable directly
by any authenticated user**. Frappe's own two access paths reach opposite verdicts on
the same row.

**How reachable is it upstream?** More than it looks. `to_user` is `reqd: 1`, but in
Frappe `reqd` is **document-level validation, not a column constraint** — the column is
nullable, so `frappe.db.set_value`, a direct SQL insert, or a patch can produce a blank
that never passes through `validate`. Upstream's branch is therefore not dead code.

**Us:** *Diverge — we deny.* Our `to_user` is a `ForeignKey` with no `null=True`, so it
is NOT NULL at the database level and no saved row can reach the branch at all; our
schema is stricter than upstream's. The branch *is* reachable on an unsaved instance,
where returning `True` granted a read. We return `False`, so the list rule and the object
rule agree.

Nothing observable changes against upstream, and the failure direction is deny rather
than grant. Was gate blocker A1; resolved.

---

## 6. SLA policy Desk link is built unencoded

**Where:** `frontend/src/components/Settings/Sla/SlaPolicyView.vue:292`

Interpolates `step.value.data?.name` straight into a Desk URL.
`CRM Service Level Agreement` is `field:sla_name`, and Frappe permits `/`, `#`, `?` and
`&` in names (`frappe/model/naming.py:498` forbids only `<>`), so an SLA named
`"Gold / Priority"` produces a broken link.

**Us:** unfixed — it is in the frontend we copied, so it will manifest for us too.
Fix is `encodeURIComponent`. Upstream does this correctly elsewhere
(`ERPNextSettings.vue:724`).

---

## 7. Holiday list Desk link is built unencoded

**Where:** `frontend/src/components/Settings/Sla/SlaHolidays.vue:282`

Same defect: `/app/crm-holiday-list/${holidayList.name}` with no encoding.
`CRM Holiday List` is `field:holiday_list_name`.

**Us:** unfixed, same reasoning as #6.

---

## 8. A lead's status type is looked up in the deal status table

**Where:** `crm/fcrm/doctype/crm_status_change_log/crm_status_change_log.py:46,51`

```python
to_status_type = frappe.db.get_value("CRM Deal Status", doc.status, "type") if doc.status else None
```

Hardcoded to `"CRM Deal Status"` — but `crm_lead.py:92` calls this same function for
leads, whose statuses live in `CRM Lead Status` (a different doctype, `field:lead_status`).
A lead status like `"Contacted"` simply does not exist in the deal table, so the lookup
returns `None`.

**Consequence:** every status-change row written for a lead has an empty `from_type` and
`to_type` upstream. The columns exist, and for leads they are always blank.

**Us:** *Diverge — fixed.* We resolve against the correct table per doctype. Safe and
invisible: nothing reads `from_type`/`to_type` today — not the frontend, not the backend
— so no behaviour changes, and the data becomes usable if anything ever does read it.

---

## 9. Three `fetch_from` declarations on CRM Deal are malformed

**Where:** `crm/fcrm/doctype/crm_deal/crm_deal.json`

```
annual_revenue  <- .annual_revenue
website         <- .website
territory       <- .territory
```

Frappe's `fetch_from` is `<link_fieldname>.<source_fieldname>`, and these have an **empty
link fieldname**. `set_fetch_from_value` splits on `.`, takes an empty first element,
finds no such link field, and skips — so all three are silently inert. They were almost
certainly meant to read `organization.annual_revenue` and so on.

**Consequence:** a deal converted from a lead does not inherit the organization's revenue,
website or territory the way the schema claims it should.

**Us:** *Reproduce.* We simply do not declare them. Implementing what they *meant* would
populate three fields upstream leaves empty, which is user-visible. The other seven
`fetch_from` declarations in the app (5 on `CRM Contacts`, 1 each on
`CRM Telephony Agent` and `CRM Sales Hierarchy`) are well-formed and **are** implemented.

---

## 10. `remove_assignments` lets any caller skip the permission check

**Where:** `crm/api/doc.py:590-604`, `frappe/desk/form/assign_to.py:212-216`

The framework function does check permission — unless told not to:

```python
# frappe/desk/form/assign_to.py:215-216
if not ignore_permissions:
    frappe.get_doc(doctype, name).check_permission()
```

And the CRM's whitelisted endpoint takes that switch **from the caller** and passes it
straight down:

```python
# crm/api/doc.py:590
def remove_assignments(doctype, name, assignees, ignore_permissions=False):
    ...
    set_status(..., ignore_permissions=ignore_permissions)   # :603
```

So any authenticated user who knows a document's name can post
`ignore_permissions=true` and cancel assignments on a record they cannot write.
Because assignment grants access (`org_hierarchy.py` reads `ToDo`), that **revokes
another user's access** to the record.

Single-tenant, so the exposure is any employee against any lead — including unassigning
a manager from a deal they cannot open.

**Us:** *Diverge.* The parameter is still accepted so the API signature matches, and is
**ignored unconditionally**; write permission is always checked. No honest client sends
it, so this is invisible to the frontend.

**Verified independently** after the phase-3 agent reported it — both line references
above were confirmed against source before the divergence was accepted.

---

## 11. `get_assigned_users` leaks assignee emails for invisible records

**Where:** `crm/api/doc.py:608-625`

The endpoint returns the assignees of any document by name, with no read check on the
document itself. So a caller can learn who is working a lead they cannot see — an email
address per assignee, and a signal about who handles which account.

**Us:** *Diverge.* Guarded by a read check.

---

## 12. `get_linked_docs_of_document` never checks read on the source document

**Where:** `crm/api/doc.py`

Same shape as #11: the linked-documents list is returned for any document name without
first checking the caller can read it.

**Us:** *Diverge.* Same guard.

---

## 13. The dashboard's comparison baseline is one day too short

**Where:** `crm/api/dashboard.py:95-99`

```python
diff = frappe.utils.date_diff(to_date, from_date)   # Mar 1 -> Mar 31 == 30
prev_from_date = frappe.utils.add_days(from_date, -diff)
```

`date_diff` returns the **gap** between two dates, not the number of days in the range.
March 1st to March 31st is a gap of 30, but March is a **31-day month**. So the baseline
window is always one day shorter than the period it is compared against:

| Viewing | Days | Upstream baseline | Days |
|---|---|---|---|
| March | 31 | Jan 30 – Feb 28 | **30** |
| February | 28 | Jan 5 – Jan 31 | **27** |
| August | 31 | Jul 2 – Jul 31 | **30** |

**Consequence:** every percentage on the dashboard is inflated by roughly 3%, purely
from the shorter baseline, before anything has actually changed. **Eight months in twelve
are affected** — the four that happen to work are 31-day months following a 30-day month.

**Us:** *Diverge — fixed.* The baseline is now genuinely the same length as the period.

This departs from the usual rule of reproducing user-visible upstream behaviour. That
rule exists to avoid overriding decisions people rely on, and nobody relies on an
inflation they cannot see. It is not a design choice being overruled; it is a sum that is
wrong, and a manager reads it to judge whether the month went well.

### Option C — comparing whole calendar months, deliberately NOT done

Even with equal lengths, the baseline is **"the previous N days"**, not **"the previous
calendar month"** — March still compares against a window reaching back to 29 January.

That part is a **design choice, and upstream's is defensible**: a dashboard may
legitimately mean "the last 31 days". Changing it to compare whole calendar months would
be a product decision, not a bug fix — us deciding their design was wrong rather than
their arithmetic.

**If it is ever wanted**, it is a small change confined to `_period_before` in
`crm_app/api/dashboard.py`: take the first and last day of the preceding month instead of
counting backwards. The callers already use a half-open window (`>= prev_from`,
`< from_date`), so only the two returned dates move. Roughly ten lines, plus updating
`tests/test_dashboard_periods.py`, whose `test_march_baseline_reaches_into_january`
currently pins the *current* behaviour on purpose.

---

## 14. Saved views and form scripts are reachable through the generic route

**Where:** `crm/fcrm/doctype/crm_view_settings/`, `crm_form_script/`

Upstream registers no row-level rules for these doctypes, relying instead on DocType
**role permissions** — which this port does not model. So "no hook" meant "no protection"
here, and both were reachable through `/api/resource/` regardless of the carefully gated
endpoints in front of them:

- **private saved views readable by anyone**
- **`CRM Form Script` writable by any authenticated user** — and a form script is
  JavaScript that runs in every colleague's browser, so this was an XSS vector

**Us:** *Diverge.* Row-level rules added for three doctypes upstream does not register.
Not strictly an upstream bug — upstream has a protection layer we chose not to port — but
recorded here because the *effect* of the difference is ours to own.

---

## 15. Mail-server validation opens a connection with no timeout

**Where:** `frappe/email/doctype/email_account/email_account.py:156-188`

Upstream validates an Email Account's credentials by opening a live connection inside
`validate()` — `get_incoming_server()` for IMAP, `validate_smtp_conn()` for SMTP. Neither
passes a timeout, so `smtplib` and `imaplib` fall back to the system default.

**Consequence:** an unreachable or wrong hostname blocks the save until the OS gives up —
typically 20 to 130 seconds depending on platform and whether the name resolves. The user
watches a spinner instead of getting the error the form was written to display.

**Us:** *Diverge.* An explicit `MAIL_CONNECT_TIMEOUT`, default 10 seconds, so the failure
arrives while somebody is still looking at the form.

**The cost, stated plainly:** a genuinely slow but working relay — a loaded corporate
server, or one over a poor link — could exceed 10 seconds and be reported as broken when
it is merely slow. **If that happens, raise the setting; do not remove it.** Recorded in
the module docstring, the setting comment and
`tests/test_mail_validation.py::test_the_connect_timeout_is_passed_to_the_backend`.

Worth knowing alongside this: phase 3 skipped the validation entirely, on the grounds
that the port had no mail layer. It has one — Django's SMTP backend wraps `smtplib` — so
the check is a few lines. The gap mattered because the failure was silent: a mistyped
password saved cleanly and the first anyone knew was that invitations never arrived.

---

## 16. Any user can self-assign into any Lead or Deal through `ToDo`

**Where:** `frappe/desk/doctype/todo/todo.json`, `todo.py:38,163`,
`crm/permissions/org_hierarchy.py:41`

**The most severe entry in this file.** The others leak a field; this one hands over the
record.

`org_hierarchy` grants access to a Lead or Deal when a `ToDo` row says you are assigned
to it. `ToDo` grants role **`All`** create/write/delete, and nothing validates the
document a `ToDo` points at. So any authenticated user can create the row that grants
them access:

```
POST /api/resource/ToDo
     {"allocated_to": "<self>", "reference_type": "CRM Deal",
      "reference_name": "<any deal>"}
```

Five guards could have caught it. None does:

| Guard | What it actually does |
|---|---|
| `todo.json` permissions | Role `All`: `create/read/write/delete = 1` |
| `todo.py:163` `has_permission` | Non-System-Manager falls to `doc.allocated_to == user` — **true when self-assigning** |
| `todo.py:38` `validate()` | Builds the assignment message. Never looks at the reference |
| Link validation (`base_document.py:830`) | `frappe.db.get_value(...)` — existence only |
| REST create (`api/v1.py:43`) | `insert()` → `check_permission("create")` on the ToDo itself |

**The permission check is not bypassed — it passes**, on data the caller supplied. Nothing
errors, so nothing logs. That is what makes it hard to notice and easy to write tests
straight past: ours tested `assign_to.add`, which is correctly gated, and never the table
beneath it.

**Root cause: one table, two jobs.** `ToDo` is both a personal task list, which everyone
must be able to write, and an assignment record, which grants access and must be
privileged. One permission setting covers both and the permissive job wins. Frappe CRM
does not even use the first job — CRM tasks are `CRM Task` — so the permissive default is
inherited from Frappe Desk, which this port has no equivalent of.

**Us:** *Diverge.* `/api/resource/ToDo` is withheld entirely (`routable=False`) rather
than guarded, because nothing calls it — the frontend assigns through
`frappe.desk.form.assign_to.add`, which checks write permission on the document first. The
permission rule we would otherwise have written is specified in full in
`specs/UNROUTED_DOCTYPES.md`, along with the observed exploit.

**Traced in source, not executed** — no Frappe instance was run, because this machine
cannot run one. Every line reference above was read from `frappe` `version-15` and `crm`
`main`.

---

## 17. The Profile "send from" picker is empty for every non-manager

**Where:** `crm/frontend/src/components/Settings/Profile/UserEmailSettings.vue:139`,
`crm/frontend/src/components/Settings/Settings.vue:109`,
`frappe/email/doctype/email_account/email_account.json`

Settings → Profile → Email offers a list of outgoing email accounts, so a user can choose
which address their mail is sent from:

```js
const emails = createListResource({
  doctype: 'Email Account',
  fields: ['name', 'email_id'],
  filters: { enable_outgoing: 1 },
})
```

Three facts collide:

1. `Email Account` grants read to **System Manager** only. `Inbox User` also has it, but
   **Frappe CRM never grants that role** — zero references in the repo.
2. The **Profile** entry in `Settings.vue` carries **no `condition`**, unlike the Email,
   User Management and Telephony sections, which are all `isManager()`-gated.
3. `frappe.get_list` filters by permission and returns `[]` rather than erroring.

So every Sales User can open the screen, and the picker is **silently empty**. No error,
no explanation — the feature simply does not work for the majority of users, and looks
like there are no email accounts configured.

Either the screen should be manager-gated like its siblings, or `Email Account` should
grant read more widely. Upstream does neither.

**Us:** *Diverge.* Reads are open (`crm_app/permissions/platform_docs.py`), so the picker
works. The cost is that ordinary users can see fields upstream would not show them at
all, which is why `EmailAccount.RESTRICTED_FIELDS` narrows the record to what the picker
actually reads. See `specs/SECURITY_MODEL.md`.

---

## 18. `permlevel` guards sorting and grouping, but not filtering

**Where:** `frappe/model/db_query.py:1544` (`validate_fieldlevel_permissions_for_sort`),
called at `:589` and `:593`; `prepare_filter_condition` at `:1088`

Frappe restricts per-field reads with `permlevel`, and the query layer defends it in two
of the three places a caller can name a field:

| Parameter | Guarded? |
|---|---|
| `order_by` | **yes** — `validate_fieldlevel_permissions_for_sort` (`:589`) |
| `group_by` | **yes** — same function (`:593`) |
| `filters` | **no** — `prepare_filter_condition` never consults `permlevel` or `get_permitted_fields` |

The asymmetry is the tell: somebody reasoned about the leak for sort and group and missed
filters — which is the **stronger** oracle of the three. Sorting reveals relative order;
a filter answers a direct question, and `like` with a growing prefix recovers a value one
character per request.

This is the same defect we had, arrived at from the other direction: ours came from
storing a credential in a column Frappe never creates. The fix is identical — every
parameter that names a field must ask the same question.

**Reachability in Frappe CRM: latent, not live.** The pattern needs a role holding
permlevel-0 read *without* permlevel-1 read. `CRM Twilio Settings` is the CRM's only
doctype with permlevel fields, and it grants **both** levels to the same two roles
(System Manager, Sales Manager), so there is no gap to exploit today. On any site that
uses `permlevel` the way it is meant to be used — the salary-on-Employee pattern — it is
live.

**Us:** *Diverge — stricter.* All four field-naming parameters route through
`field_security.is_hidden`, so a field hidden from output is hidden from questions about
it. Kept even after the credential moved to ciphertext: the reasoning covers every future
secret, and a redundant check is cheaper than rediscovering why it was removed.

**Traced in source, not executed** — no Frappe instance was run.

---

## 19. The Telephony settings screen is reachable by users who cannot read it

**Where:** `crm/frontend/src/components/Settings/Settings.vue:214-218`,
`crm/fcrm/doctype/crm_twilio_settings/crm_twilio_settings.json`

`Settings.vue` gates entries with `condition: () => isManager()`. **Eleven** entries carry
it — Users, Invite User, Sales Hierarchy, Email, Brand, Defaults, WhatsApp, ERPNext, Lead
Syncing among them. **Telephony does not:**

```js
{
  label: __('Telephony'),
  icon: PhoneIcon,
  component: markRaw(TelephonyPage),      // <- no condition, unlike its siblings
},
```

But `CRM Twilio Settings` and `CRM Exotel Settings` grant read to **System Manager and
Sales Manager only**, at every permlevel. So a Sales User can open the screen and the
fetch is refused.

**Worse than #17.** There, `get_list` returns `[]` and the picker merely looks empty.
These are **Single** doctypes fetched with `get_doc`, which raises `PermissionError` — so
the screen *errors* rather than looking empty.

Same root as #17: a settings entry that omits the role condition its siblings carry, with
nothing tying the two together, so the UI and the permission table drift apart silently.

**Us:** *Reproduce.* Reads stay manager-only. This is a **user-visible upstream behaviour
and a cosmetic UI defect, not a permission problem** — the fix belongs in the missing
`isManager()`, not in weakening a credential's protection so an admin screen renders for
non-admins. Note this is deliberately **not** the answer we gave for #17, where the screen
served an ordinary user's own feature. The decision turns on what the screen is *for*.

---

## 20. The exchange-rate credential sits on a world-readable record

**Where:** `crm/fcrm/doctype/fcrm_settings/fcrm_settings.json`

`FCRM Settings` grants `read: 1` to **Sales User** — correctly, and by necessity: it holds
`crm_timeline_timestamp_format`, which the activity timeline reads on every screen in the
product (`stores/settings.js`).

It also holds `access_key`, the credential for the configured exchange-rate provider, as
plain `Data` with **no `permlevel`**. So every Sales User can read it.

The same repository's authors did use `permlevel: 1` for exactly this purpose on
`CRM Twilio Settings.api_key` and `twiml_sid`, which is what makes this read as an
oversight rather than a decision: the mechanism was to hand and applied two doctypes away.

Low value on its own — an FX-rate API key, not a mail server — but it is a credential
handed to every user of the product, and the record it lives on can never be closed.

**Us:** *Diverge.* `FCRMSettings.RESTRICTED_FIELDS = ("access_key",)` — managers see it,
which is all the settings screen needs; nobody else does, and it cannot be probed through
filters either. Phase 1 flagged this field and correctly declined to hide it, because the
only tool available then was all-or-nothing and would have broken that screen.

---

## 21. Any Sales User can read a pending invitation's key and redeem it

**Where:** `crm/api/__init__.py:83` (`accept_invitation`),
`crm/fcrm/doctype/crm_invitation/crm_invitation.json`

**The most serious entry in this file.** #16 grants a record; this grants an account.

`accept_invitation` takes a key from the query string, looks the invitation up **by key
alone**, and acts on it:

```python
def accept_invitation(key: str | None = None):
    result = frappe.db.get_all("CRM Invitation", filters={"key": key}, pluck="name")
    invitation = frappe.get_doc("CRM Invitation", result[0])
    is_new_user = invitation.accept()
    ...
    if is_new_user:
        user = frappe.get_doc("User", invitation.email)
        frappe.local.response["location"] = user._reset_password()   # password-reset link
    else:
        frappe.local.login_manager.login_as(invitation.email)         # straight in
```

No authentication, and **no binding between the key and whoever presents it**. That is
defensible on its own — it is a link in an email, and the key is the secret.

The problem is that the key is not secret. `crm_invitation.json` grants **Sales User
`read: 1`**, and `key` is a plain `Data` field with no `permlevel`. So:

```
GET /api/resource/CRM Invitation?fields=["email","role","key"]&filters=[["status","=","Pending"]]
```

returns every open invitation with its redemption token. A Sales User who reads a pending
**System Manager** invitation and visits the link becomes that System Manager — or, if the
invitee has not yet set a password, receives a password-reset link for their account.

**Prerequisite:** a pending invitation for a role above the attacker's own. `invite_by_email`
is manager-only, so the attacker cannot create one — they have to wait for an admin to
invite someone. That is an onboarding window, not an exotic condition.

**Us:** *Diverge, twice.*

* `CRM Invitation` is **manager-only** — reads included. Upstream's Sales User read is
  exactly what makes the key reachable.
* `key` is in `SENSITIVE_FIELDS`, so it never reaches the wire even for a manager, cannot
  be selected explicitly, and cannot be probed through filters. `tasks.py` reads the
  attribute directly when it builds the email, which is the only thing that ever needs it.

Neither layer costs anything: `InviteUserPage.vue` is the sole consumer, it is
`isManager()`-gated, and it asks for `name`, `email` and `role`.

**Both were put in place before this port implements `accept_invitation` at all** — the
endpoint is missing (`specs/KNOWN_ISSUES.md` #2), so nothing can currently redeem a stolen
key. That is deliberate sequencing: the protection is in place first, so that building the
endpoint cannot quietly open the hole.

**Traced in source, not executed** — no Frappe instance was run.

---

## 22. A settings checkbox is the only thing gating an outbound call integration

**Where:** `crm/integrations/api.py:36-43`

`is_call_integration_enabled` reads one thing per provider:

```python
"twilio": bool(frappe.db.get_single_value("CRM Twilio Settings", "enabled")),
```

That is not a bug upstream — Frappe has no deployment-level feature flag, so the checkbox
on the settings singleton is the only switch there is, and the doctype is manager-only.

**Us:** *Diverge — stricter.* `crm_app/integrations/api.py:_provider_enabled` is an **and**
of the deployment flag (`ENABLE_TWILIO` / `ENABLE_EXOTEL`) and the settings checkbox.

`PHASE_7_INTEGRATIONS.md` §3 requires every integration behind its own flag, off by
default. If the checkbox alone could enable it, the flag would be advisory: anyone who can
write the settings row — a Sales Manager, per A4 — could switch on outbound calling in a
deployment whose operator deliberately opted out. Making the flag the outer gate means
turning an integration on is a *deployment* decision and configuring it is an
*administrative* one, which is the right split.

Costs nothing when both are set, and `test_a_settings_row_alone_does_not_enable_a_provider`
pins it.

---

## 23. Provider credentials are embedded in the request URL

**Where:** `crm/integrations/exotel/handler.py:131-140`

```python
return "https://{api_key}:{api_token}@{subdomain}/{version}/Accounts/{sid}/{action}".format(...)
```

Every Exotel endpoint is built with the API token *inside the URL string*. `requests` turns
that into the same `Authorization: Basic` header it would send for `auth=(key, token)`, so
the wire behaviour is identical — but the URL is a string that lives in the process, and a
URL is the one component of a failed request that reliably ends up in a traceback, a log
line, an error page, and a `Referer` header on any redirect.

**Us:** *Diverge — stricter.* `crm_app/integrations/exotel/client.py` builds the URL without
userinfo and passes `auth=_credentials()`. `integrations/http.redact()` exists for URLs
arriving from anywhere else. Costs nothing; `test_the_endpoint_url_carries_no_credentials`
pins it.

---

## 24. No timeout on any provider call

**Where:** `crm/integrations/exotel/handler.py:99` and `:145`

`requests.post(endpoint, data={...})` and `requests.get(endpoint)` — no `timeout`, so both
inherit `requests`' default of *none*. A provider that accepts the TCP connection and then
never responds holds the worker thread until the OS gives up.

Exactly the shape of #15, which this project already fixed once for mail validation.

**Us:** *Diverge — stricter.* `crm_app/integrations/http.py`: `(5, 20)` connect/read, three
attempts, backoff, retrying only connection errors and 429/502/503/504. `PHASE_7_INTEGRATIONS.md`
§3 makes this an acceptance criterion rather than a preference.

---

## 25. The webhook token is compared with `==`

**Where:** `crm/integrations/exotel/handler.py:161-168`

```python
is_valid = key and key == webhook_verify_token
```

Exotel does not sign its requests — upstream says so in a comment — so this shared secret is
the **entire** authentication for a public, `allow_guest` write endpoint. Anyone holding it
can forge call events into the CRM.

`==` on `str` short-circuits at the first differing byte. The response time therefore
depends on how many leading bytes the guess got right, and the token is recoverable from
outside one byte at a time. It is the same defect as the `like`-filter password recovery in
`SECURITY_MODEL.md`, reached through timing instead of filters — and the remote attacker
here needs no account at all.

**Us:** *Diverge — stricter.* `hmac.compare_digest`, plus an explicit refusal when no token
is configured. `test_the_comparison_is_constant_time` asserts the mechanism, since timing
cannot be asserted reliably.

---

## 26. `busy` is reported as `Ringing`

**Where:** `crm/integrations/exotel/handler.py:232-233` and `:248-249`

Both the inbound and outbound status maps send Exotel's `busy` to `Ringing`. `CRM Call Log`
has a `Busy` status in its own Select options, so the value exists and is simply not used.

**Us:** *Reproduce.* The status renders in the activity timeline, so a caller who got a busy
signal shows as "Ringing" — wrong, and **user-visible**, which is the rule's test. Correcting
it would make this port disagree with upstream for identical call data.
`test_busy_maps_to_ringing_deliberately` pins the reproduction so nobody quietly tidies it.

---

## 27. Twilio webhooks are authenticated by a value that is not a secret

**Where:** `crm/integrations/twilio/api.py:12-26`

```python
account_sid = frappe.utils.cstr(args.get("AccountSid"))
if not account_sid or account_sid != frappe.utils.cstr(twilio.account_sid):
    frappe.throw(_("Invalid Twilio account"), frappe.PermissionError)
```

That is the whole of the authentication on four `allow_guest` endpoints. **An Account SID is
not a secret**: Twilio puts it in every webhook it sends, it is displayed in the console, and
it is in any log that captured a request. Anyone who has seen one webhook can forge all the
rest — which writes call logs into the CRM and, through `voice`, returns the TwiML that
decides where an inbound call is routed.

Twilio signs every request with `X-Twilio-Signature` (HMAC-SHA1 over the URL plus the
sorted POST parameters, keyed with the account auth token). Upstream never checks it.

**Us:** *Diverge — stricter.* `twilio/client.validate_signature`, compared in constant time,
on all four endpoints. The SID comparison is kept as well: it costs nothing and catches a
correctly-signed request from a different account. `PHASE_7_INTEGRATIONS.md` §3 makes
signature verification an acceptance criterion and says explicitly not to skip it.

---

## 28. A Facebook page access token is stored in plain text

**Where:** `crm/lead_syncing/doctype/facebook_page/facebook_page.json`

`Lead Sync Source.access_token` is a `Password` fieldtype, so upstream keeps it in the
encrypted `__Auth` table. `Facebook Page.access_token` — written by
`create_facebook_page_in_db` (`facebook.py:171-182`) — is plain **`Small Text`**, in the
document table, with no `permlevel`.

A page access token reads every lead the page has ever collected and can post as the page.
The mechanism to protect it was to hand and used one doctype away.

**Us:** *Diverge — stricter.* `SENSITIVE_FIELDS` and `ENCRYPTED_FIELDS` on both tokens.
`tests/test_credential_fields.py` would have failed on it regardless, which is the point of
that test existing before this phase rather than after.

---

## 29. Synced Facebook leads have no owner, so nobody can see them

**Where:** `crm/lead_syncing/doctype/lead_sync_source/facebook.py:52-59`

```python
return frappe.get_doc({"doctype": "CRM Lead", **crm_lead_data}).insert(ignore_permissions=True)
```

`crm_lead_data` is the mapped form answers plus `source`, `facebook_lead_id` and
`facebook_form_id`. **No `lead_owner`.**

`crm_lead.json` declares no default for it and nothing in `crm_lead.py` fills it — the
browser does, before a manual create (`LeadModal.vue:187-189`). A sync has no browser. So
every lead Facebook produces is owned by nobody, and `org_hierarchy`'s rule makes it visible
to managers and System Managers only. No error, no warning.

**Us:** *Diverge.* `sync.DEFAULT_LEAD_OWNER = "Administrator"`. Reproducing this would mean
the feature does not work. `AS_BUILT.md` §4 is equally clear that stamping "whoever ran the
sync" is the wrong fix — it claims records for one person, unrecoverably — so the sync
account owns them and assignment hands them out.

---

## 30. The duplicate check crashes on an unanswered optional question

**Where:** `crm/lead_syncing/doctype/lead_sync_source/facebook.py:134-138`

```python
validation_filters = {crm_field: lead_data[crm_field] for crm_field in field_mapping.values()}
```

`lead_data` holds only the questions the person actually answered — Facebook omits the rest.
Any mapped-but-unanswered optional question makes this a `KeyError`, which the caller catches
as a generic failure and logs. The lead never arrives, and the log says "Failure" with a
traceback about a missing key rather than anything about the form.

**Us:** *Diverge.* The filter is built from the fields actually present. Identical query for
a complete payload; survives an incomplete one.

---

## 31. Reconciliation issues accumulate on every run

**Where:** `crm/fcrm/doctype/crm_product/reconcile_job.py` (`_record_issues`)

Issues are appended to `ERPNext CRM Settings.sync_issues` unconditionally. The
reconciliation is enqueued whenever the settings are saved and on demand, so a persistent
orphan produces a new identical row every time — and the settings screen lists them all.

**Us:** *Diverge.* Idempotent on `(product, kind)` among undismissed rows. A dismissed issue
that recurs is recorded again, which is the behaviour you want.

---

## 32. A provider outage rolls back a deal's status change

**Where:** `crm/fcrm/doctype/erpnext_crm_settings/erpnext_crm_settings.py:511-635`

`create_customer_in_erpnext` runs from a `doc_events` hook on CRM Deal, and
`create_customer_from_deal` ends in `_log_and_throw` on any failure. So if ERPNext is
unreachable, or returns nothing, **the user's status change is thrown away** — they moved a
deal to Won and got an error about a system they may not know exists.

**Us:** *Diverge.* The failure is logged and the save stands; `erpnext_customer` stays empty
and the next save retries. `PHASE_7_INTEGRATIONS.md` §3: *"an unreachable provider must never
break lead or deal CRUD."*

---

## 33. Meta access tokens travel in the query string

**Where:** `crm/lead_syncing/doctype/lead_sync_source/facebook.py:70-74`, `:154`, `:187-192`

```python
params = {"access_token": self.access_token, "fields": "id,created_time,field_data", ...}
return make_get_request(url, params=params).get("data", [])
```

Every Graph call passes the token as a **query parameter**. Meta documents both that and the
`Authorization: Bearer` header, and the two are equivalent to Graph — but a query string is
the worst available place for a long-lived credential. It lands in Meta's access logs, in
any proxy between, in this process's own request logging, and in a `Referer` on any redirect.
Graph's pagination then hands the token back inside its `next` URL, so following the cursor
spreads it further.

A page access token reads every lead the page has collected and can post as the page (#28).

**Us:** *Diverge — stricter.* `graph._split_token` moves it into the header, and
`_strip_token` removes it from the `next` URL before the cursor is followed. Found by the
phase-7 review, which is what `http.redact` was already anticipating.

---

## 34. A password-reset link never expires by default

**Where:** `frappe/core/doctype/user/user.py:955-962`

```python
reset_password_link_expiry = cint(
    frappe.db.get_single_value("System Settings", "reset_password_link_expiry_duration")
)
if (
    reset_password_link_expiry
    and now_datetime() > last_reset_password_key_generated_on + timedelta(seconds=...)
):
    result.message = _("The reset password link has been expired")
```

The setting defaults to **0**, and `if reset_password_link_expiry and …` short-circuits on
zero — so out of the box the expiry check does not run at all and a reset link is valid
forever. It stops working only when it is used, or when another is issued for the same
account.

A link that never expires turns a mail archive into a credential store: anyone who later
reaches an old inbox, a backup of one, or a forwarded thread has a working password reset.
It is the same shape as the invitation-key exposure phase 4 closed (#21), reached through a
mailbox rather than the API.

**Us:** *Diverge.* `PASSWORD_RESET_LINK_EXPIRY_MINUTES`, default 60, and **zero is
redefined as 60 rather than as infinity** — `frappe_core/password_reset.py:expiry_minutes`.
Upstream's "0 disables the check" is a footgun, and a deployment that sets it to zero
meaning "no limit" gets an hour instead of a permanent one.
`test_a_zero_setting_still_expires_a_key` pins the behaviour rather than the setting.

---

## 35. Forgot-password is rate-limited per caller, not per target

**Where:** `frappe/core/doctype/user/user.py:1041-1042`

```python
@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=get_password_reset_limit, seconds=60 * 60)
def reset_password(user: str) -> None:
```

`rate_limit` buckets on the caller's IP alone. Upstream is careful here in every other
respect — the response is deliberately invariant to avoid enumeration (#3 in this phase's
notes) — but the cap counts *requests*, not *addresses*, so one caller can send the hourly
allowance to a different victim each time.

The harm is small and real: unsolicited "reset your password" mail attributed to your
product, aimed at whoever the caller names.

**Us:** *Diverge — stricter.* `@rate_limit(limit=10, seconds=3600, key="user")` puts the
requested address in the bucket as well, so the cap is per IP **and** per target.
`frappe_core.security.rate_limit` already supported `key` from phase 3; this is the first
caller to use it.

---

## 36. `crm_products` money fields are computed client-side only

`crm/fcrm/doctype/crm_products/crm_products.py:112-195` builds a **JavaScript** form
script; `amount`, `net_amount`, `discount_amount`, `total` and `net_total` are all
computed in the browser and posted up. Nothing server-side recomputes or validates them,
so a hand-rolled request can set a deal's `total` to anything.

**Diverged: computed on save.** For an honest client the values are identical, so nothing
user-visible changes. Port: `backend/crm_app/models/taxonomy.py:recalculate_parent_totals`.

Note the `net_total` rule is subtle and was ported exactly: `net_total = sum(net_amount)
or total`, **unless** a discount was applied, in which case a zero sum stands. Dropping
the second branch makes a 100%-discounted deal report its full gross value.

## 37. `crm.api.settings.create_email_account` has no permission check

`crm/api/settings.py:5-53` is `@frappe.whitelist()` with no `frappe.only_for`. Upstream
relies on the Email Account doctype's own role permissions, which this port does not
model — so ported verbatim it would let any authenticated user create a
credential-bearing mail account and mark it `default_outgoing`, redirecting the system's
outbound mail.

**Diverged: restricted to System Manager / Sales Manager.**
Port: `backend/crm_app/api/settings.py`.

## 38. Metadata doctypes have no row-level protection

`CRM View Settings`, `CRM Form Script` and `CRM Fields Layout` are ordinary doctypes
upstream, protected by the DocType's `permissions` table (System Manager for write). This
port does not model DocType role permissions, and its generic `/api/resource/` route
treats "no permission hook" as "allowed" — so all three were world-readable and
world-writable to any authenticated user.

Two consequences:

* **private saved views leaked** — `CRM View Settings` is per-user, and `get_views`
  scoped correctly, but the generic route bypassed it;
* **`CRM Form Script` was an XSS vector** — `get_data` serves the script to every client,
  which executes it, so any Sales User could have run code in every colleague's browser.

**Diverged: row-level rules registered for all three** (`crm_app/permissions/metadata_docs.py`).
Read follows the list rule; write is admin-only. This makes six doctypes with row rules
where upstream registers three, and `test_exactly_the_intended_doctypes_have_row_rules`
pins that set down.

Worth noting the general shape: *any* doctype this port registers is a public read/write
surface unless a hook says otherwise. Upstream's default is the opposite.

## 39. One missing name aborts a whole bulk update, and loses its report

**Where:** `frappe/desk/doctype/bulk_update/bulk_update.py:82-124` (`_bulk_action`),
found on 16 Sep 2026 while porting `submit_cancel_or_update_docs` for the list view's
bulk edit.

```python
for idx, docname in enumerate(docnames, 1):
    doc = frappe.get_doc(doctype, docname)
    try:
        ...
        frappe.db.commit()
    except Exception:
        frappe.log_error("Bulk action failed")
        failed.append(docname)
        frappe.db.rollback()
return failed
```

The `get_doc` sits *outside* the `try`. A name that no longer exists - a row someone
deleted between the list loading and the click, which is exactly the situation a bulk
action on a shared list runs into - raises `DoesNotExistError` straight out of the loop.
Every document before it is already committed, every document after it is untouched,
and the caller gets an error instead of the `failed` list, so it cannot tell which. The
`except Exception` two lines down was written for precisely this class of failure and
never sees it.

**Us:** *Diverge - fix.* `crm_app/bulk_update.py:bulk_action` looks the name up inside
the per-document guard, so a missing document joins `failed` like a refused or invalid
one, and the rest of the batch is reported. User-visible upstream (a spinner, then an
error dialog, for a batch that half-applied), so reproduced as the outcome upstream's
own handler intended rather than the one it delivers.

---

## 40. The first onboarding update for a user with no status is a 500

**Where:** `frappe/onboarding.py:13-25` (`update_user_onboarding_status`), found on
28 Sep 2026 while porting the pair frappe-ui's `useOnboarding` calls (FINDINGS.md 39).

```python
onboarding_status = frappe.db.get_value("User", frappe.session.user, "onboarding_status")
onboarding_status = frappe.parse_json(onboarding_status)
onboarding_status[appName + "_onboarding_status"] = steps
```

`frappe.parse_json` returns its argument unchanged when it is not a string, so for a
user whose column is still `NULL` the second line yields `None` and the third subscripts
it: `TypeError`, 500. The sibling `get_onboarding_status` guards the same value with
`if onboarding_status else {}`; the writer does not. Every user starts with a `NULL`
column, so the very first "skip" or "done" click in the onboarding panel fails for
everyone, and works from the second click on only if something else wrote the column
first. The frontend fires the call without awaiting it, so the failure is a console
error and a step that does not stay ticked.

**Us:** *Diverge - fix.* An unset status reads as `{}` on both endpoints
(`crm_app/api/onboarding.py:_status_of_current_user`), so the first update stores the
key like any later one. User-visible upstream, so reproduced as the outcome the
sibling endpoint already intends.

---

## 41. frappe-ui's Vite proxy plugin never returns on Windows

**Where:** `frappe-ui` 1.0.0-beta.29, `vite/utils.js:findBenchPath` (lines 25-36) and
`findAppName` (48-64), reached from `vite/frappeProxy.js:7` at every dev-server start.
Found 29 Sep 2026 when `yarn dev` stopped after its first line (FINDINGS.md 48). A
library defect rather than a CRM or framework one, kept here because it is the same
kind of record.

```js
let currentDir = path.resolve('.')
while (currentDir !== '/') {
  if (fs.existsSync(path.join(currentDir, 'sites')) && fs.existsSync(path.join(currentDir, 'apps'))) {
    return currentDir
  }
  currentDir = path.resolve(currentDir, '..')
}
```

A Windows path's root is `D:\`, never `/`, and `path.resolve('D:\\', '..')` is `D:\`
again, so outside a bench the loop has no exit. The fix upstream is
`while (currentDir !== path.dirname(currentDir))`, which stops at the root on both
platforms.

**Us:** *Diverge - work around.* `frappeProxy: false` in `vite.config.js`, with the
proxy and port the plugin would have set written out by hand. `siteBanner` and
`buildConfig` reach the sibling loop only when given a `frontendRoute`, which the
config does not pass.

## 42. "Unlink" in the delete dialog does nothing for a document linked through a Link field

**Where:** `crm/api/doc.py:721-749` (`remove_doc_link`), reached from
`remove_linked_doc_reference` (769-792) and the delete dialog's "Unlink all"
(`DeleteLinkedDocModal.vue:203`). Found 30 Sep 2026 in the Organizations pass of the
browser testing (FINDINGS.md 56).

```python
linked_doc_data.update({"reference_doctype": "", "reference_docname": ""})
linked_doc_data.save(ignore_permissions=True)
```

`get_linked_docs_of_document` lists two kinds of document: those that name the record in
a Link field (`frappe.model.delete_doc.get_linked_docs`: a deal's `organization`) and
those that name it in the generic reference pair (`get_dynamic_linked_docs`: a task, a
note, a call log, a notification). `remove_doc_link` blanks only the pair. On a CRM Deal
those two keys are not fields, so `update` sets two attributes the save ignores: the deal
keeps its `organization`, the dialog reloads with the deal still listed, and deleting the
organization is then refused by the framework's link check ("Cannot delete or cancel
because CRM Organization ... is linked with CRM Deal ..."). Unlink works for what it was
written for, a lead's or deal's tasks, notes and calls, and is a no-op for an
organization's deals. The only way through the dialog is "Delete", which removes the deal.

**Us:** *Diverge, by the owner's decision of 16–17 Oct 2026.* The delete dialog sends the
doctype and name of the document being deleted, and `remove_linked_doc_reference` clears
every direct Link field on the linked document that points at it, using the same link map
that built the dialog. The fix to send upstream is the same: have the dialog send the
deleted document, then make `remove_doc_link` clear the Link field pointing at it as well
as the generic reference pair. See FINDINGS.md 56.

## 43. A notification with no lead or deal behind it breaks the notifications panel

**Where:** `frontend/src/components/Notifications.vue` (`getRoute`, and the `RouterLink`
it feeds), with the data from `crm/api/todo.py:126-131` (`get_redirect_to_doc`) and
`crm/fcrm/doctype/crm_notification/crm_notification.py:61-84` (`notify_user`). Found
30 Sep 2026 in the browser testing (FINDINGS.md 62).

```js
function getRoute(notification) {
  let params = { leadId: notification.reference_name }
  ...
  return { name: notification.route_name, params: params, hash: notification.hash }
}
```

When a task is assigned, the notification's reference is the task's own
`reference_doctype` / `reference_docname`, which are empty for a task made on the Tasks
page and not tied to a lead or deal. `get_notifications` still answers
`route_name: "Lead"` for it (its ternary has only two outcomes) with an empty
`reference_name`. The panel renders every row as a `RouterLink` to that route, and
vue-router throws `Missing required param "leadId"` for an empty id, inside the render.
One such row and the panel never appears for that user: clicking the bell does nothing.

**Us:** *Reproduce, pending the owner's decision.* The port stores and serves the same
rows, and the Vue file is upstream's unchanged. The fix belongs in the frontend: render a
row that has no reference as plain text, or send it to the Tasks page. A candidate for
the same pull request as 42.

## 44. The contacts list's "Phone" quick filter searches a column the contact screens never fill

**Where:** `crm/install.py:514` (`"Contact": ["status", "email_id", "phone"]`),
`crm/overrides/contact.py:24,45` (the list's column is `mobile_no`),
`crm/api/contact.py:77-78`, `ContactModal.vue:153` and `useContactFields.ts:131,167`
(every number added or picked on a contact is flagged `is_primary_mobile_no`). Found
1 Oct 2026 in the Contacts pass (FINDINGS.md 67).

A contact has two mirror columns, `phone` and `mobile_no`, each copied from the row
flagged for it (framework `contact.py:199-222`). Everything the contact screens do flags
a number as the primary *mobile*: the New Contact dialog, `create_new` for both of its
field names, and the dropdown's pick, which always sends `mobile_no`. The one place that
sets `is_primary_phone` is a lead's conversion, for a lead that has a `phone`
(`crm_lead.py:236`). So for any contact made or edited in the Contacts screens,
`Contact.phone` is empty. The list shows the number in a column that reads `mobile_no`,
while the quick filter labelled Phone filters on `phone`. Typing a number that is plainly
on screen into that quick filter finds nothing.

**Us:** *Reproduce.* The port installs the same three quick filters and fills the same
columns the same way. The Mobile No field in the full Filter menu works, since it reads
the column that is filled. The fix upstream is one word in `install.py`: `mobile_no`.

---

## 45. The Create Deal dialog keeps the last deal's form, and the Convert dialog reads the same one

**Where:** `data/document.js:110-111` (`useDocument(doctype)` with no name hands out one
`documentsCache[doctype]['']` object for the whole page session), `DealModal.vue:99,179,
214-218` (binds the form to it, nulls `contact` but not `organization` when a switch is
off, and on success only navigates), `ConvertToDealModal.vue:129` (the same
`useDocument('CRM Deal')`), `crm_deal.py:460-468` (`doc.get("organization") or
create_organization(doc)`). Found 6 Oct 2026 in the Deals pass (FINDINGS.md 74) and
confirmed the same day on the upstream demo.

Three things follow from the one shared object.

1. After a deal is created the form is never cleared, so the next Create Deal starts
   from the last deal's values. Visible, and easy to type over.
2. Once "Choose Existing Organization" has been used, its pick stays in
   `deal.doc.organization` when the switch is turned off; the field is hidden with the
   section. `createDeal()` nulls `contact` for the equivalent case
   (`DealModal.vue:179`) and does nothing for `organization`. `create_deal` then prefers
   `doc.organization` to the organization details typed, so the new deal lands on the
   old organization and the typed organization is never created. Invisible until the
   deal opens.
3. The Convert to Deal dialog's deal form is the same object, so whatever the last
   Create Deal left in it (`website`, `territory`, `annual_revenue`, `industry`,
   `no_of_employees`, `status`, `deal_owner`, and `organization` from case 2) is sent as
   the override `new_deal.update(deal)` applies last, over the lead's own values.

A page reload clears all three; the cache is in memory. Restarting the server changes
nothing.

**Us:** *Reproduce.* The frontend is upstream's, byte for byte (both files diff clean
against the upstream checkout), and the port's `create_deal` prefers `organization` the
same way. The fix upstream is in the frontend: reset `documentsCache[doctype]['']` when
the dialog closes or the create succeeds, and null `organization` beside `contact`.
Candidate for the PR with 42, 43 and 44.

---

## 46. Clicking a currency cell in a list files the formatted amount as the filter

**Where:** `pages/Deals.vue:406`, `pages/Leads.vue:437`, `pages/Organizations.vue:116`
(`_rows[row] = getFormattedCurrency(row, deal)`: the list's row object carries the
display string, "$ 500,000.00"), `ViewControls.vue:1321-1337` (`applyFilter` takes
`item.name ?? item.label ?? item` from the clicked cell and writes it into
`filters[column.key]`), then `create_or_update_standard_view` persists the standard
view's filters per user. Found 6 Oct 2026 in the Deals pass (FINDINGS.md 77).

Click the Annual Revenue cell of a deal and the list is filtered on
`annual_revenue = "$ 500,000.00"`. Upstream's `frappe.get_list` hands that string to
MariaDB, which casts it to a number for the comparison, gets 0, and so the filter
matches nothing (or every deal with no revenue). No error, just an empty list that
does not say why, and the chip shows the amount the user clicked. The filter is saved
with the standard view, so it is back on the next visit until the user removes it.

**Us:** *Diverge.* The port's filter builder refused the string ("value must be a
decimal number", 417), and because the standard view replays it on every load the
Deals page would not open at all; a 417 was never an option. Reproducing MariaDB's
cast-to-zero would keep the empty list and hide the amount the user plainly clicked.
The port reads the number out of the formatted string instead, so the click filters on
the amount shown. A string with no number in it falls back to 0, MariaDB's answer. The
fix upstream is in the frontend: file the raw value, not the display string.

---

## 47. Home Actions lets a standard entry be turned into a separator, and Settings is gone

**Where:** `crm_dropdown_item.json` (`type` has `read_only_depends_on:
eval:doc.is_standard`), `components/Controls/Grid.vue` and `GridRowModal.vue` (neither
reads `read_only_depends_on`), `UserDropdown.vue:91-104` (a Separator row draws a
divider, nothing else), `composables/settings.js` (Settings is a modal opened from that
dropdown; no route reaches it). Found 6 Oct 2026 in the Settings pass (FINDINGS.md 78),
on the upstream demo first.

The six standard rows (Apps, Settings, Log out and so on) are meant to be fixed in
Type: the doctype says so. The Home Actions grid does not apply that rule, so the
Settings row's Type can be switched to Separator and saved. The dropdown then shows a
divider where Settings was, and because Settings opens only from that dropdown there is
no way back inside the app: the grid that would fix it lives in Settings.

Nor is there one in Desk, checked on the demo the same day. `/app/fcrm-settings` shows
the row, but Desk *does* honour the rules the CRM's grid skipped: Type is read-only
because the row is standard, and `is_standard` is `read_only: 1` by definition
(`crm_dropdown_item.json`), so neither can be changed back. Deleting the row is refused
by `FCRMSettings.validate` ("Cannot delete standard items settings",
`fcrm_settings.py:59-70`), and a re-added row could not be made standard. The Restore
Defaults button runs `after_install`, whose `add_standard_dropdown_items`
(`install.py:530-542`) returns early while any row exists; `bench migrate` runs
`sync_table` (`fcrm_settings.py:196-215`), which adds missing standard rows and removes
stale ones but never repairs a changed one. What is left is the database:

```
bench --site <site> console
>>> frappe.db.set_value("CRM Dropdown Item", {"parent": "FCRM Settings", "name1": "settings"},
...     {"type": "Route", "label": "Settings", "route": "#", "icon": "settings"})
>>> frappe.db.commit(); frappe.clear_cache()
```

or the same UPDATE on `tabCRM Dropdown Item` followed by `bench --site <site> clear-cache`.

**Us:** *Reproduce* in the frontend, which is upstream's. The port has no Desk, so
`seed_defaults --force` restores the standard rows by their Name, keeping custom ones.
To raise upstream (an issue or a PR, to be decided with 42 to 46): the grid should honour
`read_only_depends_on`, or the server should refuse a Type change on a standard row, and
`sync_table` could repair a standard row's Type the way it already repairs the set.

---

## 48. A wrong URL with more than one segment draws a blank page

**Where:** `frontend/src/router.js:133` upstream (`:164` here): the catch-all route is
`path: '/:invalidpath'`, which in Vue Router matches **one** segment. Found 7 Oct 2026 in
the Sign in and out pass (FINDINGS.md 83), on the hosted demo and locally alike.

`/crm/leaderssf` reaches the route and shows `InvalidPage.vue` ("Invalid page or not
permitted to access"); `/crm/leadsdss/CRM-LEAD-2026-00003` has a second segment, matches
no route at all, and the router view renders nothing: a blank page with the sidebar,
and no message. A mistyped list name in a record URL, the likeliest typo, is exactly the
case that gets nothing.

**Us:** *Diverge*, by the tester's decision on 7 Oct 2026: the one-line patch
`path: '/:invalidpath(.*)*'`, Vue Router's own catch-all form, so every unknown path
lands on the invalid page. Recorded in `frontend/JWT_PATCH.md` with the port's other
frontend patches. The same line is the fix upstream.

---

## 49. The Getting started panel opens empty for a finished user on a browser that has not seen them

**Where:** frappe-ui `1.0.0-beta.29`, the version CRM pins: `frappe/Onboarding/onboarding.js:146-147`
(`setUp`) and `:128-140` (`syncStatus`), with `frappe/Help/HelpModal.vue:28-39` and
`:161-164`. Found 13 Oct 2026 in the Getting started pass (BROWSER_TESTING.md B2), in an
incognito window as Administrator, whose stored status had every step done.

The sidebar is created only after the users list has loaded (`router.js:232` here, the
guard before the first screen), and when it is created it does two things at once:
`useOnboarding` sends the request for the user's stored status, because this browser
holds no copy (`onboarding.js:26-35`), and `onMounted` (`AppSidebar.vue:625-637`, the
same file upstream) calls `setUp`, which decides whether to open the panel from the
cached flag alone (`:147`): unknown means open. So the panel opens listing the steps
unticked, and the answer arrives afterwards, always, since the request was only just
sent. When the answer says every step is done, `syncStatus` flips the flag (`:140`), the
step list's `v-if` (`HelpModal.vue:29`) removes it, and the help centre (`:39`) does not
take its place, because that is switched on only when the panel is *opened* for a user
already known to be finished (`:161-164`). What remains is the frame with its minimise
and close buttons and nothing inside.

Once per browser profile: the flag is then cached (`useStorage`), the next load shows the
sidebar's Help entry instead, and a browser that already knows the user never sees it.
An incognito window sees it on every sign-in, which is how it was found. A user with
steps still open is unaffected, and so is a browser that cached the status while the
steps were being done.

**Us:** *Reproduce*. The code is frappe-ui's, installed from npm, and the port's sidebar
is upstream's file unchanged, so the port shows exactly what upstream shows. The fix is
to decide after the answer rather than before it: move `showHelpModal.value =
!isOnboardingStepsCompleted.value` out of `setUp` into the status resource's `onSuccess`
after `syncStatus()`, or have `syncStatus` close the panel when it flips the flag to
true. A frappe-ui pull request, not a CRM one.

---

## 50. Settings → Defaults is a blank page for a Sales Manager

**Where:** `frontend/src/components/Settings/Settings.vue:121-144` and
`frontend/src/components/Settings/DefaultsSettings.vue:43` upstream, against
`frappe/core/doctype/system_settings/system_settings.json` in the framework. Found
15 Oct 2026 while planning finding 64 (FINDINGS.md), and confirmed by the tester on the
hosted demo the same day: signed in as a Sales Manager, Settings → Defaults shows an empty
panel.

The Settings dialog shows its System Configuration group (General, Dashboard, Defaults,
Brand) when `isManager()` holds (`Settings.vue:144`), and `isManager` is true for a Sales
Manager as well as an admin (`stores/users.js:140-142`). The data behind Defaults is the
framework's `System Settings` single, whose role table has one row, System Manager. So the
tab is offered to a role that cannot read what it shows. The page asks for the document
(`createDocumentResource`, `DefaultsSettings.vue:154-157`), the server refuses, and the
document stays empty. The form has no `v-if` waiting for the document: its first input
binds `settings.doc.currency` (`:43`), reading a field of nothing throws while Vue renders
the component, and Vue drops the component. The Sales Manager gets an empty panel, with
the error in the browser console and no message on screen.

**Us:** *Reproduce*. Security is the standing exception to "diverge on what nothing can
observe", and the two fixes pull in opposite directions: giving Sales Manager read on
System Settings widens access to a document upstream keeps for System Manager, which the
port does not do on its own say. The port's `System Settings` (finding 64) keeps
upstream's role table, so a Sales Manager sees the same blank. The fix upstream is in the
frontend: give the Defaults item its own `condition: () => isAdmin()` (`users.js`
already has it), or give the form a `v-if="settings.doc"` and a "not permitted" message.

---

## 51. "Avg. deal value" shows an amount with a percent sign

**Where:** `crm/api/dashboard.py:414-423` (`get_average_deal_value`). Found 15 Oct 2026 in
the review of findings 63 and 64.

The card's `delta` is `current_month_avg - prev_month_avg`, the difference of two
averages in the dashboard currency, and the card also sends `"deltaSuffix": "%"`. The
dashboard prints the suffix after the delta, so an average that rose from 1,000 to 1,500
shows "+500%". Its two siblings, "Avg. won deal value" and "Avg. ongoing deal value",
compute the delta the same way and send no suffix, which is what this one meant to do.

**Us:** *Reproduce*. It is on screen, and the port shows upstream's dashboard. The fix
upstream is to drop `deltaSuffix` from that one return, or compute a percentage as the
count cards do.

---

## 52. An assignment condition with a quote in its value never fires

**Where:** `frontend/src/utils/index.js:599-700` (`convertToConditions`), used by the
Assignment Rules and SLA Policies screens. Found 15 Oct 2026 comparing Assignment Rules
with upstream (FINDINGS.md 80); read, not run.

The screen turns each condition into a Python expression the server evaluates with
`frappe.safe_eval`. A plain comparison escapes a `"` in its value, but "like", "not
like", "in", "not in" and "between" put the value between double quotes as typed:
`(title and "5" screen" in title)`. That is not valid Python. `AssignmentRule.safe_eval`
catches the error, shows "Auto assignment failed" and returns false
(`assignment_rule.py:200-209`, version-15), so the rule never assigns anyone, on every
save, with nothing on the rule itself to say why.

**Us:** *Diverge*, by construction. Decided 15 Oct 2026 (FINDINGS.md 80, decision 1): the
port evaluates the JSON form, not the expression, so the quote is just a character and
the rule works. Nothing can rely on a rule silently never firing. The fix upstream is to
escape the value in those five branches as the plain comparison already does.

---

## 53. Assignment Rules is offered to a Sales Manager who cannot save a rule

**Where:** `frontend/src/components/Settings/Settings.vue:186-205`, against the framework's
`assignment_rule.json` (version-15). Found 15 Oct 2026 with bug 52; the same shape as 50.

The Automation & Rules group (Assignment Rules, SLA Policies, Forms) shows when
`isManager()` holds, which a Sales Manager passes. `Assignment Rule` has one role row,
System Manager. A Sales Manager therefore sees the list, because
`get_assignment_rules_list` reads with `frappe.get_all`, which checks no permission, and
is refused on New, on an edit, on Duplicate and on delete.

**Us:** *Reproduce*, decided 15 Oct 2026 (FINDINGS.md 80, decision 5), as 50 was. The
fix upstream is to show the item to `isAdmin()` only, or to read the list with
`frappe.get_list`, so a Sales Manager gets a consistent "not permitted".

---

## 54. Date conditions and "between" in assignment and SLA conditions do not work

**Where:** `frontend/src/components/ConditionsFilter/CFCondition.vue:256-282` (what the
condition editor stores) against `frontend/src/utils/index.js:599-700`
(`convertToConditions`, the expression built from it), evaluated by `frappe.safe_eval`
against `doc.as_dict()` (`assignment_rule.py:200-209`, version-15). Found 15 Oct 2026 in
the discussion of FINDINGS.md 80; read, not run.

The editor stores a value as a number when it parses as one (`updateValue`, `:281`), so
number comparisons work. Two kinds do not:

* **"between" never works.** For a date field the editor stores the range as a list,
  `[start, end]` (`:279`). The converter's "between" branch only handles a string with a
  comma, so the list falls through to the generic branch and becomes
  `close_date between "2026-01-01,2026-01-31"`. `between` is not Python, so the
  expression does not compile; `safe_eval` raises, the rule reports "Auto assignment
  failed" and never matches, on every save.
* **A date compared with a date depends on how the document was loaded.** The editor
  stores the date as text, `"2026-10-20"`. A document loaded from the database holds a
  date field as a `datetime.date`, so `expected_closure_date == "2026-10-20"` is false
  and `>` or `<` raises. A document built from a client's request, an insert, holds the
  text and compares as text. So the same rule matches a deal when it is created and not
  when it is edited, with nothing to say why.

**Us:** *Diverge*, decided 15 Oct 2026 (FINDINGS.md 80, decision 1). The port's evaluator
reads the JSON form, compares a date field's value as a date with the condition's value
parsed as one, and takes "between" from the list as inclusive bounds. A condition that
upstream can never meet, or meets only by accident of loading, does what the screen
says. The fix upstream is a "between" branch for a list value, and comparing dates as
dates (or both as ISO text) in the converter.

---

## 55. Any signed-in user can list the assignment rules

**Where:** `crm/api/assignment_rule.py:4-23` (`get_assignment_rules_list`). Found 15 Oct
2026 comparing Assignment Rules with upstream (FINDINGS.md 80).

The endpoint is a bare `@frappe.whitelist()` and reads with `frappe.get_all`, which
applies no permission. `Assignment Rule` is System Manager's alone
(`assignment_rule.json`), yet any signed-in user, a Sales User included, can call it and
read every rule's name, description, priority and whether it has users. Low sensitivity,
but past the role table.

**Us:** *Reproduce for now*, decided 15 Oct 2026 (FINDINGS.md 80, decision 4): the port
answers as upstream does, and an upstream pull request will propose `frappe.get_list`
(or a System Manager check); the port follows whatever upstream decides. The security
rule would normally restrict it; this is a recorded exception, held open until that pull
request is answered.

---

## 56. SLA skips a holiday or non-working day without resetting the time of day

**Where:** `crm/fcrm/doctype/crm_service_level_agreement/
crm_service_level_agreement.py:234-260` (`calc_time`). Found 16 Oct 2026 while building
FINDINGS.md 91.

When the current day is a holiday or has no working-hours row, `calc_time` adds exactly
one day to the datetime and keeps its time. The separate branch for a working day with
no time left instead moves to the next day's midnight. A deadline counted from 15:00 on
Saturday consequently begins counting at 15:00 on Monday, not at Monday's working-hours
start; the same happens across a holiday. Which branch reaches the next workday changes
the deadline users see.

**Us:** *Reproduce.* The SLA engine carries the time through skipped days and tests the
Saturday and holiday cases explicitly. The upstream fix is to move to the next day's
midnight in the holiday/non-working branch, as the no-time-left branch already does.

---

## 57. An SLA with no working hours hangs every save it applies to

**Where:** `crm/fcrm/doctype/crm_service_level_agreement/
crm_service_level_agreement.py:224-261` (`calc_time`). Found 16 Oct 2026 in the review
of FINDINGS.md 91; read, not run.

`calc_time` loops `while time_needed:`, and only a day with working time left reduces
`time_needed`. If the SLA has no working-hours rows, every day is "not a workday" and the
loop adds a day forever; a holiday list covering every working day does the same. The
loop runs in `before_save` of every lead or deal the SLA applies to, so each such save
never returns: a worker is stuck, and the user sees a request that never finishes. The
SLA Policies screen asks for working hours, but nothing on the server requires them.

**Us:** *Diverge.* A hang is nothing anyone can rely on. The port's `calc_time` returns no
deadline when there are no working days, or after stepping over 3,660 days
(`crm_app/sla.py`, `MAX_DAYS_SKIPPED`), and `set_response_by` already treats that as "no
deadline". Tested in `tests/test_sla_timing.py`. The upstream fix is the same guard, or
refusing to save an SLA without working hours.

---

## 58. Clearing a task's Assigned To leaves the assignment open

**Where:** `crm/fcrm/doctype/crm_task/crm_task.py:33-39` (`validate`). Found 17 Oct
2026 while resolving FINDINGS.md 70; reproduced on the upstream demo.

`validate` returns immediately when `assigned_to` is empty. Clearing the field therefore
does not call `unassign_from_previous_user`: the previous user's ToDo stays open, the
assignee keeps the task in their list, and the task board's `_assign` cache still shows
their avatar even though `assigned_to` itself is empty.

**Us:** *Diverge,* by the owner's decision of 17 Oct 2026. `CRMTask.save` cancels the
previous field assignee when `assigned_to` is cleared, while leaving any separately
assigned users in place. The upstream fix is to make `validate` unassign the previous
user when `assigned_to` changes from a user to empty, before returning.

---

## Faithful behaviours we chose to keep (not bugs — decisions)

Recorded here so they are not later mistaken for defects:

- **SLA breaches are only detected on write.** A lead that breaches while untouched keeps
  showing `First Response Due` until something saves it. There is no scheduler entry
  (`crm/hooks.py` has none). Adding a sweep would make our lists disagree with upstream's.
- **403 and 404 are distinguishable**, so a user can tell whether a record they cannot see
  exists. Upstream behaves identically.
- **Polymorphic child tables have no referential integrity** — `parent` is a plain string.
  Frappe shares this, but Frappe also has an `on_trash` cascade we have not ported yet.
- **`FCRM Settings.access_key` is readable by any authenticated user** — the JSON declares
  it `Data`, unhidden, and the settings screen reads it back. Restricting it is a product
  decision that diverges from upstream and needs a UI change too.

> **`remove_assignments` was recorded here too, as a second #10.** Same defect, same
> endpoint, written twice — once from each phase's notes. The fuller account, with the
> framework line that makes the mechanism clear and the note that it was verified
> independently, is **`UPSTREAM_BUGS_PHASE_3-6.md` #10**. That is the entry to cite.

## The pattern worth remembering

Entries 10, 11, 12 and 14 are the same defect wearing four hats:

> **A doctype's endpoints are not its attack surface — the generic `/api/resource/` route
> is.**

Each phase gated the endpoints it wrote, and each time the generated route was left open
beside them. The agent's own tests passed every time, because they tested the endpoint
just written. Codex caught each one.

The standing fix — a test enumerating routable doctypes and asserting each is either
gated or deliberately world-readable — was proposed in `docs/internal/PROGRESS_PHASE_4.md`
and **has since been written**: `tests/test_route_surface.py`, joined by
`tests/test_credential_fields.py` for what is *inside* a doctype rather than who can reach
it. Both landed on `phase-7-prep`, before this phase started, which is why phase 7 adding
several new doctypes does not reopen the hole.

*(This paragraph said "not yet written" until phase 7 Step 0 — the tests it asked for were
already there. Left as a marker of how quickly a true sentence goes stale.)*
