# Phase 7 — PASS   [branch: `phase-7-integrations`]
Started: 2026-08-22   Finished: 2026-08-22

**Built:** All five integrations, each behind its own flag, all off by default.
**Tests:** **1574 passing**, 31 skipped (all pre-existing), 0 failing. 232 new.
Nothing skipped or weakened. **Migrations clean.** **Review: tier 1 (Codex, PowerShell 7).**

**9 commits**, each green and each one coherent piece of work — the rule that changed for
this run.

| # | Commit | What |
|---|---|---|
| 1 | `cc70f96` | Step 0 orientation + four stale claims it turned up |
| 2 | `e1a3dd2` | Shared telephony path + the isolation test |
| 3 | `beefb04` | Exotel + the shared HTTP helper |
| 4 | `1e32ee0` | Twilio |
| 5 | `6694931` | WhatsApp |
| 6 | `8374d22` | Facebook lead sync |
| 7 | `03641bb` | ERPNext |
| 8 | `f168edd` | Review fixes |
| 9 | *(this)* | Second-pass review fixes, docs, and this file |

## Acceptance criteria (`PHASE_7_INTEGRATIONS.md` §4)

| Criterion | Covered by |
|---|---|
| All flags off → suite passes, no integration code imported | `test_integration_isolation.py` — a **subprocess** boot, because this session has already imported what other tests needed |
| Each integration enables independently | `test_each_flag_is_independent` |
| Webhook signatures verified; unsigned rejected | `test_exotel.py` (8), `test_twilio.py` (14), incl. three over **real HTTP** |
| Credentials encrypted at rest, absent from logs | `test_both_access_tokens_are_encrypted_at_rest`, `test_the_endpoint_url_carries_no_credentials`, `test_the_secret_is_encrypted_and_not_selectable` |
| Provider outage does not break core CRUD | `test_an_unreachable_erpnext_does_not_break_the_deal_save`, `test_an_unresolvable_number_still_leaves_the_call_logged` |
| Lead sync idempotent | `test_re_running_the_same_batch_creates_no_duplicates` + `test_the_database_refuses_a_duplicate_facebook_lead` |
| Call logs identical for both providers | `test_both_providers_produce_the_same_shape`, `test_the_call_log_shape_matches_exotels` |

---

## Read this first if you read nothing else

**Two things upstream does that this port refuses to.**

1. **Twilio webhooks are authenticated by a value that is not a secret.** Upstream compares
   the `AccountSid` in the payload — which Twilio puts in *every* webhook, and which is in
   the console and in any log. Anyone who has seen one webhook can forge the rest, which
   writes call logs and, through `voice`, returns the TwiML that decides where an inbound
   call is routed. Twilio signs every request and upstream never checks it. We do.
2. **Synced Facebook leads have no owner.** Upstream inserts them with only the mapped form
   answers, and `lead_owner` is not among them — so every Facebook lead upstream is
   invisible to every Sales User. Reproducing that would mean the feature does not work.

**And one thing this port shipped that only worked in tests.** The Twilio signature check
was correct and unreachable: the endpoints took the signature as a *parameter*, and Twilio
sends it in a header. Green test file, non-functional integration. Found by the review; see
"The review" below.

---

## Decisions made without you

1. **Branched from `phase-7-prep`, not `main`.** TASK.md said `main`; `phase-7-prep` carried
   six commits `main` did not, including `RUNBOOK_PHASE_7.md` itself and
   `tests/test_credential_fields.py` — the test the runbook says will fail on me. Cutting
   from `main` would have discarded both.
