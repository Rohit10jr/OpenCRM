# PROGRESS

Unattended run, started 2026-08-14. Newest entry at the bottom. Read the **Concerns**
section of each phase first — that is where the honest uncertainty lives.

> **Environment defect affecting every gate — read this first.**
> `codex exec -s read-only` **cannot run on this machine.** Codex's Windows sandbox
> fails to spawn any child process:
> `windows sandbox: runner failed during SpawnChild: CreateProcessAsUserW failed: 5
> (Access is denied.)`
> It fails identically with `-s workspace-write`, and it fails on a bare `Get-Location`,
> so it is the sandbox runner, not the repo or the command. **Codex still exits 0**, so
> a script that only checks the exit code would silently record a review that never
> happened. Mine did not: the first run produced no findings and an explicit "I couldn't
> complete the review" message.
>
> **Workaround used:** Codex itself suggested it — *"or paste the relevant files, and
> I'll review"*. Every gate review is therefore run as
> `Get-Content prompt.txt | codex exec -s read-only`, with the source files inlined into
> the prompt with line numbers. Codex needs no shell, `-s read-only` stays on, and the
> `file:line` citations remain accurate. This contradicts `CLAUDE.md`'s "Don't paste code
> into the prompt; point it at paths", which assumes path reading works.
>
> **Cost:** Codex sees only the files I choose to inline, so it cannot go looking. A
> review is only as good as my file selection. Treat every Codex verdict below as
> scoped, not exhaustive.
>
> I did **not** work around this with `--dangerously-bypass-approvals-and-sandbox`. That
> would have removed the "Codex cannot touch your files" guarantee the runbook is
> explicitly buying, and the harness blocked it anyway.

---

## Phase 0 — PASS   [branch: phase-0-foundation]
Started: 2026-08-14 00:45   Finished: 2026-08-14 01:35   Commit: `<see git log>`

**Built:** The Django skeleton and the whole phase-0 contract: `BaseDocument` with the
six naming strategies and the four underscore caches, the DocType registry, the Frappe
filter-grammar translator, the generic `/api/resource/` viewset, `/api/method/` dispatch,
`crm.api.doc.get_data` (list branch complete, kanban structural), JWT auth, the Frappe
response/error envelopes, and named, *tested* extension points for phases 2 and 4.
4,508 lines of Python across `frappe_core`, `frappe_platform`, `config`, and tests.

**Tests:** **235 passing**, 0 failing, ~15s. Every phase-0 acceptance criterion has a
real test. Mapping:

| Criterion (spec §10) | Tests |
|---|---|
| 1. `/api/resource/` with `filters` + `fields` returns `{"data": [...]}` | `test_resource_api.py` (30) |
| 2. All six naming strategies | `test_naming.py::test_naming_series_*`, `test_field_value_*`, `test_autoincrement_*`, `test_hash_*`, `test_format_*`, `test_prompt_*` |
| 3. Series atomic under 50 concurrent creates | `test_naming_series_is_atomic_under_50_concurrent_creates` (50 real threads), `test_concurrent_document_creates_get_unique_names` |
| 4. `@me` in dict, operator, tuple forms | `test_filters.py::test_me_resolves_in_{dict,operator,tuple}_form` + 5 more |
| 5. `like` case-insensitive | `test_like_is_case_insensitive`, `test_like_generates_case_insensitive_sql`, `test_like_wildcards_map_to_anchored_lookups` |
| 6. `get_data` returns data + columns + rows | `test_get_data.py` (34), incl. `test_response_has_every_upstream_key` |
| 7. JWT login/refresh; token reaches an authenticated endpoint | `test_auth.py` (23), incl. `test_token_from_login_reaches_an_authenticated_endpoint` |
| 8. Phase 2/4 hooks called and provably wired | `test_hooks.py` (27) — registers a hook, drives a real request, asserts it was consulted *and* honoured |
| 9. Throwaway model routable in ≤3 lines | `test_a_registered_model_is_routable_with_no_view_code` |
| 10. Specs 3–6 revised | done — see "Spec revisions" below |

