# Phase 1 — Models

**Fan out by cluster. Needs phase 0. No two agents in the same cluster.**

Convert DocType JSON into Django models. Mostly mechanical — but three things below
are not, and skipping them costs a rewrite later.

Source: `crm/fcrm/doctype/<doctype>/<doctype>.json` (schema) and `.py` (logic).
**Read both.** The JSON gives fields; the `.py` gives validation and lifecycle rules.

---

## 1. The models that aren't in the DocType list

The 39 CRM doctypes are **not** the whole data model. The app depends on Frappe
*platform* doctypes that ship no JSON in this repo. Verified by reference count:

| Model | Refs | Why it's needed |
|---|---|---|
| `User` | 53 | PK is **email**. Owner, assignment, session, roles |
| `Contact` | 24 | Overridden upstream (`overrides/contact.py`). Multi email/phone child tables |
| `ToDo` | — | **Backs `_assign`.** Assignment is a ToDo record. Phase 2 queries it directly |
| `Communication` | 10+ | Email/call timeline on leads and deals |
| `Comment` | — | Comments; feeds the `_comments` cache |
| `Email Template` | — | Overridden upstream (`overrides/email_template.py`) |
| `File` | — | Attachments |
| `Email Account` | — | Outbound config (`api/settings.py`) |
| `Tag` | — | Feeds `_user_tags` |

**Build these first, before any CRM doctype.** Everything else foreign-keys into them.
Port only the fields the CRM actually uses — do not reimplement Frappe's full platform.

### Platform naming — RESOLVED against `frappe` `version-15`

Originally guessed, because the CRM repo never shows platform `autoname`. Now read from
source. **Three of these are controller `autoname()` methods, not JSON `autoname`** — a
seventh strategy beyond the six in `PHASE_0_FOUNDATION.md` §2:

| Model | Naming | Source |
|---|---|---|
| **`User`** | PK is the email, **lowercased and stripped**; `Administrator`/`Guest` are named from `first_name` | `core/doctype/user/user.py:150-156` |
| **`Contact`** | `first middle last` (company only as a *fallback*), + `-<first Dynamic Link>`, + `-N` on collision | `contacts/doctype/contact/contact.py:54-63`, `:463-473` |
| **`File`** | folder-aware `autoname()`; hash otherwise | `core/doctype/file/file.py:82` |
| `ToDo` | `hash` | `desk/doctype/todo/todo.json` |
| `Tag`, `Email Template` | `Prompt` | respective JSON |
| `Email Account` | `field:email_account_name` | `email/doctype/email_account/email_account.json` |
| `Comment`, `Communication` | no `autoname`, no method → framework default | — |

Two consequences worth stating, both of which were wrong before:

- **`User` must lowercase.** `owner`, `modified_by`, `ToDo.allocated_to`, `_assign`
  entries and every `@me` filter compare this value as a plain string. Skip the
  lowercasing and `John@Example.com` becomes a second, separate user whose records
  silently vanish from the first one's lists.
- **`Contact`'s `company_name` is a fallback, never a suffix.** Every CRM contact has
  `company_name` set (`crm_lead.py:219`), so treating it as a suffix corrupts
  essentially every contact name — and the frontend routes on that value.

`WhatsApp Message` comes from a separate app (`frappe_whatsapp`) — defer with phase 7.

---

## 2. Fieldtype → Django mapping

| Frappe | Django |
|---|---|
| `Data` | `CharField(max_length=140)` |
| `Small Text`, `Text`, `Long Text`, `Text Editor` | `TextField` |
| `Int` | `IntegerField` |
| `Float`, `Percent` | `FloatField` |
| `Currency` | `DecimalField(max_digits=18, decimal_places=6)` |
| `Check` | `BooleanField(default=False)` |
| `Select` | `CharField(choices=...)` — options are **newline-separated** in JSON |
| `Link` | `ForeignKey(<options doctype>, on_delete=PROTECT)` |
| `Dynamic Link` | Generic FK — target doctype named by a sibling field |
| `Date` / `Datetime` / `Time` | `DateField` / `DateTimeField` / `TimeField` |
| `Duration` | `IntegerField` — **seconds** |
| `Rating` | `FloatField` — 0..1 in Frappe v14+, not 0..5 |
| `Attach`, `Attach Image` | `CharField` holding a file URL, not `FileField` |
| `Table` | Child table — reverse FK, see §3 |
| `Table MultiSelect` | M2M through a child table |
| `Password` | Encrypted field |
| `Code`, `JSON` | `TextField` / `JSONField` |
| `Section Break`, `Column Break`, `Tab Break`, `HTML`, `Heading` | **SKIP — layout only, not data** |

Two traps:

- **Layout fieldtypes are not columns.** `crm_lead.json` has 61 "fields" but a large
  share are `Section Break` / `Column Break` / `Tab Break`. Filter them out or you will
  generate junk columns. They belong to phase 4 (form layout), not here.
