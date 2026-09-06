# What the React client needs and this backend does not serve

**A running register, written during run 5.** Each entry names the screen that wants it, the
dotted path the Vue client calls, and what the React component does instead.

**The policy for run 5 is different from runs 1–4, deliberately.** Earlier runs refused to
build UI for an unserved endpoint, on the grounds that a Send button which 404s is worse
than no Send button. The owner reversed that for this run: **build the React frontend
anyway, wire it to the real path, let it fail visibly, and flag it here.** So every entry
below describes a component that exists, renders, and will show an error toast the moment
you use the part that needs the missing endpoint.

Components affected render a `<MissingEndpoint>` banner naming the path, so the gap is
visible before you click rather than after.

**Checked against `frappe_core.whitelist.all_methods()` on 2026-09-07**, not inferred from
the Vue source. The whitelist is larger than earlier runs assumed — telephony, WhatsApp,
ERPNext, dashboard, notifications and exchange rate are all served. Only the two below are
genuinely absent.

---

## 1. Sending email — `frappe.core.doctype.communication.email.make`

**Wanted by:** the record screen's email composer (`CommunicationArea.vue:216`).

**Not whitelisted.** The registry has `crm.api.settings.create_email_account` and
`crm.api.contact.search_emails` — account configuration and recipient lookup — and nothing
that sends a message.

**React does:** `EmailComposer` renders in full — recipients, subject, body, template
picker — and posts to the real path on Send. It will 404. The banner says so.

**To unblock:** whitelist a send endpoint. Everything else the composer needs already
exists: the record context, `search_emails` for recipients, `get_user_signature` for the
signature, and the activity feed it writes into.

---

## 2. Uploading a file — `upload_file`

**Wanted by:** the attachments tab, the email composer's attach button, brand/logo settings.

**Not whitelisted, and there is no route for it at all** — `config/urls.py` maps only
`/api/resource/*` and `/api/method/*`, so even an unlisted multipart handler has nowhere to
live. `crm.api.delete_attachment` and `crm.api.get_file_uploader_defaults` *are* served, so
listing and deleting work and only adding does not.

**React does:** `FileUploader` renders a drop zone and a file picker, and posts multipart to
`/api/method/upload_file`. It will 404.

**To unblock:** a multipart upload route plus a `File` doctype write path.

---

## 3. Deal contacts — `crm.fcrm.doctype.crm_deal.api.get_deal_contacts`

**Wanted by:** the Deal side panel's `contacts_section` (`Deal.vue:709`).

**Not whitelisted.** `conversion.py` has a `create_deal` that shares a name with a different
unserved endpoint; neither is this one. `crm.api.contact.get_linked_deals` exists but is the
inverse relation — deals for a contact, not contacts for a deal.

**React does:** the section renders its heading and a banner. Adding a contact posts to the
real path and fails.

**To unblock:** whitelist `get_deal_contacts`, or point the client at
`/api/resource/CRM Contacts` filtered by parent, if the child table is exposed.

---

## 4. Creating a deal through its controller — `crm.fcrm.doctype.crm_deal.crm_deal.create_deal`

**Wanted by:** `DealModal.vue:184`.

**Not whitelisted.** React posts to `/api/resource/CRM Deal` instead, which works. Whatever
that controller did beyond an insert is lost — nothing in the port depends on it today.

**Status: worked around, not blocking.**

---

## 5. Converting a lead to a deal — `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal`

**Wanted by:** the Convert button on a lead record (`ConvertToDealModal.vue:154`).

**Implemented but not exposed.** `backend/crm_app/conversion.py:263` *is* `convert_to_deal`
and looks complete — it carries the organization and contact across and marks the lead
converted. Nothing whitelists it, so the client cannot reach it.

**React does:** `ConvertToDealButton` opens a confirmation with the banner, and posts to the
real path. It will 404.

**To unblock:** one `@whitelist` decorator, most likely. This is the cheapest gap on the
list and the one with the most behind it already.

---

## 6. Rich text everywhere — no TipTap yet

Not a backend gap, but it belongs beside them because it shapes the same screens.

The Vue app composes emails, comments and notes in a TipTap editor and stores **HTML**.
React sends plain text from a textarea in all three places, and **renders comments as text
rather than HTML** — a comment written by the Vue client is HTML authored by another user,
so unescaping it would be stored XSS with a Vue-shaped delivery mechanism.

**To close:** `@tiptap/react` plus a sanitiser on the render side. Contained, and it wants
doing before either client is used against the other's data in anger.

---

## Things earlier runs assumed were missing and are not

Recorded because two runs planned around the wrong assumption:

| Endpoint | Serves |
|---|---|
| `crm.integrations.exotel.handler.make_a_call`, `twilio.api.*` | Telephony — click-to-call, call status, recordings |
| `crm.api.whatsapp.*` | WhatsApp messages, templates, reactions |
| `crm.fcrm.doctype.erpnext_crm_settings.*` | ERPNext sync, quotations, product sync |
| `crm.api.exchange_rate.get_exchange_rate` | Currency conversion |
| `crm.api.dashboard.get_dashboard`, `get_chart` | The dashboard |
| `crm.api.notifications.*` | Notifications and mark-as-read |
| `crm.api.onboarding.*` | The onboarding wizard |
| `crm.api.assignment_rule.*` | Assignment rules |
| `crm.api.contact.create_new`, `set_as_primary`, `search_emails` | Contact management |
| `crm.api.get_user_signature`, `get_translations`, `auth.oauth_providers` | Signatures, i18n, SSO |