**Two criteria are verified indirectly. Both are named here rather than buried:**

- **Criterion 1 names `CRM Lead`,** which phase 0 is forbidden to build (spec §9). It is
  tested against a phase-0 test doctype using the identical request shape
  (JSON-encoded `filters` list-of-tuples + `fields`, doctype name containing a space).
  **Re-run it against the real `CRM Lead` in phase 1.**
- **Criterion 7's "patched frappe-ui reaches an authenticated endpoint"** is proved
  server-side end-to-end (login → token → authenticated call, `test_auth.py`). The
  JavaScript patch itself has **no automated test** — this repo's frontend has no test
  runner wired for it. Verified by reading, not by running.

**Migrations:** apply cleanly from empty; `makemigrations --check --dry-run` reports no
changes. `pytest-django` builds and drops `test_opencrm` every run, so the from-empty
path is exercised 226 times per run.

---

### Codex findings

Round 1 produced 5 findings. **I fixed 4 and dispute 1.** Each fix has a regression test
named after the finding.

| # | Finding | Verdict |
|---|---|---|
| 1 | `FieldValue` doesn't slugify | **Disputed** — see below |
| 2 | `get_data` silently dropped list/tuple filters | **Fixed** — real, and the worst of the five |
| 3 | `like` on a JSON column was case-sensitive | **Fixed** — real |
| 4 | Hidden columns checked the column dict, not field metadata | **Fixed** — real |
| 5 | Repointing a ToDo left the old document's `_assign` stale | **Fixed** — real |

**Finding 2 was the serious one.** `get_data` coerced `filters` through a dict cast, so
the list-of-tuples grammar (which the spec explicitly requires, §5) became `{}` — and the
caller got an **unfiltered list back** instead of an error. Silently widening a result
set is a bad failure mode: the rows are still permission-filtered, but a caller asking
for "my open leads" would have received every lead they can see. Now both shapes pass
through to the shared translator; `_merge_filters` handles `default_filters` for each
shape; the kanban branch normalises too. Six new tests, incl.
`test_list_form_filters_are_not_silently_dropped`.

Note upstream is *also* wrong here, differently: `frappe._dict(filters)` raises on a
3-tuple list. Raising is at least visible, which is why the new code raises on a genuinely
unusable type rather than defaulting.

**Finding 3.** I originally mapped `like` on a JSONField to JSON containment
(`__contains=[x]`), reasoning that `_assign` is a real list here. Codex was right that
this diverges twice: containment is case-**sensitive** on Postgres, and it matches whole
elements where upstream matches substrings. Upstream stores `_assign` as a JSON *string*
and runs a plain `LIKE '%user%'`, case-insensitive because MariaDB's LIKE is. Django
renders `icontains` on a JSONField as `UPPER(col::text) LIKE UPPER(...)` — verified
against the live database — which is upstream's behaviour exactly. Switched.

**Finding 4.** Upstream reads `hidden` from the *doctype field metadata*
(`crm/api/doc.py:350-352`), not from a flag on the column dict as I had it. Now consults
a model-declared `get_hidden_fields()` (same pattern as `get_non_filterable_fields()`)
as well as the column flag. **Deliberate divergence:** upstream mutates `columns` while
iterating it, so a hidden column causes the *next* column to be skipped. I iterate a
copy. Replicating that would drop visible columns at random;
`test_removing_a_hidden_column_does_not_skip_the_next_one` locks in the corrected
behaviour. Flagging it because it is a real, if minor, behavioural difference from
upstream.

**Finding 5.** Real. A ToDo can be repointed at a different document; rebuilding only the
new target left the old one advertising an assignee it no longer had. `pre_save` now
stashes the previous reference and `post_save` rebuilds both.

#### Disputed: finding 1, `field:` autoname and slugification