- **`on_delete`**: Frappe blocks deletion of linked documents rather than cascading.
  `PROTECT` is the faithful default. Use `SET_NULL` only where the source explicitly
  permits orphans.

---

## 3. Child tables

10 of the 39 are child tables (`"istable": 1`): `crm_contacts`, `crm_dropdown_item`,
`crm_holiday`, `crm_product_sync_issue`, `crm_products`, `crm_rolling_response_time`,
`crm_service_day`, `crm_service_level_priority`, `crm_status_change_log`,
`crm_telephony_phone`.

Rules:
- FK to parent + `parenttype`, `parentfield`, `idx` (ordering) — Frappe's own columns
- **No standalone `/api/resource/` route.** They are reached through the parent
- Serialise nested inside the parent; the frontend expects them inline
- Writing a parent replaces its child rows wholesale (Frappe semantics) — not a merge

---

## 4. Lifecycle mapping

Read the source `.py` and map consistently across all agents:

| Frappe | Django |
|---|---|
| `validate()` | `Model.clean()` |
| `before_save()` | `pre_save` signal |
| `after_insert()` | `post_save` signal, `created=True` |
| `on_update()` | `post_save` signal |
| `on_trash()` | `pre_delete` signal |
| `frappe.throw(msg)` | `ValidationError(msg)` — **preserve message text**, it is user-facing |

---

## 5. Cluster assignment

One agent per cluster. `(C)` child, `(S)` singleton.

| # | Cluster | DocTypes | Notes |
|---|---|---|---|
| 1 | **Platform** | `User`, `Contact`, `ToDo`, `Communication`, `Comment`, `Email Template`, `File`, `Tag`, `Email Account` | **Must land first — blocks all others** |
| 2 | **Core sales** | `crm_lead` (545 LOC), `crm_deal` (472), `crm_organization`, `crm_task`, `fcrm_note`, `crm_contacts` (C) | Heaviest logic. Read controllers line by line |
| 3 | **Taxonomy** | `crm_lead_status`, `crm_deal_status`, `crm_lead_source`, `crm_industry`, `crm_lost_reason`, `crm_territory`, `crm_communication_status`, `crm_product`, `crm_products` (C) | Near-trivial lookups. `crm_territory` is a **tree** |
| 4 | **SLA** | `crm_service_level_agreement`, `crm_service_day` (C), `crm_service_level_priority` (C), `crm_holiday_list`, `crm_holiday` (C), `crm_rolling_response_time` (C), `crm_status_change_log` (C) | Business-hours arithmetic. Timezone-sensitive |
| 5 | **Telephony** | `crm_call_log` (295 LOC), `crm_telephony_agent`, `crm_telephony_phone` (C), `crm_twilio_settings` (S), `crm_exotel_settings` (S) | Models now, provider logic in phase 7 |
| 6 | **UI metadata + misc** | `crm_view_settings`, `crm_fields_layout`, `crm_form_script`, `crm_dashboard`, `crm_dropdown_item` (C), `crm_notification`, `crm_invitation`, `crm_sales_hierarchy`, `fcrm_settings` (S), `crm_global_settings` | Models only — behaviour is phase 4 |
| — | **Deferred** | `facebook_*`, `failed_lead_sync_log`, `lead_sync_source`, `crm_product_sync_issue` (C), `erpnext_crm_settings` (S) | Phase 7 |

Cluster 1 blocks 2–6. Clusters 2–6 run concurrently once it lands.

---

## 6. Singletons

`fcrm_settings`, `crm_twilio_settings`, `crm_exotel_settings`, `erpnext_crm_settings`
are `"issingle": 1` — exactly one record, stored key-value upstream. Use a normal table
with an enforced single row (`django-solo` or a `pk=1` constraint). `fcrm_settings`
carries `enable_sales_hierarchy`, which phase 2 reads.

---

## 7. Acceptance criteria

- [ ] Platform cluster lands before any CRM cluster
- [ ] Every model registers with the phase-0 registry and is routable
- [ ] Correct naming strategy per doctype (`PHASE_0_FOUNDATION.md` §2)
- [ ] No layout fieldtypes leaked into any model
- [ ] Child tables have no standalone route, serialise inline, replace-on-write
- [ ] `_assign` stays consistent with `ToDo` via signal, both directions
- [ ] Migrations apply cleanly from empty on Postgres
- [ ] Every `frappe.throw` in a ported controller has a `ValidationError` with identical text
- [ ] Cross-cluster FK targets confirmed to exist before referencing

> **PROVISIONAL:** the registry API in §4 of phase 0 and the `Meta.name_strategy`
> declaration are as-designed, not as-built. Re-check against the landed phase-0 code
> before starting.