2. **The deployment flag ANDs with the settings checkbox** (divergence #22). Upstream has
   only the checkbox. Otherwise the flag is advisory: anyone who can write the settings row
   could switch on outbound calling in a deployment that opted out.
3. **No Twilio SDK.** Signatures, TwiML and the access token are documented public formats,
   so writing them is transcription. It keeps a module-scope SDK import out of the process
   and puts every outbound call through the shared HTTP helper. **The cost is real:** an SDK
   upgrade would track Twilio's API changes for us and this will not.
4. **ERPNext: only the remote path is ported.** The same-site mode presupposes ERPNext's
   models and Frappe's runtime-schema machinery in this process, which the standing decision
   rules out. Those branches refuse with a message naming the reason rather than silently
   doing nothing. That removed ~2/3 of `erpnext_crm_settings.py` from scope, for a reason
   rather than for time.
5. **Facebook leads are owned by `Administrator`.** Something had to own them (see above),
   and `AS_BUILT.md` §4 is explicit that stamping "whoever ran the sync" is the wrong fix —
   it claims records for one person, unrecoverably.
6. **`ensure_facebook_lead_source` creates the `Facebook` lead source on demand.** This port
   never ported upstream's `add_default_lead_sources()`, and `CRMLead.source` is a real FK —
   so every synced lead failed with a `ValueError` the per-lead `except` swallowed into a
   failure log. The wider gap is item 3 under "Concerns".
7. **`WhatsApp Message` defers to its referenced document** rather than getting its own rule.
8. **Idempotency got a database constraint**, not just the application check.
9. **`wants_request` added to `frappe_core.whitelist`** — a framework change, opt-in, and
   the only way a handler can see the header a signature arrives in.
10. **Four stale claims fixed in Step 0**, the most important being `AS_BUILT.md:161`'s wrong
    argument order for `realtime.publish` — which the phase-6 notes 30 lines below warn
    about specifically, and which Exotel would have hit.

## Deviations from spec

- ERPNext same-site mode not ported (decision 4).
- `WhatsApp Templates` not ported — `render_template` returns `None` and template messages
  are left unenriched rather than given a fabricated body.
- `update_call_status_info` does not post a `user_defined_message` back to Twilio; that
  relies on the SDK's parent-call relay, and this port publishes over its own Channels layer.
- `get_the_call_attender` cannot narrow to "currently logged in" — no server-side session
  table, which is phase 0's sanctioned deviation. With several agents on one Twilio number,
  upstream rings the one at their desk and this rings the first reachable one. The
  deal/lead-owner preference is kept.

## Upstream bugs recorded — #22 to #33

`UPSTREAM_BUGS_PHASE_3-6.md` (**gitignored**, so the summaries below are the tracked record).

| # | Bug | Us |
|---|---|---|
| 22 | A settings checkbox is the only gate on outbound calling | stricter |
| 23 | Provider credentials embedded in the request URL | stricter |
| 24 | No timeout on any provider call | stricter |
| 25 | Webhook token compared with `==` (timing oracle) | stricter |
| 26 | Exotel `busy` reported as `Ringing` | **reproduced** — user-visible |
| 27 | Twilio webhooks authenticated by a non-secret | stricter |
| 28 | Facebook page access token stored in plain text | stricter |
| 29 | Synced Facebook leads have no owner | diverge |
| 30 | Duplicate check crashes on an unanswered optional question | diverge |
| 31 | Reconciliation issues accumulate on every run | diverge |
| 32 | A provider outage rolls back a deal's status change | diverge |
| 33 | Meta access tokens travel in the query string | stricter |

## The review — tier 1 (Codex, PowerShell 7)

Ran clean, with real `file:line` citations. **Eight findings: six fixed, one disputed, one
already recorded.** It took ~12 minutes, over the runbook's 10-minute bar; the output was a
genuine review rather than a timeout, so it was accepted rather than re-run narrower.

Every finding was the same shape — **a second door**: an endpoint or mechanism doing the
same job as a guarded one, without the guard.

**High — `frappe.client.get_single_value` bypassed both mechanisms.** It rejected
`SENSITIVE_FIELDS` and checked nothing else: no row rule, no `RESTRICTED_FIELDS`. Any Sales
User could read `CRM Exotel Settings.webhook_verify_token` — the entire authentication on a
public webhook — and `ERPNext CRM Settings.api_key`. **The hole is phase 3's**, and there
were no tests for that endpoint at all, which is how it survived; phase 7 made it serious by
putting credentials behind restricted fields.

**High — the Twilio signature check was unreachable in production.** Described above. The
worst kind of finding: the check existed, was correct, and the production path never reached
it. Fixed with `wants_request`, plus three tests that drive the real HTTP stack.

**Four Mediums**, all fixed: WhatsApp wrote while switched off; `get_external_companies`
called out for a disabled integration; `dismiss_sync_issue` wrote to a child table around its
parent's rule; the Facebook duplicate check was a race.

**Disputed — the Exotel webhook token stays plaintext at rest.** Codex is right that it is a
credential in a column. It is not encrypted because `ExotelSettings.vue:66` binds it with
`v-model`: it is an editable input the administrator types into and reads back, so encrypting
it shows them ciphertext and saving re-encrypts that. Closing it needs a decrypt-on-read path
for permitted users (does not exist) or a frontend change. Either is a mechanism, not a review
fix. **The serious half is closed** by the `get_single_value` fix — it is manager-only now.

### The second pass

Re-reviewed after the fixes. **All six were confirmed closed**, and it raised four more —
two substantive, two answered.

**Fixed: Meta access tokens travelled in the query string** (#33). Upstream's form, and Meta
documents the `Authorization: Bearer` header as an equivalent. A query string is the worst
place for a long-lived credential — the far end's access log, any proxy between, a `Referer`
— and Graph hands the token back inside its own `next` URL, so following the cursor spread
it further. Now a header, with the cursor stripped before it is followed.

**Fixed: a docstring of mine had become false.** `integrations/exotel/__init__.py` said
*"Nothing here is imported at module scope by `apps.py`… `apps.py` imports it only when
`ENABLE_EXOTEL` is on."* It never was: I wrote it before deciding to register endpoints
unconditionally and never went back. Codex caught the contradiction between the sentence and
the code, which is precisely the failure `RUNBOOK_PHASE_7.md` describes under *"A claim you
write will be trusted"* — and it was mine, in the same phase that read that warning.

**Answered — integration modules are imported unconditionally, on purpose.** Codex read the
acceptance criterion as "no integration module is imported"; the isolation test reads it as
"no *provider SDK* is imported", and states that in its docstring. Registering endpoints
always is upstream's shape: `make_a_call` exists and refuses with *"Please setup Exotel
intergration"*. Gating registration would turn that dialog into a 404, and
`is_call_integration_enabled` must answer on every page load with both flags off. No provider
SDK is imported at module scope, which Codex confirms.

**Answered — `api_key` is restricted but not encrypted, on all three providers.** That
matches upstream's own classification: the *secret* half is a `Password` fieldtype (encrypted
in `__Auth`), the *key* half is `Data` with a `permlevel`. A key without its secret does not
authenticate anything. Encrypting identifiers alongside secrets would blur a distinction
upstream draws deliberately, and this port already restricts the keys, which upstream does
not do for Exotel's.

## Not ported — named, not hidden

- **ERPNext same-site mode** — custom fields, property setters, role grants on ERPNext's own
  doctypes, `check_customer_for_quotation`, `create_customer_on_sales_order`.
- **Bidirectional product reconciliation.** Ours links CRM Products to remote Items by code.
  Upstream also *creates* Items and Products on either side. `created_in_crm` and
  `created_in_erpnext` are in the summary and always zero, so the frontend does not gain a
  `KeyError`.
- **`WhatsApp Templates`**, and `add_roles()` (Frappe `Custom DocPerm`, no counterpart here).
- **`get_recording_url`** — the SSRF-safe recording proxy (`integrations/api.py:251-299`),
  with its IP pinning and per-hop redirect validation. Deliberately left for its own change:
  it is the most security-sensitive single function in the phase and deserves its own tests.
  The frontend does not call it by dotted path, so nothing is broken by its absence.
- **Facebook `get_pages_with_forms`** and the settings-screen discovery endpoints —
  `fetch_and_store_pages` exists and is tested; the thin whitelisted wrappers are not
  registered because the frontend for them is not in this repo's `OUT_OF_SCOPE` list.

## Concerns — what I would look at first with another hour

1. **`get_recording_url` is the biggest gap**, and the one most likely to be re-implemented
   badly by someone who has not read upstream's version. It defends against SSRF and
   DNS rebinding with IP pinning and per-hop redirect validation. Port it *with* those.
2. **The Exotel webhook token.** See "disputed" above. It needs a product decision, not a
   patch.
3. **No default lead sources or statuses are seeded anywhere.** Upstream's `install.py`
   creates fifteen lead sources and the status rows; this port creates none, and every test
   in the suite makes its own. The Facebook sync tripped over it. It belongs in an install
   or bootstrap step and would otherwise surface as a `ValueError` in whatever integration
   touches it next.
4. **Nothing here has met a real provider.** Every test stubs at
   `integrations.http.request` or at a named seam. That is the runbook's instruction and it
   is the right default — but signature verification against a *real* Twilio request, and
   the Graph pagination cursor, are the two places I would most want a live smoke test.
   `KNOWN_ISSUES.md` §4/§5 is the precedent for how to do that and write it up.
5. **The frequency map** (`tasks.FREQUENCY_LABELS`) is the only place the scheduler's slugs
   and the doctype's Select labels meet. A test asserts they cover each other, but a *new*
   frequency added to the Select without a task would silently never run.
