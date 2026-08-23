# Upstream bugs — found during phases 3 to 6

Defects found in **upstream** while porting. Not our bugs.

Companion to `UPSTREAM_BUGS_PHASE_0-2.md`, which holds bugs 1–9 from the earlier
phases. Numbering continues from there.

Two reasons this file exists:

1. **It records where our port deliberately differs from upstream.** Every entry marked
   *Diverge* is a place our behaviour will not match a real Frappe instance — which
   matters when diffing against a live install, and when deciding whether a difference is
   a port bug or a fix.
2. **It is the shortlist if you ever upstream anything.**

Source refs: `crm/` = `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm`
(branch `main`), `frappe/` = `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe`
(branch `version-15`).

| # | Bug | Our stance |
|---|---|---|
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
