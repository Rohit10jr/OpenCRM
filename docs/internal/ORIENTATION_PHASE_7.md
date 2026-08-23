# Orientation — phase 7

Written before any code, per `RUNBOOK_PHASE_7.md` Step 0. Baseline verified on
`phase-7-prep`: **1342 passed, 31 skipped** (TASK.md said ~1,290; the count is higher, all
green, so the premise holds).

---

## 1. What exists that I must not rebuild

| Thing | Path |
|---|---|
| Six lead-sync tasks, registered, flag-gated no-ops | `crm_app/tasks.py:126-173` — `_sync_leads(frequency)` raises `NotImplementedError` when the flag is **on** |
| `run_product_reconciliation` + `_reconcile_products` seam | `crm_app/tasks.py:291-328` — returns `{"skipped": ...}` when off, calls the seam then publishes |
| Twilio + Exotel settings, credentials already encrypted | `crm_app/models/telephony.py:189-260` |
| `CRM Call Log`, `CRM Telephony Agent`, `CRM Telephony Phone` | same file, `:70-186` |
| Encryption at rest | `frappe_core.secrets.EncryptedFieldsMixin`, `ENCRYPTED_FIELDS` |
| Realtime publish | `crm_app.realtime.publish(event, message=None, user=None)` |
| Permission-filtered reads | `frappe_core.query.fetch_rows / count_rows / base_queryset` |
| Endpoint registration | `frappe_core.whitelist.whitelist("dotted.path")`, imported from `AppConfig.ready()` |
| Change history | `TRACKED_FIELDS` on the model; `specs/VERSION_HISTORY.md` |

`CRM Call Log` already exists with `reference_doctype`/`reference_docname` and a
`telephony_medium` choice list containing `Twilio` and `Exotel`. **The shared call-log path
is a write into this model, not a new one.**

## 2. The mechanisms that protect a doctype

Registering a doctype **publishes it**: `/api/resource/X` gives every authenticated caller
full CRUD, and `frappe.client.*` reaches it through `_get_checked`. Protection is opt-in.

**Row rule** (`has_permission` + `permission_query_conditions`) decides who may touch the
document at all. The list rule and the object rule may legitimately differ, and a write
path needs both — phase 5 shipped a bulk delete authorised from the list filter alone.

**The four field declarations**, and why two of them are usually needed together:

- `SENSITIVE_FIELDS` keeps a value **off the wire** — not serialised, not selectable in
  `fields=`, and not usable in `filters` / `or_filters` / `order_by` / `group_by`. That
  last part is the whole point: hiding a value from *output* leaves the row count as an
  oracle, and `["password","like","sw%"]` recovers it one character per request. That is
  how a real SMTP password was recovered from this codebase.
- `ENCRYPTED_FIELDS` keeps the plaintext **out of the database**. It protects a backup, a
  dump, a log, or anyone with SQL — none of which the wire-level rule touches.

Neither implies the other, and the failure modes are different. Encrypted-but-not-sensitive
is served over the API as ciphertext **and stays filterable** — better than plaintext, not
protected. Sensitive-but-not-encrypted is invisible over HTTP and sitting in plain text on
disk. A real credential needs both; `test_credential_fields.py` enforces that.

- `RESTRICTED_FIELDS` — manager-only read. Applied **per request**, because serializers are
  built once per model and cached and so cannot know who is asking.
- `READONLY_FIELDS` — everyone reads, nobody writes. For a field whose subject must not set
  it (`User.enabled`).

**And a rule as well as the declarations.** `SENSITIVE_FIELDS` hides the value; it does
nothing to stop the *record* being rewritten. Hiding a mail password did not stop anyone
repointing the server it belonged to. For a webhook secret this is sharper than usual: an
attacker who cannot read the token but can *overwrite* it can set one they know and then
forge signed webhooks.

**`routable=False`** withholds the route entirely — correct when nothing addresses the
doctype over HTTP, because a route that does not exist is a smaller surface than a guarded
one. The two questions that settle it (`SECURITY_MODEL.md`): does anything actually call
this route, and do the `frappe.client.*` endpoints share the check?

## 3. What I believe is stale or wrong in these documents

Five, all verified rather than suspected.

1. **`specs/AS_BUILT.md:161` gives the wrong argument order for `publish`.** The phase-5
   table says `publish(event, user=..., message=...)`; the real signature is
   `publish(event, message=None, user=None)` (`realtime.py:83`), and the phase-6 section
   30 lines below says so and explains why the order matters. The stale row comes **first**
   in the file. This is precisely the mistake phase 6 warned about: `publish("exotel_call",
   payload)` under the wrong reading hashes the payload into a group name nobody is in and
   returns `True`. Exotel is one of my five integrations. **I will fix this row in my first
   commit** rather than carry it.
