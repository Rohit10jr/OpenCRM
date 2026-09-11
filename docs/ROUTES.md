# Route inventory — every backend and frontend path

**Generated** by `backend/scripts/generate_route_inventory.py` from the whitelist
registry, the doctype registry and `frontend/src/router.js`. Re-run it after adding an
endpoint, a doctype or a page; do not edit the tables by hand. The blank **Tested**
column is the one thing meant to be filled in — it is the checklist for the API
walkthrough.

## How to read this

| | |
|---|---|
| Backend base URL | `http://localhost:8000` (`runserver 8000`, ASGI via daphne) |
| Frontend base URL | `http://localhost:8080/crm` (`yarn dev`; the router's history base is `/crm`) |
| Auth header | `Authorization: Bearer <access token>` — access tokens live 5 minutes, refresh tokens 7 days |
| `/api/method/*` envelope | `{"message": ...}` |
| `/api/resource/*` envelope | `{"data": ...}` |
| Error body | Frappe-shaped (`exc_type`, `exception`, `_server_messages`) — see `frappe_core/exceptions.py` |
| Unknown or withheld doctype | 404, deliberately indistinguishable |
| Forbidden row | 403, distinguishable from 404 — matches upstream |

The dev server proxies `/api`, `/assets`, `/files` and `/private` to the backend, so the
browser only ever talks to port 8080. Manual testing with curl or a REST client goes
straight to port 8000.

---

## 1. Method endpoints — `/api/method/<dotted.path>`

One generic view (`frappe_core/method_views.py`) dispatches every row below by looking
the dotted path up in the whitelist registry. Parameters merge the query string and the
JSON body; each value is JSON-decoded if it parses, so `filters=[["a","=","b"]]` and a
native array are the same thing. Surplus parameters are dropped.

Columns: **Verbs** the view accepts; **Access** is `guest` for the few endpoints that
work without a token, `auth` otherwise, and `+request` marks the webhook handlers that
receive the raw request for signature checks; **Frontend uses** is how many times the
literal path appears under `frontend/src`.

| # | Dotted path | Verbs | Access | Parameters | Frontend uses | Source | Tested |
|---|---|---|---|---|---|---|---|
| 1 | `crm.api.accept_invitation` | GET/POST | guest | `key: 'str' = '', **extra` | 1 | `crm_app/api/auth_pages.py:311` | ✅ 11 Sep — 01_auth (2 red, see FINDINGS.md) |
| 2 | `crm.api.activities.get_activities` | GET/POST | auth | `name: 'str'` | 1 | `crm_app/api/activities.py:453` | ✅ 10 Sep — step 3, 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md) |
| 3 | `crm.api.assignment_rule.duplicate_assignment_rule` | GET/POST | auth | `docname: 'str', new_name: 'str'` | 1 | `crm_app/api/assignment_rule.py:26` | ✅ 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 4 | `crm.api.assignment_rule.get_assignment_rules_list` | GET/POST | auth | — | 1 | `crm_app/api/assignment_rule.py:20` | ✅ 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 5 | `crm.api.auth.oauth_providers` | GET/POST | guest | — | 0 | `crm_app/api/auth.py:17` | ✅ 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 6 | `crm.api.comment.add_comment` | GET/POST | auth | `reference_doctype: 'str', reference_name: 'str', content: 'str', attachments: 'str \| list \| None' = None` | 1 | `crm_app/api/comment.py:117` | ✅ 10 Sep — step 3, 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md) |
| 7 | `crm.api.contact.create_new` | GET/POST | auth | `contact: 'str', field: 'str', value: 'str'` | 1 | `crm_app/api/contact.py:72` | ✅ 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md) |
| 8 | `crm.api.contact.get_linked_deals` | GET/POST | auth | `contact: 'str'` | 2 | `crm_app/api/contact.py:41` | ✅ 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md) |
| 9 | `crm.api.contact.search_emails` | GET/POST | auth | `txt: 'str'` | 1 | `crm_app/api/contact.py:127` | ✅ 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md) |
| 10 | `crm.api.contact.set_as_primary` | GET/POST | auth | `contact: 'str', field: 'str', value: 'str'` | 1 | `crm_app/api/contact.py:101` | ✅ 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md) |
| 11 | `crm.api.dashboard.get_chart` | GET/POST | auth | `name: 'str', type: 'str', from_date: 'str \| None' = None, to_date: 'str \| None' = None, user: 'str \| None' = None` | 1 | `crm_app/api/dashboard.py:511` | ✅ 11 Sep — 10_dashboard (3 red, see FINDINGS.md), 11 Sep — 11_permissions_matrix |
| 12 | `crm.api.dashboard.get_dashboard` | GET/POST | auth | `from_date: 'str \| None' = None, to_date: 'str \| None' = None, user: 'str \| None' = None` | 1 | `crm_app/api/dashboard.py:484` | ✅ 11 Sep — 10_dashboard (3 red, see FINDINGS.md) |
| 13 | `crm.api.dashboard.reset_to_default` | POST | auth | — | 1 | `crm_app/api/dashboard.py:466` | ✅ 11 Sep — 10_dashboard (3 red, see FINDINGS.md) |
| 14 | `crm.api.delete_attachment` | DELETE/POST | auth | `doctype: 'str', docname: 'str', file_url: 'str'` | 1 | `crm_app/api/misc.py:125` | ✅ 11 Sep — 09_users_and_invitations |
| 15 | `crm.api.doc.delete_bulk_docs` | GET/POST | auth | `doctype: 'str', items: 'str \| list', delete_linked: 'bool' = False` | 1 | `crm_app/api/doc.py:534` | ✅ 11 Sep — 11_permissions_matrix, 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 16 | `crm.api.doc.get_assigned_users` | GET/POST | auth | `doctype: 'str', name: 'str', default_assigned_to: 'str \| None' = None` | 1 | `crm_app/api/doc.py:247` | ✅ 11 Sep — 03_leads (1 red, see FINDINGS.md) |
| 17 | `crm.api.doc.get_data` | GET/POST | auth | `doctype: 'str', filters: 'Any' = None, order_by: 'Any' = None, page_length: 'int' = 20, page_length_count: 'int' = 20, column_field: 'str \| None' = None, title_field: 'str \| None' = None, columns: 'Any' = None, rows: 'Any' = None, kanban_columns: 'Any' = None, kanban_fields: 'Any' = None, view: 'Any' = None, default_filters: 'Any' = None` | 1 | `frappe_core/api/doc.py:211` | ✅ 10 Sep — list view, @me, as Sales User, 11 Sep — 03_leads (1 red, see FINDINGS.md), 11 Sep — 04_deals (8 red, see FINDINGS.md), 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md), 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md), 11 Sep — 11_permissions_matrix |
| 18 | `crm.api.doc.get_fields` | GET/POST | auth | `doctype: 'str', allow_all_fieldtypes: 'bool' = False` | 2 | `crm_app/api/doc.py:296` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 19 | `crm.api.doc.get_filterable_fields` | GET/POST | auth | `doctype: 'str'` | 2 | `crm_app/api/doc.py:95` | ✅ 11 Sep — 03_leads (1 red, see FINDINGS.md), 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 20 | `crm.api.doc.get_group_by_fields` | GET/POST | auth | `doctype: 'str'` | 1 | `crm_app/api/doc.py:101` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 21 | `crm.api.doc.get_linked_docs_of_document` | GET/POST | auth | `doctype: 'str', docname: 'str'` | 1 | `crm_app/api/doc.py:349` | ✅ 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md) |
| 22 | `crm.api.doc.get_quick_filters` | GET/POST | auth | `doctype: 'str', cached: 'bool' = True` | 1 | `crm_app/api/doc.py:145` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 23 | `crm.api.doc.remove_assignments` | GET/POST | auth | `doctype: 'str', name: 'str', assignees: 'str \| list', ignore_permissions: 'bool' = False` | 2 | `crm_app/api/doc.py:262` | ✅ 11 Sep — 03_leads (1 red, see FINDINGS.md), 11 Sep — 11_permissions_matrix |
| 24 | `crm.api.doc.remove_linked_doc_reference` | GET/POST | auth | `items: 'str \| list', remove_contact: 'bool' = False, delete: 'bool' = False` | 1 | `crm_app/api/doc.py:430` | ✅ 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md) |
| 25 | `crm.api.doc.sort_options` | GET/POST | auth | `doctype: 'str'` | 1 | `crm_app/api/doc.py:73` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 26 | `crm.api.doc.update_quick_filters` | GET/POST | auth | `quick_filters: 'str \| list', old_filters: 'str \| list', doctype: 'str'` | 1 | `crm_app/api/doc.py:201` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 27 | `crm.api.exchange_rate.get_exchange_rate` | GET/POST | auth | `from_currency: 'str', to_currency: 'str', date: 'str \| None' = None` | 0 | `crm_app/api/exchange_rate.py:27` | ✅ 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 28 | `crm.api.get_file_uploader_defaults` | GET/POST | auth | `doctype: 'str'` | 1 | `crm_app/api/misc.py:158` | ✅ 11 Sep — 09_users_and_invitations |
| 29 | `crm.api.get_translations` | GET/POST | guest | — | 0 | `crm_app/api/misc.py:30` | ✅ 11 Sep — 09_users_and_invitations |
| 30 | `crm.api.get_user_signature` | GET/POST | auth | — | 1 | `crm_app/api/misc.py:41` | ✅ 11 Sep — 09_users_and_invitations |
| 31 | `crm.api.invite_by_email` | GET/POST | auth | `emails: 'str', role: 'str'` | 1 | `crm_app/api/misc.py:74` | ✅ 11 Sep — 09_users_and_invitations |
| 32 | `crm.api.notifications.get_notifications` | GET/POST | auth | — | 1 | `crm_app/api/notifications.py:33` | ✅ 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md) |
| 33 | `crm.api.notifications.mark_as_read` | GET/POST | auth | `doc: 'str \| None' = None` | 1 | `crm_app/api/notifications.py:97` | ✅ 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md) |
| 34 | `crm.api.onboarding.get_first_deal` | GET/POST | auth | — | 1 | `crm_app/api/onboarding.py:22` | ✅ 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 35 | `crm.api.onboarding.get_first_lead` | GET/POST | auth | — | 1 | `crm_app/api/onboarding.py:9` | ✅ 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 36 | `crm.api.session.get_organizations` | GET/POST | auth | — | 1 | `crm_app/api/session.py:158` | ✅ 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md) |
| 37 | `crm.api.session.get_user_info` | GET/POST | auth | `users: 'str \| list'` | 1 | `crm_app/api/session.py:138` | ✅ 11 Sep — 09_users_and_invitations |
| 38 | `crm.api.session.get_users` | GET/POST | auth | `include_all: 'bool' = False` | 2 | `crm_app/api/session.py:62` | ✅ 11 Sep — 09_users_and_invitations |
| 39 | `crm.api.settings.create_email_account` | GET/POST | auth | `data: 'str \| dict'` | 1 | `crm_app/api/settings.py:68` |  |
| 40 | `crm.api.user.add_existing_users` | GET/POST | auth | `users: 'str \| list', role: 'str' = 'Sales User'` | 1 | `crm_app/api/user.py:110` | ✅ 11 Sep — 09_users_and_invitations |
| 41 | `crm.api.user.change_password` | GET/POST | auth | `old_password: 'str', new_password: 'str'` | 1 | `crm_app/api/user.py:54` | ✅ 11 Sep — 09_users_and_invitations |
| 42 | `crm.api.user.remove_crm_roles_from_user` | GET/POST | auth | `user: 'str'` | 1 | `crm_app/api/user.py:182` | ✅ 11 Sep — 09_users_and_invitations |
| 43 | `crm.api.user.update_user_role` | GET/POST | auth | `user: 'str', new_role: 'str'` | 1 | `crm_app/api/user.py:128` | ✅ 11 Sep — 09_users_and_invitations, 11 Sep — 11_permissions_matrix |
| 44 | `crm.api.views.get_views` | GET/POST | auth | `doctype: 'str'` | 1 | `crm_app/api/views.py:11` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 45 | `crm.api.whatsapp.create_whatsapp_message` | GET/POST | auth | `reference_doctype: 'str', reference_name: 'str', message: 'str' = '', to: 'str' = '', attach: 'str' = '', reply_to: 'str' = '', content_type: 'str' = 'text'` | 1 | `crm_app/integrations/whatsapp/api.py:189` |  |
| 46 | `crm.api.whatsapp.get_whatsapp_messages` | GET/POST | auth | `reference_doctype: 'str', reference_name: 'str'` | 1 | `crm_app/integrations/whatsapp/api.py:117` |  |
| 47 | `crm.api.whatsapp.is_whatsapp_enabled` | GET/POST | auth | — | 1 | `crm_app/integrations/whatsapp/api.py:99` |  |
| 48 | `crm.api.whatsapp.is_whatsapp_installed` | GET/POST | auth | — | 1 | `crm_app/integrations/whatsapp/api.py:104` |  |
| 49 | `crm.api.whatsapp.react_on_whatsapp_message` | GET/POST | auth | `emoji: 'str', reply_to_name: 'str'` | 1 | `crm_app/integrations/whatsapp/api.py:254` |  |
| 50 | `crm.api.whatsapp.send_whatsapp_template` | GET/POST | auth | `reference_doctype: 'str', reference_name: 'str', template: 'str', to: 'str'` | 1 | `crm_app/integrations/whatsapp/api.py:233` |  |
| 51 | `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout` | GET/POST | auth | `doctype: 'str', type: 'str', parent_doctype: 'str \| None' = None` | 14 | `crm_app/api/fields_layout.py:112` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 52 | `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections` | GET/POST | auth | `doctype: 'str'` | 8 | `crm_app/api/fields_layout.py:213` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 53 | `crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.save_fields_layout` | POST | auth | `doctype: 'str', type: 'str', layout: 'str'` | 4 | `crm_app/api/fields_layout.py:243` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 54 | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create` | POST | auth | `view: 'str \| dict'` | 1 | `crm_app/api/view_settings.py:150` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 55 | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.create_or_update_standard_view` | POST | auth | `view: 'str \| dict'` | 1 | `crm_app/api/view_settings.py:273` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 56 | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.delete` | POST/DELETE | auth | `name: 'str \| int'` | 1 | `crm_app/api/view_settings.py:190` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 57 | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.fetch_and_update_kanban_columns` | POST | auth | `name: 'str \| int'` | 1 | `crm_app/api/view_settings.py:318` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 58 | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.pin` | POST | auth | `name: 'str \| int', value: 'bool \| int'` | 1 | `crm_app/api/view_settings.py:232` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 59 | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.public` | POST | auth | `name: 'str \| int', value: 'bool \| int'` | 1 | `crm_app/api/view_settings.py:204` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 60 | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.set_as_default` | POST | auth | `name: 'str \| int \| None' = None, type: 'str \| None' = None, doctype: 'str \| None' = None` | 1 | `crm_app/api/view_settings.py:246` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 61 | `crm.fcrm.doctype.crm_view_settings.crm_view_settings.update` | POST/PUT | auth | `view: 'str \| dict'` | 2 | `crm_app/api/view_settings.py:170` | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 62 | `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.dismiss_sync_issue` | GET/POST | auth | `issue_name: 'str'` | 0 | `crm_app/integrations/erpnext/api.py:255` |  |
| 63 | `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_customer_link` | GET/POST | auth | `crm_deal: 'str'` | 0 | `crm_app/integrations/erpnext/api.py:90` |  |
| 64 | `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_external_companies` | GET/POST | auth | — | 0 | `crm_app/integrations/erpnext/api.py:76` |  |
| 65 | `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_open_sync_issues` | GET/POST | auth | — | 0 | `crm_app/integrations/erpnext/api.py:233` |  |
| 66 | `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_product_sync_status` | GET/POST | auth | — | 1 | `crm_app/integrations/erpnext/api.py:278` |  |
| 67 | `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_quotation_url` | GET/POST | auth | `crm_deal: 'str', organization: 'str \| None' = None` | 0 | `crm_app/integrations/erpnext/api.py:117` |  |
| 68 | `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.is_erpnext_installed` | GET/POST | auth | — | 0 | `crm_app/integrations/erpnext/api.py:65` |  |
| 69 | `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.prefill_quotation_items` | GET/POST | auth | `crm_deal: 'str'` | 0 | `crm_app/integrations/erpnext/api.py:186` |  |
| 70 | `crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.run_product_sync` | GET/POST | auth | — | 0 | `crm_app/integrations/erpnext/api.py:309` |  |
| 71 | `crm.integrations.api.add_note_to_call_log` | GET/POST | auth | `call_sid: 'str', note: 'dict'` | 3 | `crm_app/integrations/api.py:116` | ✅ 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md) |
| 72 | `crm.integrations.api.add_task_to_call_log` | GET/POST | auth | `call_sid: 'str', task: 'dict'` | 2 | `crm_app/integrations/api.py:140` | ✅ 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md) |
| 73 | `crm.integrations.api.get_contact_by_phone_number` | GET/POST | auth | `phone_number: 'str'` | 2 | `crm_app/integrations/api.py:177` | ✅ 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md) |
| 74 | `crm.integrations.api.get_contact_lead_or_deal_from_number` | GET/POST | auth | `number: 'str'` | 0 | `crm_app/integrations/api.py:183` | ✅ 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md) |
| 75 | `crm.integrations.api.is_call_integration_enabled` | GET/POST | auth | — | 1 | `crm_app/integrations/api.py:63` |  |
| 76 | `crm.integrations.api.set_default_calling_medium` | GET/POST | auth | `medium: 'str'` | 1 | `crm_app/integrations/api.py:79` |  |
| 77 | `crm.integrations.exotel.handler.handle_request` | GET/POST | guest | `**kwargs` | 0 | `crm_app/integrations/exotel/handler.py:187` |  |
| 78 | `crm.integrations.exotel.handler.is_integration_enabled` | GET/POST | auth | — | 0 | `crm_app/integrations/exotel/handler.py:52` |  |
| 79 | `crm.integrations.exotel.handler.make_a_call` | GET/POST | auth | `to_number: 'str', from_number: 'str \| None' = None, caller_id: 'str \| None' = None` | 1 | `crm_app/integrations/exotel/handler.py:226` |  |
| 80 | `crm.integrations.twilio.api.generate_access_token` | GET/POST | auth | — | 2 | `crm_app/integrations/twilio/handler.py:263` |  |
| 81 | `crm.integrations.twilio.api.is_enabled` | GET/POST | auth | — | 0 | `crm_app/integrations/twilio/handler.py:32` |  |
| 82 | `crm.integrations.twilio.api.twilio_incoming_call_handler` | GET/POST | guest +request | `_twilio_url: 'str' = '', _twilio_signature: 'str \| None' = None, **kwargs` | 0 | `crm_app/integrations/twilio/handler.py:339` |  |
| 83 | `crm.integrations.twilio.api.update_call_status_info` | GET/POST | guest +request | `_twilio_url: 'str' = '', _twilio_signature: 'str \| None' = None, **kwargs` | 0 | `crm_app/integrations/twilio/handler.py:423` |  |
| 84 | `crm.integrations.twilio.api.update_recording_info` | GET/POST | guest +request | `_twilio_url: 'str' = '', _twilio_signature: 'str \| None' = None, **kwargs` | 0 | `crm_app/integrations/twilio/handler.py:402` |  |
| 85 | `crm.integrations.twilio.api.voice` | GET/POST | guest +request | `_twilio_url: 'str' = '', _twilio_signature: 'str \| None' = None, **kwargs` | 0 | `crm_app/integrations/twilio/handler.py:303` |  |
| 86 | `frappe.auth.get_logged_user` | GET/POST | auth | — | 0 | `frappe_core/api/auth.py:166` | ✅ 10 Sep — step 1, 11 Sep — 01_auth (2 red, see FINDINGS.md) |
| 87 | `frappe.client.delete` | DELETE/POST | auth | `doctype: 'str', name: 'str'` | 15 | `crm_app/api/client.py:202` | ✅ 11 Sep — 11_permissions_matrix |
| 88 | `frappe.client.get` | GET/POST | auth | `doctype: 'str', name: 'str \| None' = None, filters=None, parent=None` | 3 | `crm_app/api/client.py:53` | ✅ 11 Sep — 11_permissions_matrix, 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 89 | `frappe.client.get_doc_permissions` | GET/POST | auth | `doctype: 'str', docname: 'str'` | 1 | `crm_app/api/client.py:241` | ✅ 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md), 11 Sep — 11_permissions_matrix |
| 90 | `frappe.client.get_list` | GET/POST | auth | `doctype: 'str', fields=None, filters=None, or_filters=None, order_by: 'str \| None' = None, limit_start: 'int' = 0, limit_page_length: 'int' = 20, parent=None, **extra` | 1 | `crm_app/api/client.py:71` | ✅ 11 Sep — 11_permissions_matrix, 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 91 | `frappe.client.get_single_value` | GET/POST | auth | `doctype: 'str', field: 'str'` | 2 | `crm_app/api/client.py:96` | ✅ 11 Sep — 12_settings_singletons |
| 92 | `frappe.client.insert` | POST | auth | `doc=None, **extra` | 9 | `crm_app/api/client.py:169` | ✅ 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 93 | `frappe.client.rename_doc` | POST | auth | `doctype: 'str', old_name: 'str', new_name: 'str', merge: 'bool' = False` | 5 | `crm_app/api/client.py:211` | ✅ 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md), 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 94 | `frappe.client.set_value` | POST/PUT | auth | `doctype: 'str', name: 'str', fieldname, value=None` | 13 | `crm_app/api/client.py:143` | ✅ 10 Sep — step 3, 11 Sep — 11_permissions_matrix, 11 Sep — 12_settings_singletons |
| 95 | `frappe.core.doctype.user.user.reset_password` | POST | guest | `user: 'str' = '', **extra` | 1 | `crm_app/api/auth_pages.py:45` | ✅ 11 Sep — 01_auth (2 red, see FINDINGS.md) |
| 96 | `frappe.core.doctype.user.user.update_password` | POST | guest | `new_password: 'str' = '', key: 'str' = '', old_password: 'str' = '', logout_all_sessions: 'int' = 0, **extra` | 1 | `crm_app/api/auth_pages.py:99` | ✅ 11 Sep — 01_auth (2 red, see FINDINGS.md), 11 Sep — 99_lockout |
| 97 | `frappe.desk.form.assign_to.add` | POST | auth | `doctype: 'str', name: 'str', assign_to=None, description: 'str' = '', **extra` | 2 | `crm_app/api/client.py:263` | ✅ 10 Sep — step 3, 11 Sep — 03_leads (1 red, see FINDINGS.md), 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md), 11 Sep — 11_permissions_matrix |
| 98 | `frappe.desk.like.toggle_like` | POST | auth | `doctype: 'str', name: 'str', add: 'str' = 'No'` | 1 | `crm_app/api/client.py:286` | ✅ 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md) |
| 99 | `frappe.desk.search.search_link` | GET/POST | auth | `doctype: 'str', txt: 'str' = '', query: 'str \| None' = None, filters=None, page_length: 'int' = 10, reference_doctype: 'str \| None' = None, ignore_user_permissions: 'bool' = False, **extra` | 1 | `crm_app/api/client.py:312` | ✅ 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md), 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 100 | `login` | POST | guest | `usr: 'str' = '', pwd: 'str' = '', **extra` | 3 | `frappe_core/api/auth.py:39` | ✅ 10 Sep — steps 1, 4, 11 Sep — 01_auth (2 red, see FINDINGS.md), 11 Sep — 02_resource_grammar (6 red, see FINDINGS.md), 11 Sep — 03_leads (1 red, see FINDINGS.md), 11 Sep — 04_deals (8 red, see FINDINGS.md), 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md), 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md), 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md), 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md), 11 Sep — 09_users_and_invitations, 11 Sep — 10_dashboard (3 red, see FINDINGS.md), 11 Sep — 11_permissions_matrix, 11 Sep — 12_settings_singletons, 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md), 11 Sep — 14_unserved_paths, 11 Sep — 99_lockout |
| 101 | `logout` | POST/GET | auth | `refresh: 'str' = '', **extra` | 2 | `frappe_core/api/auth.py:110` | ✅ 10 Sep — step 1, 11 Sep — 01_auth (2 red, see FINDINGS.md) |
| 102 | `token/refresh` | POST | guest | `refresh: 'str' = '', **extra` | 1 | `frappe_core/api/auth.py:129` | ✅ 10 Sep — step 1, rotation and blacklist confirmed, 11 Sep — 01_auth (2 red, see FINDINGS.md) |

---

## 2. Resource endpoints — `/api/resource/<DocType>[/<name>]`

Two generic views (`frappe_core/views.py`) serve every routable doctype:

| Verb | Route | Does |
|---|---|---|
| GET | `/api/resource/<DocType>` | List. Params: `filters`, `or_filters`, `fields`, `order_by`, `limit_start`, `limit_page_length`, `group_by`, `parent` — all JSON strings |
| POST | `/api/resource/<DocType>` | Create. Body is the document; child tables inline |
| GET | `/api/resource/<DocType>/<name>` | Read one. `<name>` may contain slashes |
| PUT | `/api/resource/<DocType>/<name>` | Update. Child tables are replaced wholesale |
| DELETE | `/api/resource/<DocType>/<name>` | Delete → `{"data": null}` |

There is no PATCH. Doctype names contain spaces — URL-encode them (`CRM%20Lead`) or let
the client do it.

Columns: **Naming** is the primary-key strategy, which tells you what `name` to expect
on create; **Protection** is the route-surface classification from
`tests/test_route_surface.py` — `ruled` means a permission hook is registered, the other
two states are recorded decisions; **Declared fields** are the field-visibility
declarations (`S` sensitive: never on the wire, `E` encrypted at rest, `R` restricted to
managers, `RO` read-only); **Frontend refs** counts `'<DocType>'` literals under
`frontend/src`; **Rows** is the count in the local database when this file was generated.

### 2a. Routable doctypes

| # | DocType | Model | Route | Single | Naming | Protection | Declared fields | Frontend refs | Rows | Tested |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CRM Call Log | `crm_app.CRMCallLog` | `/api/resource/CRM Call Log` |  | `FieldValue('id')` | awaiting review — call history references leads and deals; recording URLs are on the row |  | 13 | 5 | ✅ 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md) |
| 2 | CRM Communication Status | `crm_app.CRMCommunicationStatus` | `/api/resource/CRM Communication Status` |  | `FieldValue('status')` | reviewed-open — reference data - communication status vocabulary |  | 2 | 0 |  |
| 3 | CRM Dashboard | `crm_app.CRMDashboard` | `/api/resource/CRM Dashboard` |  | `FieldValue('title')` | reviewed-open — chart definitions, not data - `get_dashboard` filters the numbers |  | 2 | 1 | ✅ 11 Sep — 10_dashboard (3 red, see FINDINGS.md) |
| 4 | CRM Deal | `crm_app.CRMDeal` | `/api/resource/CRM Deal` |  | `NamingSeries('CRM-DEAL-.YYYY.-')` | ruled: list rule, object rule |  | 58 | 11 | ✅ 10 Sep — list and read only; 403 as Sales User, 11 Sep — 04_deals (8 red, see FINDINGS.md), 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md), 11 Sep — 11_permissions_matrix |
| 5 | CRM Deal Status | `crm_app.CRMDealStatus` | `/api/resource/CRM Deal Status` |  | `FieldValue('deal_status')` | reviewed-open — reference data - status vocabulary, rendered in every list view |  | 5 | 7 | ✅ 11 Sep — 04_deals (8 red, see FINDINGS.md) |
| 6 | CRM Exotel Settings | `crm_app.CRMExotelSettings` | `/api/resource/CRM Exotel Settings` | single | default | ruled: list rule, object rule | S: `api_token`; E: `api_token`; R: `webhook_verify_token`, `api_key`, `account_sid` | 2 | 0 | ✅ 11 Sep — 12_settings_singletons |
| 7 | CRM Fields Layout | `crm_app.CRMFieldsLayout` | `/api/resource/CRM Fields Layout` |  | `Format('{dt}-{type}')` | ruled: list rule, object rule |  | 0 | 4 | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 8 | CRM Form Script | `crm_app.CRMFormScript` | `/api/resource/CRM Form Script` |  | `Prompt()` | ruled: list rule, object rule |  | 1 | 0 | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 9 | CRM Global Settings | `crm_app.CRMGlobalSettings` | `/api/resource/CRM Global Settings` |  | `Hash(10)` | reviewed-open — no secrets: holds only `dt`, `type` and a JSON blob. Upstream grants all three roles full CRUD (`crm_global_settings.json`), deliberately. Reproduced. |  | 0 | 0 | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 10 | CRM Holiday List | `crm_app.CRMHolidayList` | `/api/resource/CRM Holiday List` |  | `FieldValue('holiday_list_name')` | reviewed-open — reference data - business calendar, read by the SLA engine |  | 1 | 0 |  |
| 11 | CRM Industry | `crm_app.CRMIndustry` | `/api/resource/CRM Industry` |  | `FieldValue('industry')` | reviewed-open — reference data - industry vocabulary, shown on organisation forms |  | 0 | 0 | ✅ 11 Sep — 02_resource_grammar (6 red, see FINDINGS.md), 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md) |
| 12 | CRM Invitation | `crm_app.CRMInvitation` | `/api/resource/CRM Invitation` |  | `Hash(10)` | ruled: list rule, object rule | S: `key` | 1 | 0 | ✅ 11 Sep — 09_users_and_invitations |
| 13 | CRM Lead | `crm_app.CRMLead` | `/api/resource/CRM Lead` |  | `NamingSeries('CRM-LEAD-.YYYY.-')` | ruled: list rule, object rule |  | 70 | 15 | ✅ 10 Sep — CRUD, naming series, status default, owner rule, 11 Sep — 03_leads (1 red, see FINDINGS.md), 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md), 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md), 11 Sep — 09_users_and_invitations, 11 Sep — 11_permissions_matrix, 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 14 | CRM Lead Source | `crm_app.CRMLeadSource` | `/api/resource/CRM Lead Source` |  | `FieldValue('source_name')` | reviewed-open — reference data - source vocabulary, shown on every lead form |  | 0 | 0 | ✅ 11 Sep — 03_leads (1 red, see FINDINGS.md) |
| 15 | CRM Lead Status | `crm_app.CRMLeadStatus` | `/api/resource/CRM Lead Status` |  | `FieldValue('lead_status')` | reviewed-open — reference data - status vocabulary, rendered in every list view |  | 4 | 6 |  |
| 16 | CRM Lost Reason | `crm_app.CRMLostReason` | `/api/resource/CRM Lost Reason` |  | `FieldValue('lost_reason')` | reviewed-open — reference data - reasons offered when a deal is marked lost |  | 2 | 0 | ✅ 11 Sep — 03_leads (1 red, see FINDINGS.md), 11 Sep — 04_deals (8 red, see FINDINGS.md) |
| 17 | CRM Notification | `crm_app.CRMNotification` | `/api/resource/CRM Notification` |  | `Hash(10)` | ruled: list rule, object rule |  | 1 | 0 | ✅ 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md) |
| 18 | CRM Organization | `crm_app.CRMOrganization` | `/api/resource/CRM Organization` |  | `FieldValue('organization_name')` | awaiting review — same as Contact - is org data meant to be company-wide? |  | 31 | 7 | ✅ 10 Sep — full CRUD, filters, paging, slash name, 11 Sep — 02_resource_grammar (6 red, see FINDINGS.md), 11 Sep — 04_deals (8 red, see FINDINGS.md), 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md), 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 19 | CRM Product | `crm_app.CRMProduct` | `/api/resource/CRM Product` |  | `FieldValue('product_code')` | awaiting review — catalogue data; writes change prices used in deal totals |  | 1 | 0 | ✅ 11 Sep — 04_deals (8 red, see FINDINGS.md) |
| 20 | CRM Sales Hierarchy | `crm_app.CRMSalesHierarchy` | `/api/resource/CRM Sales Hierarchy` |  | `Hash(10)` | ruled: list rule, object rule |  | 1 | 0 | ✅ 10 Sep — create refused for Sales User (403), 11 Sep — 11_permissions_matrix |
| 21 | CRM Service Level Agreement | `crm_app.CRMServiceLevelAgreement` | `/api/resource/CRM Service Level Agreement` |  | `FieldValue('sla_name')` | awaiting review — SLA definitions; writes change response deadlines |  | 6 | 0 |  |
| 22 | CRM Task | `crm_app.CRMTask` | `/api/resource/CRM Task` |  | `AutoIncrement()` | reviewed-open — collaborative - upstream grants all roles full CRUD and `pages/Tasks.vue` is a company-wide board. Deferring to the parent would empty it |  | 20 | 16 | ✅ 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md) |
| 23 | CRM Telephony Agent | `crm_app.CRMTelephonyAgent` | `/api/resource/CRM Telephony Agent` |  | `FieldValue('user')` | awaiting review — holds colleagues' phone numbers |  | 2 | 0 |  |
| 24 | CRM Territory | `crm_app.CRMTerritory` | `/api/resource/CRM Territory` |  | `FieldValue('territory_name')` | reviewed-open — reference data - territory tree, shown on lead and deal forms |  | 0 | 0 | ✅ 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md) |
| 25 | CRM Twilio Settings | `crm_app.CRMTwilioSettings` | `/api/resource/CRM Twilio Settings` | single | default | ruled: list rule, object rule | S: `api_secret`, `auth_token`; E: `api_secret`, `auth_token`; R: `api_key`, `twiml_sid` | 2 | 0 | ✅ 11 Sep — 12_settings_singletons |
| 26 | CRM View Settings | `crm_app.CRMViewSettings` | `/api/resource/CRM View Settings` |  | `AutoIncrement()` | ruled: list rule, object rule |  | 0 | 2 | ✅ 11 Sep — 07_views_and_metadata (2 red, see FINDINGS.md) |
| 27 | Comment | `frappe_platform.Comment` | `/api/resource/Comment` |  | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | 6 | 71 | ✅ 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md) |
| 28 | Communication | `frappe_platform.Communication` | `/api/resource/Communication` |  | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | 0 | 0 | ✅ 11 Sep — 08_activities_comments_notifications (3 red, see FINDINGS.md) |
| 29 | Contact | `frappe_platform.Contact` | `/api/resource/Contact` |  | default | awaiting review — shared across leads and deals; upstream relies on role permissions |  | 43 | 5 | ✅ 11 Sep — 04_deals (8 red, see FINDINGS.md), 11 Sep — 05_contacts_organizations (12 red, see FINDINGS.md), 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md) |
| 30 | ERPNext CRM Settings | `crm_app.ERPNextCRMSettings` | `/api/resource/ERPNext CRM Settings` | single | default | ruled: list rule, object rule | S: `api_secret`; E: `api_secret`; R: `api_key`, `erpnext_site_url` | 3 | 0 | ✅ 11 Sep — 12_settings_singletons |
| 31 | Email Account | `frappe_platform.EmailAccount` | `/api/resource/Email Account` |  | `FieldValue('email_account_name')` | ruled: list rule, object rule | S: `password`, `api_secret`; E: `password`, `api_secret`; R: `smtp_server`, `smtp_port`, `email_server`, `incoming_port`, `login_id`, `domain`, `api_key`, `frappe_mail_site`, `signature`, `no_smtp_authentication`, `awaiting_password` | 5 | 0 |  |
| 32 | Email Template | `frappe_platform.EmailTemplate` | `/api/resource/Email Template` |  | `Prompt()` | awaiting review — writes change the wording of mail the system sends on your behalf |  | 4 | 0 | ✅ 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 33 | FCRM Note | `crm_app.FCRMNote` | `/api/resource/FCRM Note` |  | `Hash(10)` | reviewed-open — same as CRM Task - `pages/Notes.vue` is company-wide, and a note can legitimately have no parent at all |  | 13 | 5 | ✅ 11 Sep — 06_tasks_notes_calls (6 red, see FINDINGS.md), 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 34 | FCRM Settings | `crm_app.FCRMSettings` | `/api/resource/FCRM Settings` | single | default | ruled: list rule, object rule | R: `access_key` | 10 | 1 | ✅ 11 Sep — 04_deals (8 red, see FINDINGS.md), 11 Sep — 11_permissions_matrix, 11 Sep — 12_settings_singletons |
| 35 | Facebook Lead Form | `crm_app.FacebookLeadForm` | `/api/resource/Facebook Lead Form` |  | `FieldValue('id')` | ruled: list rule, object rule |  | 5 | 0 |  |
| 36 | Facebook Page | `crm_app.FacebookPage` | `/api/resource/Facebook Page` |  | `FieldValue('id')` | ruled: list rule, object rule | S: `access_token`; E: `access_token` | 2 | 0 |  |
| 37 | Failed Lead Sync Log | `crm_app.FailedLeadSyncLog` | `/api/resource/Failed Lead Sync Log` |  | `Hash(10)` | ruled: list rule, object rule |  | 2 | 0 |  |
| 38 | File | `frappe_platform.File` | `/api/resource/File` |  | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | 3 | 0 | ✅ 11 Sep — 09_users_and_invitations, 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 39 | Lead Sync Source | `crm_app.LeadSyncSource` | `/api/resource/Lead Sync Source` |  | default | ruled: list rule, object rule | S: `access_token`; E: `access_token` | 3 | 0 | ✅ 11 Sep — 12_settings_singletons |
| 40 | Tag | `frappe_platform.Tag` | `/api/resource/Tag` |  | `Prompt()` | awaiting review — low risk, but writes are unconstrained |  | 0 | 0 | ✅ 11 Sep — 13_bulk_and_misc (1 red, see FINDINGS.md) |
| 41 | User | `frappe_platform.User` | `/api/resource/User` |  | default | ruled: list rule, object rule | S: `groups`, `user_permissions`, `is_superuser`, `is_staff`, `reset_password_key`, `last_reset_password_key_generated_on`; RO: `enabled`, `user_type` | 36 | 10 | ✅ 10 Sep — read own row, hidden fields absent, hidden filter 400, 11 Sep — 09_users_and_invitations |
| 42 | WhatsApp Message | `crm_app.WhatsAppMessage` | `/api/resource/WhatsApp Message` |  | `Hash(10)` | ruled: list rule, object rule, destination re-check |  | 1 | 0 |  |

### 2b. Registered but not routable

Child tables are reached inline through their parent. Withheld doctypes exist, have
rules and internal callers, and simply publish no route — `specs/UNROUTED_DOCTYPES.md`
has the reasoning.

| # | DocType | Model | Route | Single | Naming | Protection | Declared fields | Frontend refs | Rows | Tested |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | CRM Contacts | `crm_app.CRMContacts` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 0 | 0 |  |
| 2 | CRM Dropdown Item | `crm_app.CRMDropdownItem` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 1 | 0 |  |
| 3 | CRM Holiday | `crm_app.CRMHoliday` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 0 | 0 |  |
| 4 | CRM Product Sync Issue | `crm_app.CRMProductSyncIssue` | child table — inline in parent, no route |  | `AutoIncrement()` | n/a |  | 0 | 0 |  |
| 5 | CRM Products | `crm_app.CRMProducts` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 0 | 0 | ✅ 11 Sep — 02_resource_grammar (6 red, see FINDINGS.md) |
| 6 | CRM Rolling Response Time | `crm_app.CRMRollingResponseTime` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 0 | 0 |  |
| 7 | CRM Service Day | `crm_app.CRMServiceDay` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 0 | 0 |  |
| 8 | CRM Service Level Priority | `crm_app.CRMServiceLevelPriority` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 0 | 0 |  |
| 9 | CRM Status Change Log | `crm_app.CRMStatusChangeLog` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 0 | 98 |  |
| 10 | CRM Telephony Phone | `crm_app.CRMTelephonyPhone` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 0 | 0 |  |
| 11 | Contact Email | `frappe_platform.ContactEmail` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 3 | 0 |  |
| 12 | Contact Phone | `frappe_platform.ContactPhone` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 2 | 0 |  |
| 13 | Dynamic Link | `frappe_platform.DynamicLink` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 9 | 0 |  |
| 14 | Facebook Lead Form Question | `crm_app.FacebookLeadFormQuestion` | child table — inline in parent, no route |  | `Hash(10)` | n/a |  | 1 | 0 |  |
| 15 | ToDo | `frappe_platform.ToDo` | **withheld** (`routable=False`) |  | `Hash(10)` | withheld — `specs/UNROUTED_DOCTYPES.md` |  | 0 | 68 | ✅ 10 Sep — route absent (404), 11 Sep — 11_permissions_matrix |
| 16 | Version | `frappe_core.Version` | **withheld** (`routable=False`) |  | `Hash(10)` | withheld — `specs/UNROUTED_DOCTYPES.md` |  | 0 | 22 |  |

---

## 3. WebSocket — `ws://localhost:8000/ws/realtime?token=<access token>`

