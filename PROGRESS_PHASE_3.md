# Phase 3 — PASS   [branch: phase-3-endpoints]
Started: 2026-08-16   Finished: 2026-08-16   Commit: `762b0ac`
(`a3bcc8a` was recorded here originally; the commit was amended and that SHA is orphaned.)

**Built:** The endpoint layer — 58 dotted paths registered, up from 5. All of
`PHASE_3_ENDPOINTS.md` groups A–D, plus the `frappe.client.*` / `frappe.desk.*`
built-ins the frontend needs, plus the three carried-over items (C4 product totals,
C5 `Dynamic Link`, C9 batched bulk permission checks). Modules live in `crm_app/api/`,
one per source module.

**Tests:** **952 passing**, 31 skipped (all pre-existing), 0 failing. 139 new.
No test was skipped or weakened in this phase.

| Criterion (`PHASE_3_ENDPOINTS.md` §4) | Covered by |
|---|---|
| Every dotted path resolves | `test_every_frontend_dotted_path_resolves` — reads the **frontend source** and fails on any path nothing serves; plus 42 spec-listed paths asserted individually |
| Parameter names and defaults match source | `test_parameter_names_and_defaults_match_source`, 30 signatures |
| Responses wrapped in `{"message": ...}` | `test_method_response_is_message_enveloped` |
| JSON-string **and** native params | `test_json_string_params_are_accepted`, `test_native_list_params_are_accepted` |
| Permission checks; nothing bypasses phase 2 | `test_no_endpoint_bypasses_the_permission_layer` (source-level), plus per-endpoint denial tests |
| `frappe.throw` messages verbatim | 6 tests asserting exact strings |
| Bulk ops transactional + per-item checked | `test_delete_bulk_docs_refuses_the_whole_batch_if_one_item_is_denied` |
| No `Model.objects` for list reads | source-level grep test, with a justified allowlist that is **itself** tested |
| Named documents check `check_object_permission` | 6 denial tests |

Two structural tests do the heavy lifting: one checks the contract against the **client**
rather than my own list, and one greps for the single mistake that silently undoes
phase 2. Both would have caught real regressions; the allowlist for the second is itself
tested, so it cannot become a place to park failures.

---

## Review — tier 1 (Codex, PowerShell 7)

Ran clean: no spawn-failure markers, real `file:line` citations, returned in ~8 minutes.
Six findings. **Five fixed, one disputed.**

**High — `remove_assignments` honoured a caller-supplied `ignore_permissions=True`.**
Real, and the worst of the six. Upstream whitelists the same parameter and passes it
straight to `set_status` (`crm/api/doc.py:597-604`), so **upstream has the identical
hole**: any authenticated caller who knows a document name could cancel assignments on a
lead they cannot write — which revokes another user's access. The flag is now accepted
for signature fidelity and deliberately ignored. No honest client sends it, so this is
invisible to the frontend and closes a privilege escalation. Logged in `UPSTREAM_BUGS.md`.

**High — `get_assigned_users` leaked assignee emails for invisible records.** Real.
Upstream does not check either. Now guarded by `_require_readable`.

**Medium — `get_linked_docs_of_document` never checked read on the source document.**
Real; criterion 9 requires it. Same guard.

**Low — parameter defaults drifted from source** on four endpoints (`search_emails`,
`get_chart`, `get_file_uploader_defaults`, `get_views`). Real and exactly the kind of
thing criterion 2 exists for. Fixed, and the signature test now covers all four.

**High — `frappe.client.insert` does not set `lead_owner`/`deal_owner`. DISPUTED.**
Codex cites the `AS_BUILT.md` §4 invariant. I checked the source before deciding:

* `crm_lead.py` has **no** server-side default — the only writes to `lead_owner` are the
  share/assign hooks at `:88-98`, which fire only `if self.lead_owner`.
* The **client** is what defaults it:
  `frontend/src/components/Modals/LeadModal.vue:189-190` sets
  `lead.doc.lead_owner = getUser().name` before saving.

So upstream has exactly this behaviour, and a generic-endpoint create without the field
produces a record its author cannot see — upstream too. I reproduced it rather than
diverging, and pinned it down with two tests, one of which fails loudly if someone later
adds a default without justifying it. The invariant in `AS_BUILT.md` is still right as
*guidance for endpoints that create leads*; `frappe.client.insert` is a generic
passthrough, and inventing a default there would be inventing semantics.