Codex says `FieldValue.generate()` should slugify, citing `PHASE_0_FOUNDATION.md` line 36
("PK = that field's value, **slugified**"). **I did not slugify, and I believe the spec
line is wrong.** `CLAUDE.md` and `RUNBOOK.md` both rank the Frappe source above the spec:
*"Never invent Frappe semantics. The source is the truth."*

Evidence from source that names are stored verbatim — `crm/demo/deals.py`:

```
line 75:  # Organization logos keyed by org name
          _org_logos = {"ScaleUp Labs": ..., "Meridian Systems": ...,
                        "Vertex Analytics": ..., "Forge Digital": ...}
line 92:  org = frappe.db.get_value("CRM Deal", d_name, "organization")  # a Link value == the PK
line 94:  logo = _org_logos.get(org)                                     # looked up in the dict above
line 96:  frappe.db.set_value("CRM Organization", org, ...)              # used as the PK
```

`CRM Organization`'s autoname is `field:organization_name`. If the PK were slugified it
would be `scaleup-labs`, every `_org_logos.get(org)` would return `None`, and no demo
organization would ever get a logo. The asset *paths* in that same dict **are** slugified
(`/assets/crm/images/demo/scaleup-labs.png`) — they slugify for filenames, not for record
names, which is the contrast that makes this conclusive.

Corroborating: `crm/fcrm/doctype/crm_lead/crm_lead.py:244-262` round-trips a lead's
free-text `organization` through the Organization's PK and back into `organization_name`;
slugifying would corrupt the display name of the second lead referencing the same
organization. And `grep -rn "slugify|scrub(" crm/` finds no slugification anywhere in the
app.

**Action for a human:** `specs/PHASE_0_FOUNDATION.md` line 36 should drop the word
"slugified". I did not edit it — phase 0's own spec is Authoritative and human-owned, and
the runbook only assigns me specs 3–6.

#### Round 2 — dispute upheld, two new defects found

I put the four fixes and the demo-data evidence back to Codex.

**On the dispute, Codex reversed itself:** *"FieldValue slugification: dispute upheld.
Your Frappe source evidence settles it... My prior finding should be withdrawn."* It
confirmed fixes 2–5 as correct, and noted fix 2 was incomplete — which led to:

**Two new real defects, both in `get_data`, both fixed:**

- **A. The kanban branch inverted a non-equality filter on `column_field`.** My round-1
  fix built a `{fieldname: value}` map that *dropped the operator*, so
  `filters=[["status","!=","Closed"]]` with `column_field="status"` was read as
  `status == "Closed"`: every other column was blanked and the Closed column was
  populated — the exact inverse of the request. Now only an `=` condition can pre-select
  or blank a column; any other operator is preserved and AND-ed with the column's own
  constraint. Three regression tests, incl.
  `test_kanban_does_not_invert_a_non_equality_filter_on_the_column_field`.

  **Divergence, deliberate:** upstream compares `filters.get(column_field) != kc.name`,
  which for the operator form compares a list against a string, is always unequal, and
  therefore blanks *every* column — a blank board. I AND instead, which narrows
  correctly. Upstream's equality path is preserved exactly
  (`test_kanban_equality_filter_selects_only_the_matching_column`).

- **B. Fallback columns/rows could be overwritten with an empty default.** A doctype with
  no `default_list_data()` (or one returning `columns` but no `rows`) had the fallback
  assigned early and then replaced by the empty default. It happened to recover, because
  step 4 re-adds every column key to `rows` and the registry's fallback is identical to
  `get_data`'s — but only by coincidence, and a malformed saved view would still have
  produced a column-less list. Both branches now fall back again when they resolve to
  empty. Two tests, incl.
  `test_doctype_without_default_list_data_still_gets_columns_and_rows`.

Round 2 is the reason I ran a review at all rather than trusting the round-1 pass: the
round-1 fix for finding 2 introduced defect A. **Fixes need review as much as the
original code does.**

#### Round 3 — clean

