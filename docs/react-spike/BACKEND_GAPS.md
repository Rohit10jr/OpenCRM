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
ERPNext, dashboard, notifications and exchange rate are all served.

Later in run 5 the check was made exhaustive: every dotted path the Vue client mentions,
diffed against every path this backend whitelists. That is what turned up the deal-contact
*writes* (§3) and `create_lead_from_call_log` (§7) — both of which the earlier, screen-by-
screen pass had missed, because nobody had reached those screens yet. The register below is
now the full list rather than the list of what happened to be built.

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

**React does:** `record/Attachments.tsx` renders a file picker and posts multipart to
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

**The write side is missing too**, found in run 5 by diffing every dotted path the Vue
client calls against every one this backend whitelists. All three of

* `crm.fcrm.doctype.crm_deal.crm_deal.add_contact`
* `crm.fcrm.doctype.crm_deal.crm_deal.remove_contact`
* `crm.fcrm.doctype.crm_deal.crm_deal.set_primary_contact`

are called by `Deal.vue` and served by nothing. So the whole feature is absent, not just its
read half — worth knowing before someone whitelists `get_deal_contacts` alone and expects a
working panel.

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

## 6. ~~Rich text everywhere — no TipTap yet~~ — CLOSED in run 5

`@tiptap/react` and `dompurify` are in, and `components/RichText.tsx` holds both halves:
`RichTextEditor` for composing and `RichTextView` for rendering. Comments and the email body
are HTML now, matching what the Vue client stores.

**`RichTextView` sanitises every render, and there is no unsanitised path in that file on
purpose.** The content in these fields is HTML authored by other users, some of them on the
Vue client; rendering it raw is stored XSS with a Vue-shaped delivery mechanism. If a future
change wants a raw render, that wanting is the bug.

**Still plain text:** the email signature (`get_user_signature` returns whatever the user
saved and nothing says which format), and notes.

---

## 7. Creating a lead from a call log — `crm_call_log.create_lead_from_call_log`

**Wanted by:** `CallLogDetailModal.vue` — an unknown number rings, and the modal offers to
make a lead out of it. It is the one action on that screen.

**Not whitelisted.** Nothing else covers it: the endpoint reads the call log and creates the
lead with the number already on it, which a plain `/api/resource/CRM Lead` insert would not.

**React does:** nothing. `pages/CallLogs.tsx` shows the call read-only. This one is *not*
wired-to-fail like the email send, because unlike a Send button it has no obvious place —
adding a button whose only outcome is a 404 to a screen that otherwise works is a worse
trade than leaving the screen honest.

**To unblock:** whitelist it. Then the detail dialog grows one button.

---

## 8. Rule conditions have nothing to attach to — `ConditionsFilter/`

**Wanted by:** `AssignmentRulesSection.vue` and `SlaAssignmentConditions.vue`. Those are the
only two callers; earlier notes here called this "nested AND/OR list filters", which was
wrong — `get_data` takes no `or_filters` and neither does upstream's, so the list views
never had this and were never meant to.

**Both destinations are dead ends, for different reasons:**

* **Assignment Rules.** `Assignment Rule` is a *framework* doctype and this port does not
  model it, so `get_assignment_rules_list` returns `[]` permanently and duplication raises
  (`api/assignment_rule.py:20`). There is no rule to put a condition on.
* **SLA.** `CRM Service Level Agreement` *is* modelled and has both `condition` and
  `condition_json` (`sla.py:74`) — but **nothing in the backend ever reads either.** The
  model comment says as much: *"phase 5 owns whether we evaluate it at all. Storing it is
  not executing it."* Grepping confirms the only other mention is the migration.

**React does:** nothing, deliberately. This is the one place the run-5 "wire it up and let
it fail visibly" policy does not apply, because there is no failure to see — the write
would succeed, the value would persist, and it would change nothing. A condition builder
here is a screen that looks like it configures behaviour and does not, which is worse than
its absence and much harder to notice.

**To unblock:** model `Assignment Rule`, or make the SLA engine evaluate `condition`. Until
one of those, this is not frontend work.

---

## 9. Twilio's browser softphone — `crm.integrations.twilio.api.generate_access_token`

**Not a backend gap. A frontend dependency this port has not taken on.** Recorded here
because the symptom looks identical from the UI: Twilio users get no call panel.

Exotel and Twilio are two different features wearing one name. Exotel places the call
server-side and rings the agent's real handset, so the browser only has to *display* the
call — `telephony/CallPanel.tsx` does that, driven by the `exotel_call` socket event that
`exotel/handler.py:209` publishes. Nothing to install.

Twilio is an in-browser softphone. The audio runs through WebRTC in the tab, which means
`@twilio/voice-sdk`, an access token from the endpoint above, a device registration
lifecycle, and mute / hold / hang-up controls that talk to the SDK rather than to us —
`TwilioCallUI.vue` is 523 lines and most of them are SDK plumbing. `twilio_call_status` is
published (`twilio/handler.py:444`) so the *status* half would work today; it is the audio
half that needs the dependency.

**What to do:** decide whether this deployment uses Twilio at all before spending on it. If
it does, it is a self-contained piece of work — add the SDK, add a second panel, reuse
nothing from the Exotel one because the state machines have nothing in common.

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