**Medium — `duplicate_assignment_rule` throws a message with no upstream counterpart.
DISPUTED, partially.** Correct that the string is mine. But `Assignment Rule` is a
**framework** doctype this port does not model, so there is nothing to duplicate. The
options were: raise, or return a fabricated object the UI would then show as a rule that
does not exist. Raising is the honest one. Kept, and called out here.

### One defect the review did not find, and my own test did

**Every API-created lead and deal was rejected with "status is required."** Phase 1
ported upstream's `validate_status`, which defaults `status` on create — and
`AS_BUILT.md` §5 says so. But DRF validates *before* the model runs, so the serializer
demanded a field the model was about to fill in. Direct ORM creates worked and every
API create failed, which is why no existing test caught it. Models now declare
`AUTO_DEFAULTED_FIELDS` and the serializer honours it.

This is the phase's reminder that a green suite means only what the tests actually
exercise: nothing before this phase created a lead through an endpoint.

---

## Decisions made without you

1. **`frappe.client.*` and `frappe.desk.*` built-ins were added to the phase.** Not in
   `PHASE_3_ENDPOINTS.md` §2, but `PORT_PLAN.md` §3 names them as required by the
   frontend, and criterion 1 says every dotted path must resolve. 11 endpoints in
   `crm_app/api/client.py`. Widening scope needs justifying; leaving the app unable to
   delete, rename or set a value would have been worse.
2. **C4's totals are computed server-side, which upstream does not do.** Upstream
   computes them in a **client-side form script** (`crm_products.py:112-195` builds the
   JS). For an honest client the numbers are identical, so nothing user-visible changes —
   but money fields taken on trust from the wire is not a behaviour worth reproducing.
   The `net_total` fallback rule is ported exactly, including the branch that stops a
   100%-discounted deal reporting its gross value.
3. **`get_linked_deals` permission-filters; upstream does not.** Upstream uses
   `frappe.get_cached_doc`, so a contact shared across the sales hierarchy would expose
   deal values the caller cannot otherwise see. Diverged.
4. **`search_link` ignores `ignore_user_permissions`.** Honouring it would let a Link
   autocomplete enumerate rows the caller cannot see.
5. **`create_email_account` is restricted to System/Sales Manager.** Upstream has no
   explicit guard — it leans on the Email Account doctype's role permissions, which this
   port does not model. Without a check, any authenticated user could create a
   credential-bearing account and set it as default outgoing, i.e. redirect the system's
   mail. Found by my own allowlist test, not by review.
6. **Dashboard charts read through `base_queryset`.** Upstream's raw `frappe.qb` does
   not, so our numbers are *narrower* for a restricted user. Safer direction.
7. **`in_standard_filter` lives in one table**, not per-model like `get_hidden_fields`,
   because phase 4 owns field metadata (C7) and will fold it in. Verified against every
   DocType JSON by test, so its location does not affect correctness.
8. **Select detection is patched locally in `crm_app/api/doc.py`.** `_frappe_fieldtype`
   keys on the Django internal type, so a Select is indistinguishable from Data — that is
   C7. Without a local fix `get_quick_filters` returned a raw newline string and the
   frontend rendered its first character. **Phase 4 should delete `_resolved_fieldtype`
   when it fixes C7 properly.**

## Deviations from spec

- Added the `frappe.client.*` built-ins (decision 1).
- C4 computed server-side (decision 2), `get_linked_deals` filtered (3),
  `search_link` (4), `create_email_account` guarded (5), dashboards filtered (6).
- `remove_assignments` ignores `ignore_permissions` (review, High).

## Not ported — named, not hidden

> **Four of the five below were ported afterwards** — see *Fixed* and *Also fixed in the
> review pass*, which supersede this list. Only the six dashboard charts remain. Left
> unedited because the reasoning is the record of what the unattended run believed at the
> time, and two of those beliefs turned out to be wrong.

- **Six dashboard charts**: `sales_trend`, `forecasted_revenue`, `funnel_conversion`,
  `average_time_to_close_a_lead`, `average_time_to_close_a_deal`,
  `deal_status_change_counts`. All time-series or duration arithmetic. They resolve to
  `None`, which is what upstream does for an unknown chart name, so the dashboard renders
  with those tiles empty rather than failing. Listed in `dashboard.UNPORTED_CHARTS`.
- **Field-change entries in `get_activities`.** Upstream builds them from the framework's
  `Version` doctype — a per-save JSON diff. `Version` is not modelled, and recording it
  means diffing every document on every save: a framework-wide write cost, well outside
  this phase. The timeline has creation, status changes (from the ported
  `CRM Status Change Log`), comments, communications, calls, notes, tasks and
  attachments. Attachment-log entries are absent for the same reason.