One endpoint, `crm_app/consumers.py:RealtimeConsumer`, routed in `config/routing.py`.
The token rides in the query string because a browser cannot set headers on a handshake.
An invalid or missing token closes the socket with code **4001**. `ENABLE_REALTIME=0`
removes the route entirely.

The vite dev server does **not** proxy `/ws`, so in development the browser needs
`VITE_WS_ORIGIN=ws://localhost:8000` in `frontend/.env.local`, or the client silently
retries with backoff and the app runs without live updates.

| Client → server event | Meaning |
|---|---|
| `doc_subscribe` | `{"event": "doc_subscribe", "args": ["CRM Lead", "<name>"]}` — join the document's room. Permission-checked with the same list + object rules the HTTP detail route uses; replies `doc_subscribed` |
| `doc_unsubscribe` | same args — leave the room; replies `doc_unsubscribed` |
| `ping` | keepalive; replies `pong` |

---

## 4. Other backend routes

| Route | What |
|---|---|
| `/admin/` | Django admin. Present in `config/urls.py`; not part of the Frappe contract |

---

## 5. Frontend pages — `http://localhost:8080/crm<path>`

From `frontend/src/router.js`. Every path below is relative to the `/crm` history base.
The navigation guard sends a logged-out visitor to **Login** with `?redirect=<path>`, sends
a logged-in visitor without a CRM role to **Not Permitted**, and resolves **Home** to the
user's default saved view (falling back to **Leads**).