2. **`UPSTREAM_BUGS*.md` is gitignored** (`.gitignore:59`, deliberately — "local working
   notes"). The runbook gives me a standing obligation to record every divergence there, in
   a file that is never committed and that a reviewer cannot see. I will comply *and*
   summarise each divergence in `PROGRESS_PHASE_7.md`, which is tracked, so the record
   survives.
3. **`CLAUDE.md` says "18 cases" of upstream bugs.** There are 21; the runbook says 21 and
   tells me to continue from there. Minor, but it is the kind of drift that makes the next
   agent trust a count instead of reading.
4. **`AS_BUILT.md`'s header says "Phases 0–2 are complete and reviewed"** while the file
   documents through phase 6. Harmless to me, misleading about how much of it is load-bearing.
5. **`CLAUDE.md` says "Report findings to me… Don't auto-apply them"; the runbook says
   "Act on the findings."** For an unattended run the runbook is right and it is what
   phases 3–6 did. Following the runbook, recording disagreements.

**And one about my own starting point.** TASK.md says to cut from `main`. `phase-7-prep`
carries six commits `main` does not — including `RUNBOOK_PHASE_7.md` itself and
`tests/test_credential_fields.py`, the test the runbook says will fail on me. Cutting from
`main` would silently discard both. **Branching from `phase-7-prep`.**

## 4. What I do not understand yet

- **Which ERPNext endpoints are reachable without a live instance.** `erpnext_crm_settings.py`
  is 690 LOC and 12 endpoints; several (`get_customer_link`, `prefill_quotation_items`) look
  like pure URL construction plus a remote read. I will read before deciding what is
  testable at the seam versus what needs a stub client.
- **What `frappe_whatsapp`'s message model actually looks like.** It is not in this repo, so
  I am inferring the schema from `api/whatsapp.py`'s reads. Risk of inventing semantics —
  I will port only fields the six endpoints touch and say so.
- **Whether the six lead-sync frequencies map to distinct work** or are one job on six
  schedules. `lead_sync_source.py` is 69 LOC with `facebook.py` at 226; I expect one path
  parameterised by frequency, but I have not read it yet.

## 5. Risks I see in phase 7 specifically

1. **This is the credential-heavy phase.** ERPNext API key/secret, Meta long-lived page
   tokens, webhook signing secrets. Every new settings doctype trips both guard tests, which
   is the system working. The trap is the *fourth* checklist step — a rule, not just the two
   field declarations.
2. **Webhook endpoints are unauthenticated write paths from the public internet.** They
   cannot use JWT. Signature verification is the only thing standing there, and it must be
   constant-time and must reject on a missing signature, not just a wrong one.
3. **Import-time coupling is the easiest acceptance criterion to fail by accident.** One
   `import twilio` at module scope in a file that `apps.py` imports and the flag stops
   meaning anything. I will assert it, not assume it.
4. **`ENABLE_ERPNEXT=True` currently raises** at the `_reconcile_products` seam. Anything
   that turns the flag on in a test today gets a `NotImplementedError`, and `KNOWN_ISSUES`
   §5 notes this is why no Celery task has ever published to a browser end to end.
5. **Lead sync must be idempotent.** Re-running must not duplicate leads, and every created
   lead needs `lead_owner` set or it is invisible to everyone but a manager
   (`AS_BUILT.md` §4 — this bites integrations specifically).
6. **The 25,000-line-commit failure.** I am the run that produced it. A dozen or more
   commits, each green.

## 6. Plan

Order is by dependency and by risk, not by size.

1. **Fix `AS_BUILT.md:161`** — one commit, before anything can read it wrong.
2. **Shared call-log path** — the write into `CRM Call Log` both telephony providers use,
   plus `integrations/api.py`'s provider-neutral endpoints. Both providers depend on it, so
   it lands first and alone.
3. **Exotel** (~200 LOC) — smallest real integration, exercises the whole shape end to end:
   settings → outbound call → signed webhook → call log → realtime `exotel_call`. Proves the
   pattern before I repeat it.
4. **Twilio** (~250) — same shape, second provider. Confirms the shared path is actually
   shared rather than Exotel-specific.
5. **WhatsApp** (~200) — six endpoints, message model behind a named seam, `whatsapp_message`
   published as a **broadcast** (`AS_BUILT.md`, phase 6). No vendoring.
6. **Facebook lead sync** (~550) — fills the six registered tasks. Idempotency and
   `lead_owner` are the whole risk.
7. **ERPNext** (~1,300) — largest and last, as an API client. Fills `_reconcile_products`,
   which finally gives `crm_product_sync_complete` a live caller.

If ERPNext runs long I stop after 6 and say so. The runbook is explicit that a clean stop
with three integrations beats five unverified ones.