- **`oauth_providers`** returns `[]` and **`get_assignment_rules_list`** returns `[]` —
  both depend on framework doctypes (`Social Login Key`, `Assignment Rule`) outside the
  ported surface. Empty is what upstream returns when none are configured.
- **`create_email_account` does not validate credentials.** Upstream opens a live IMAP
  connection first (`get_incoming_server()`). No mail layer exists here; faking a
  successful validation would be worse than saving unvalidated.
- **`change_password` has no rate limiting or lockout.** Upstream uses
  `LoginAttemptTracker` and `@rate_limit(5/5min)`, both framework infrastructure. This is
  a real weakening of brute-force resistance on a password-change endpoint and wants
  addressing before production.

## Concerns

> Of these six, four are resolved below and two carry into phase 4
> (`_resolved_fieldtype`, `search_link`'s missing title field). The last one —
> `_period_before` — was right to flag and wrong about the cause: it is not upstream's
> behaviour faithfully reproduced, it is an upstream arithmetic bug. See B1.

- **`change_password` brute-force protection is the one I would fix first.** It is a
  genuine security regression against upstream, not a cosmetic gap.
- **`get_activities` is materially thinner than upstream's** until `Version` exists.
  Users will see a timeline without "Alice changed Status from New to Qualified".
  Whether that matters is a product call.
- **`_resolved_fieldtype` is a plaster over C7** and will be wrong for any fieldtype
  distinction beyond Select-vs-Data. Phase 4 should remove it.
- **`search_link` has no title field.** It returns names with empty descriptions because
  no model declares `SEARCH_FIELD`. Link autocompletes will look bare until phase 4's
  metadata layer supplies a title field per doctype.
- **The dashboard's `_period_before` baseline differs subtly from upstream** for
  month-length ranges: upstream uses `date_diff` in days, which I reproduced, so a
  31-day month compares against 31 days rather than the previous calendar month. That is
  upstream's behaviour, but it is odd enough to be worth a second look.

---

# REVIEW RESOLUTION — human pass over the phase 3 concerns

Everything above was written by the unattended run. This section records what happened
when those concerns were worked through afterwards.

## Fixed

**`change_password` brute-force protection — the top concern.** Commit `3eaf43c`.

Reading the source found the same gap on **`login`**, which matters more and this report
did not mention: `change_password` needs a session, `login` needs nothing. Both are now
protected, as upstream does it — `LoginAttemptTracker` on login keyed to **IP and
account**, both mechanisms on `change_password`.

Two things that decide whether it works, neither obvious: the counters need shared
storage (Django's default cache is per-process, so four workers turn a 10-attempt limit
into 40), and the client IP must be the real client (`TRUSTED_PROXY_COUNT` defaults to 0,
ignoring `X-Forwarded-For`, because a forged header would otherwise let an attacker pick
a fresh bucket per request).

Found while testing: Django's `authenticate()` rejects inactive users internally, so a
disabled account and a wrong password arrived identically and were counted the same —
which kept an account locked after an admin re-enabled it. Now distinguished.

Suite 1106 → 1128.

## Disputes — both upheld

**`frappe.client.insert` does not set `lead_owner`.** Verified independently:
`crm_lead.json` declares no default and no `reqd`; nothing in `crm_lead.py` fills it; the
**browser** does, at `LeadModal.vue:187-189`. Upstream has exactly this behaviour.

The dispute stands, and the reasoning was right — but the consequence is now written into
`AS_BUILT.md` §4 rather than left in this file, because it is reachable in a way it is
not upstream: **a bulk import omitting the field creates records nobody can see**, with no
error. A server-side default was considered and rejected: stamping the caller as owner
would silently claim every imported record, which is unrecoverable and wrong for any
assign-later workflow.

**`duplicate_assignment_rule` throws a non-upstream message.** Upheld without further
work. `Assignment Rule` is not modelled, so the options were raise or fabricate a rule the
UI would then display. Raising is the honest one.

## Divergences — all six confirmed, keep

Reviewed as a block. Each makes this port stricter than upstream, and none was reversed.

| | Divergence | Note from the review |
|---|---|---|
| D1 | `remove_assignments` ignores `ignore_permissions` | The flag is ignored unconditionally and write permission always checked. Single-tenant, so the exposure is any employee against any lead — including unassigning a manager, which revokes their access |
| D2 | Product totals computed server-side | Upstream sums them in browser JavaScript and stores what arrives. Same formula, different author. **Spot-check the arithmetic against real figures before go-live** |
| D3 | `get_linked_deals` permission-filters | Upstream checks the contact then fetches every linked deal unchecked, so a shared contact exposes deal values from accounts the caller cannot open |
| D4 | `search_link` respects permissions | Lower risk than first assessed: only Lead, Deal and Notification have row rules, so the dropdown only narrows when linking to those |
| D5 | `create_email_account` restricted to managers | Otherwise any authenticated user could add an account and set it default outgoing, redirecting the system's mail. Matches least-privilege guidance for SMTP configuration |
| D6 | Dashboard charts permission-filtered | **Not a divergence to apologise for.** Role-scoped dashboards are the documented norm — reps see their own pipeline, executives see the organisation. Upstream showing everyone company-wide totals is the unusual choice. If a company-wide figure is wanted later, a leaderboard widget is the accepted pattern |

## Verified

**B2** — the `lead_owner` claim, above. Closed.

## Also fixed in the review pass

**A2 — field-change history in the timeline.** Commit `70dd970`. Ports Frappe's
`Version` doctype, narrowed: upstream records **every** field including description
edits, this records a declared list per model (money, ownership, dates). Full parity
would mean an extra INSERT on every save forever and a timeline entry for every corrected
typo. Status is excluded because `CRM Status Change Log` already carries it, with a
duration per transition. Widening `TRACKED_FIELDS` is one line per model.

**B1 — the dashboard's comparison baseline.** Upstream derives it with `date_diff`, which
returns the *gap* between two dates rather than the number of days in the range, so the
baseline was always one day shorter than the period it was compared against and **every
percentage was inflated ~3%**. Eight months in twelve affected. Fixed. Calendar alignment
was deliberately *not* changed — that part is a design choice, recorded as option C in
`UPSTREAM_BUGS_PHASE_3-6.md` #13.

**B3 — the `remove_assignments` upstream hole.** Verified independently. `assign_to.py:215`
holds the permission check, `crm/api/doc.py:603` lets the caller switch it off. The claim
was accurate and the divergence stands.

**A4 — email credentials validated before saving.** The phase-3 note said this port had
no mail layer; it has one — Django's SMTP backend wraps `smtplib`, and `imaplib` is
standard library. All three of upstream's escape hatches ported (`awaiting_password`, the
localhost bypass, `no_smtp_authentication`). `EmailAdd.vue:149` has held the error string
`"Failed to create email account: invalid credentials"` since the frontend was written;
it was unreachable until now.