`:viewType` is one of `list`, `kanban`, `group_by`, or a saved-view name; `?view=<name>`
selects a saved view. Lead and Deal pages append `#activity` (or the last-used tab) when
opened without a hash. Mobile variants are chosen at load when the viewport is under
768px.

| # | Path | Alias | Route name | Component | Access | Tested |
|---|---|---|---|---|---|---|
| 1 | `/crm/` |  | Home | — (redirects in the guard) | login required |  |
| 2 | `/crm/login` |  | Login | auth/Login.vue | public |  |
| 3 | `/crm/forgot-password` |  | Forgot Password | auth/ForgotPassword.vue | public |  |
| 4 | `/crm/update-password` |  | Update Password | auth/UpdatePassword.vue | public |  |
| 5 | `/crm/accept-invitation` |  | Accept Invitation | auth/AcceptInvitation.vue | public |  |
| 6 | `/crm/notifications` |  | Notifications | MobileNotification.vue | login required |  |
| 7 | `/crm/dashboard` |  | Dashboard | Dashboard.vue | login required |  |
| 8 | `/crm/leads/view/:viewType?` | `/crm/leads` | Leads | Leads.vue | login required |  |
| 9 | `/crm/leads/:leadId` |  | Lead | Lead.vue / MobileLead.vue | login required |  |
| 10 | `/crm/deals/view/:viewType?` | `/crm/deals` | Deals | Deals.vue | login required |  |
| 11 | `/crm/deals/:dealId` |  | Deal | Deal.vue / MobileDeal.vue | login required |  |
| 12 | `/crm/notes/view/:viewType?` | `/crm/notes` | Notes | Notes.vue | login required |  |
| 13 | `/crm/tasks/view/:viewType?` | `/crm/tasks` | Tasks | Tasks.vue | login required |  |
| 14 | `/crm/contacts/view/:viewType?` | `/crm/contacts` | Contacts | Contacts.vue | login required |  |
| 15 | `/crm/contacts/:contactId` |  | Contact | Contact.vue / MobileContact.vue | login required |  |
| 16 | `/crm/organizations/view/:viewType?` | `/crm/organizations` | Organizations | Organizations.vue | login required |  |
| 17 | `/crm/organizations/:organizationId` |  | Organization | Organization.vue / MobileOrganization.vue | login required |  |
| 18 | `/crm/call-logs/view/:viewType?` | `/crm/call-logs` | Call Logs | CallLogs.vue | login required |  |
| 19 | `/crm/data-import` |  | DataImportList | DataImport.vue | login required |  |
| 20 | `/crm/data-import/doctype/:doctype` |  | NewDataImport | DataImport.vue | login required |  |
| 21 | `/crm/data-import/:importName` |  | DataImport | DataImport.vue | login required |  |
| 22 | `/crm/welcome` |  | Welcome | Welcome.vue | login required |  |
| 23 | `/crm/onboarding` |  | Onboarding | PersonaForm.vue | login required |  |
| 24 | `/crm/:invalidpath` |  | Invalid Page | InvalidPage.vue | login required |  |
| 25 | `/crm/not-permitted` |  | Not Permitted | NotPermitted.vue | login required |  |

---

## 6. Regenerating

```
cd backend
.venv/Scripts/python.exe scripts/generate_route_inventory.py
```

Whatever is written in a **Tested** cell is carried forward on regeneration, keyed on the
dotted path, doctype or page path in the row. A row that disappears takes its note with it.