Codex on the two round-2 fixes: *"Both fixes are correct and complete... I agree with
not copying upstream's blank-whole-board behavior for operator filters. No remaining or
new defects found. `get_data` is now clean."*

Three rounds total: 5 findings → 4 fixed + 1 withdrawn; 2 new findings → both fixed;
clean.

#### Two further defects I found myself, after Codex signed off

Codex only sees the files I inline (see the environment note at the top), so I re-read
the paths it never received. Two real bugs in the create path, both now fixed and tested:

- **`prompt` doctypes could not be created through the API.** `name` is `editable=False`
  on `BaseDocument`, so DRF derives it as **read-only** and silently ignored my
  `extra_kwargs={"name": {"required": True}}`. The client-supplied name was dropped and
  the create failed. `build_serializer_class` now declares an explicit writable `name`
  field for `prompt` strategies. Only `crm_form_script` uses `prompt`, so this would
  have surfaced as a mystery in phase 3.

- **A duplicate-name POST silently overwrote an existing document.** Django only
  auto-forces an INSERT when the PK has a default, which a `CharField` PK does not — so
  it ran UPDATE-then-INSERT. For any doctype whose PK comes from the client or from user
  data (`prompt`, and all 14 `field:` doctypes), POSTing an existing name **updated
  somebody else's row** instead of failing. `BaseDocument.save` now forces an insert
  whenever the instance did not come from the database, which turns that into the
  `IntegrityError` the error handler already renders as Frappe's `DuplicateEntryError`
  (409). Tests: `test_creating_a_duplicate_name_does_not_overwrite`,
  `test_duplicate_field_named_doctype_does_not_overwrite`.

  This one was the most serious defect found in phase 0 — a cross-document data-loss
  bug reachable from the public create endpoint — and no review round caught it. It is
  the clearest evidence for the concern logged below about how narrow the Codex reviews
  are in this environment.

---

### Decisions made without you

1. **Error-envelope shape — `PHASE_0_FOUNDATION.md` §6c, open question #2. ANSWERED.**
   Settled from the frontend's own consumers, not guessed. The envelope carries
   `exc_type`, `messages` (list of plain strings), `message` (scalar), `_server_messages`
   (a JSON string of JSON strings), and `exception`. Evidence: `src/data/document.js:40,43,61`
   branch on `err.exc_type`; `:41,46` read `err.messages[0]`; `:62` calls `.map()` on it,
   so it must be a list of strings; `SettingsPage.vue:92` prints `err.message` as a
   separate scalar; `FilesUploader.vue:216` does
   `JSON.parse(JSON.parse(error._server_messages)[0]).message`, which pins the double
   encoding. HTTP status codes follow Frappe's (`ValidationError` 417, `PermissionError`
   403, `DoesNotExistError` 404, `AuthenticationError` 401). All asserted in
   `test_envelope.py`, each with the citation on the assertion.

2. **SLA compute timing — `PHASE_5_ASYNC.md` §4, open question #1. ANSWERED: on write.
   There is no scheduled job; do not invent one.** `before_validate()` → `set_sla()`
   (`crm_lead.py:78-79`, `crm_deal.py:80-81`); `before_save()` → `apply_sla()`
   (`crm_lead.py:99-100`, `crm_deal.py:104-105`); `apply(doc)` mutates the doc in place
   (`crm_service_level_agreement.py:74-79`); and `scheduler_events` in `hooks.py:217-231`
   contains **no** SLA entry — a grep for `sla|service_level` across `hooks.py` returns
   nothing. Consequence worth knowing: `handle_sla_status` compares
   `response_by < now_datetime()` *at save time*, so a lead that breaches while untouched
   keeps showing `First Response Due` until the next write. That is upstream behaviour;
   adding a sweep would make our lists disagree with upstream's. Written into
   `PHASE_5_ASYNC.md` §4 with the citations.