One divergence: upstream passes **no connection timeout**, so an unreachable host blocks
the save for 20–130 seconds while the user watches a spinner. We pass 10 seconds
(`MAIL_CONNECT_TIMEOUT`). A genuinely slow but working relay could exceed that and be
reported as broken — **raise the setting, do not remove it.**
`UPSTREAM_BUGS_PHASE_3-6.md` #15.

## Deferred — A3 / C16, six dashboard charts

**Not done, deliberately parked.** Revisit when the dashboard has users.

`sales_trend`, `forecasted_revenue`, `funnel_conversion`,
`average_time_to_close_a_lead`, `average_time_to_close_a_deal`,
`deal_status_change_counts`.

All six resolve to `None`, which is what upstream returns for an unknown chart name — so
the tiles render **empty rather than broken**, and nothing errors.

**Why they are grouped:** every one needs arithmetic across *time* — bucket counts by
month, or average the number of days between two dates. The charts already ported are
plain counts and sums. So this is one body of work, not six unrelated ones, and doing any
of them builds the machinery for the rest.

**Where they live:** listed in `dashboard.UNPORTED_CHARTS`, so the set is discoverable
from the code rather than only from this file.

**What to weigh when picking it up:** `forecasted_revenue` and `funnel_conversion` are
often the reason a sales director opens a dashboard at all. If nobody has asked for them,
empty tiles are honest. If they are wanted, budget for the shared time-bucketing helper
first — that is the part worth getting right once.

## Still open from this phase

- **Six dashboard charts** — deferred, see above. The only item from this phase's own
  scope still outstanding.

Carried to later phases, not gaps in this one:

- **`_resolved_fieldtype`** is a plaster and will be wrong for any fieldtype distinction
  beyond Select-vs-Data → **phase 4**, which builds the metadata layer that removes the
  need for it.
- **`search_link` returns no title field**, so link autocompletes look bare → **phase 4**,
  same reason: it needs a per-doctype title field from metadata.
- **`oauth_providers` and `get_assignment_rules_list` return `[]`** — both need framework
  doctypes (`Social Login Key`, `Assignment Rule`) outside the ported surface → **phase
  7/8**. Empty is what upstream returns when none are configured, so this is only visible
  once those integrations exist.
