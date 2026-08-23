# Upstream bugs — Frappe CRM / Frappe framework

Defects found in **upstream** while porting. Not our bugs.

This file is gitignored — it is a local working note, not part of the port.

Two reasons it exists:

1. **It records where our port deliberately differs from upstream.** Every entry marked
   *Diverge* is a place our behaviour will not match a real Frappe instance — which
   matters when diffing against the Docker oracle, and when deciding whether a
   difference is a port bug or a fix.
2. **It is the shortlist if you ever upstream anything.**

Source refs are `crm/` = `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm`
(branch `main`), `frappe/` = `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe`
(branch `version-15` — the pairing CRM's own CI uses, `.github/workflows/builds.yml:43`).

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

---

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

## 10. `remove_assignments` exposes `ignore_permissions` over HTTP

`crm/api/doc.py:589-604`. The endpoint is `@frappe.whitelist()` with
`ignore_permissions: bool = False`, and passes it straight to
`frappe.desk.form.assign_to.set_status(..., ignore_permissions=ignore_permissions)`.

Any authenticated caller who knows a document name can therefore send
`ignore_permissions=True` and cancel assignment ToDo rows on a lead or deal they cannot
write — which revokes another user's access to that record.

**Diverged: the flag is accepted and ignored.** No client sends it (the frontend calls
the endpoint without it), so honest behaviour is unchanged; the escalation is closed.
Port: `backend/crm_app/api/doc.py:remove_assignments`.

## 11. `crm_products` money fields are computed client-side only

`crm/fcrm/doctype/crm_products/crm_products.py:112-195` builds a **JavaScript** form
script; `amount`, `net_amount`, `discount_amount`, `total` and `net_total` are all
computed in the browser and posted up. Nothing server-side recomputes or validates them,
so a hand-rolled request can set a deal's `total` to anything.

**Diverged: computed on save.** For an honest client the values are identical, so nothing
user-visible changes. Port: `backend/crm_app/models/taxonomy.py:recalculate_parent_totals`.

Note the `net_total` rule is subtle and was ported exactly: `net_total = sum(net_amount)
or total`, **unless** a discount was applied, in which case a zero sum stands. Dropping
the second branch makes a 100%-discounted deal report its full gross value.

## 12. `crm.api.settings.create_email_account` has no permission check

`crm/api/settings.py:5-53` is `@frappe.whitelist()` with no `frappe.only_for`. Upstream
relies on the Email Account doctype's own role permissions, which this port does not
model — so ported verbatim it would let any authenticated user create a
credential-bearing mail account and mark it `default_outgoing`, redirecting the system's
outbound mail.

**Diverged: restricted to System Manager / Sales Manager.**
Port: `backend/crm_app/api/settings.py`.

## 13. Metadata doctypes have no row-level protection

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