3. **`@me` resolution replaces *every* occurrence, at any depth.** Upstream
   (`crm/api/doc.py:283-293`) scans only the top level, replaces the *first* `@me` via
   `list.index()` but *every* `%@me%` via a loop, and short-circuits the second check with
   `elif`. That is internally inconsistent. I replace both tokens everywhere. Identical to
   upstream for every filter the product actually sends (a token appears at most once per
   value), and it resolves the inconsistency in the direction upstream already takes for
   `%@me%`.

4. **`field:` autoname is verbatim, not slugified.** See the dispute above. This is the
   judgment call I would most want a human to confirm, because it is expensive to reverse
   — it decides every URL for 14 doctypes.

5. **`like` honours SQL wildcards instead of mapping blindly to `icontains`.** The spec
   says `like → icontains`. Taken literally, `icontains` on the frontend's pre-wrapped
   `%foo%` searches for a literal percent sign and matches nothing. So `%foo%`→`icontains`,
   `foo%`→`istartswith`, `%foo`→`iendswith`, `foo`→`iexact`, and interior wildcards fall
   back to `iregex`. Case-insensitive in every branch, which is what the spec was
   protecting.

6. **Phase 0 built one model the spec arguably excludes: `User`.** Spec §9 says build no
   models, but §7 requires JWT auth and email PKs, and `BaseDocument.owner` needs a FK
   target. `AUTH_USER_MODEL` cannot be moved later without pain, so it is fixed now in
   `frappe_platform`. **Phase 1 cluster 1 owns the rest of that app** (Contact, ToDo,
   Communication, Comment, Email Template, File, Tag, Email Account) and should extend
   `User` rather than replace it.

7. **`Administrator` and `Guest` are seeded as real User rows** (migration
   `frappe_platform/0002`), because Frappe treats them as real users and
   `BaseDocument.save` stamps `owner` with the ambient user — which is `Guest` outside a
   request. A transactional test flushes them, so `tests/conftest.py::builtin_users`
   restores the invariant per test rather than weakening the model to tolerate a dangling
   FK.

8. **The two "assigned" definitions are kept deliberately separate.**
   `crm/api/doc.py:608-625` excludes `Closed` **and** `Cancelled` for display;
   `PHASE_2_PERMISSIONS.md` §2 excludes only `Cancelled` for access. `_assign` mirrors the
   display definition; `get_assigned_users(..., for_permission=True)` implements the other.
   A document can therefore grant access to someone absent from `_assign` — which is
   exactly why phase 2 must query ToDo. `test_assignment.py::test_a_closed_todo_still_grants_access_but_is_not_displayed`
   locks this in. **Phase 2 should confirm this reading against the framework source if it
   becomes available.**

9. **Spec status stays PROVISIONAL, not Authoritative.** `specs/README.md` tells the
   phase-0 agent to flip specs 3–6 to Authoritative; `RUNBOOK.md` says leave them
   PROVISIONAL and add "Revised by phase-0 agent, pending human review". They conflict.
   `TASK.md` says the runbook wins, so they stay PROVISIONAL. Noted at the top of each
   revised spec.

10. **`fields`/`order_by`/`group_by` are validated in phase 0, not phase 2.**
    `PHASE_2_PERMISSIONS.md`'s last criterion ("permission bypass is impossible via
    `fields`, `order_by` or `group_by`") is enforced now, in `frappe_core/query.py`,
    against the model's concrete fields — so relation traversal like
    `order_by=widget_owner__password` is rejected with 417. Phase 2 still owns the row
    rules; this just means the injection surface is closed before phase 2 starts.

### Deviations from spec

- **`class Meta: name_strategy = ...`** — Django's `ModelBase` rejects unknown `Meta`
  attributes, so a metaclass (`frappe_core/models.py:DocumentBase`) strips our keys before
  Django validates. Kept because the spec's §4 declaration is what five concurrent phase-1
  agents will copy; changing the syntax would have meant changing the spec everyone reads.
- **`like` wildcard handling** — decision 5.
- **`@me` replaces all occurrences** — decision 3.
- **`field:` verbatim** — decision 4.
- **Hidden-column iteration** — fixed upstream's iterate-while-mutating bug rather than
  reproducing it (Codex finding 4).
- **`get_data`'s `_selectable()`** — row keys the model has no column for are skipped for
  the *query* while staying in the returned `rows`. Upstream would raise. During a port a
  partially-built model naming one missing field would otherwise break the entire list
  view. Revisit once phase 1 is complete: by then a missing field is a genuine bug and
  should probably raise.

### Concerns

- **The Codex reviews are narrower than intended.** Because of the sandbox defect, Codex
  only ever sees the files I inline. It cannot notice something in a file I didn't think
  to send. That weakens the whole point of an independent second opinion, and it applies
  to *every* phase gate in this run — most importantly phase 2's security review.
- **The `field:` slugify dispute is the single most expensive thing to reverse.** It sets
  the primary key of 14 doctypes and every URL the frontend routes on. My evidence is
  strong and I acted on it, but a human should sign it off before phase 1 builds on it.
- **`get_data`'s kanban branch is structural, not complete.** Column resolution from a
  Link target or Select options works; `get_records_based_on_order` (per-column manual
  ordering) and `getCounts` (the email/comment/task/note badge counts) are absent — both
  need CRM models. Spec §6b only requires "structurally", but do not mistake it for done.
- **`_assign` is writable through the generic resource endpoint.** It is a normal model
  field, so a client with write access can set it. It is only a cache and the permission
  layer ignores it, so this is not an access-control hole — but it is untidy, and phase 1
  should make the underscore fields read-only on the serializer.
- **No login page exists.** The SPA redirects to the Frappe desk's login
  (`session.js:35`). Nothing in phases 0–4 serves that page or calls `login`. The backend
  endpoints and the token plumbing are done and tested; the page is not, and no spec owns
  it.
- **`logout` cannot revoke an access token.** `token_blacklist` is not installed, so a
  stolen access token stays valid until it expires (60 min default). Documented in
  `frontend/JWT_PATCH.md`; the code already calls `.blacklist()` if the app is ever added.
- **`metadata.py` keys its allowlists on Django internal types, not Frappe fieldtypes.**
  That mapping is lossy: `Long Text`/`Small Text`/`Text Editor` all collapse to
  `TextField`, and `Duration`/`Rating` are indistinguishable from `IntegerField`/
  `FloatField`. So the group-by list is slightly wrong today — `Duration` should be
  group-by-able and is only included by accident. Phase 4 must fix this once phase 1
  records each field's original Frappe fieldtype. Written into `PHASE_4_METADATA.md` §3.
- **I could not read the Frappe *framework* source**, only the `crm` app. Framework
  semantics (`make_filter_tuple`, `_field_autoname`, `assign_to.get_assignments`) were
  inferred from how the app uses them. Where that mattered I said so above.

### Spec revisions (deliverable 10)

All four marked **"PROVISIONAL — revised by phase-0 agent, pending human review"**:

- **`PHASE_3_ENDPOINTS.md`** — new §1a documents the as-built registry, `@whitelist`,
  envelope, permission and parameter-binding contracts, with a table of what to call
  instead of re-inventing; two new acceptance criteria closing the "bypassed the
  permission layer by using the ORM directly" hole.
- **`PHASE_4_METADATA.md`** — new §2a documents the exact seam left in `get_data`
  (`register_metadata_hooks`, the provider contract, the four `PHASE 4` stubs) and states
  that the response shape is already final; §3 records the fieldtype-allowlist defect above.
- **`PHASE_5_ASYNC.md`** — §4's open question answered from source with citations, plus a
  criterion asserting no SLA beat entry exists so a later agent cannot quietly add one.
- **`PHASE_6_REALTIME.md`** — auth and permission sections now point at the concrete
  phase-0 functions (`session_user`, `check_object_permission`) and at
  `frontend/JWT_PATCH.md` as the place to document the second frontend deviation.
