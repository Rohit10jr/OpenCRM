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
Started: 2026-08-14 00:45   Finished: 2026-08-14 01:45   Commit: `2a3b8df`

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

---

## Phase 1 — PASS   [branch: phase-0-foundation]
Started: 2026-08-14 01:50   Finished: 2026-08-14 03:20   Commit: `6e18bd8`

**Built:** All 46 models — the 9 platform doctypes (cluster 1) and 37 CRM doctypes
(clusters 2–6). Every one registers with the phase-0 registry and is routable with no
view code. Plus two pieces of framework the models turned out to need: credential
field-blocking and inline child-table serialisation.

**Tests:** **592 passing**, 31 skipped, 0 failing (~32s). Up from 235 at the end of
phase 0.

The 31 skips are all intentional and structural, not silence: `test_crm_models.py`
parametrises every doctype over the same checks, so "is this child table shaped
correctly" skips for the 27 doctypes that are not child tables, and the naming check
skips for the 3 singletons.

| Criterion (PHASE_1_MODELS.md §7) | How it is covered |
|---|---|
| Platform cluster lands first | Built and committed first; `test_platform_models.py` (51 tests) |
| Every model registers and is routable | `test_doctype_is_registered`, `test_child_tables_are_flagged_and_not_routable`, parametrised over all 37 |
| Correct naming strategy per doctype | `test_naming_strategy_matches_the_json` — reads `autoname` from each JSON and asserts the strategy class *and* its argument |
| No layout fieldtypes leaked | `test_no_layout_fieldtype_leaked_into_the_model` — 130 layout fields across the 39 JSONs, none materialised |
| Child tables: no route, inline, replace-on-write | `test_child_tables_are_not_routable_over_http`, `test_children_serialise_inline`, `test_writing_a_parent_replaces_children_wholesale` |
| `_assign` consistent with ToDo both ways | `test_assignment.py` (22) now runs against the real `ToDo`; plus `test_crm_behaviour.py` on real leads/deals |
| Migrations apply cleanly from empty | `makemigrations --check` clean; pytest-django rebuilds `test_opencrm` every run |
| Every `frappe.throw` has identical text | `test_crm_behaviour.py` asserts each message verbatim, incl. the two lost-reason messages that differ by one word |
| Cross-cluster FK targets exist | `test_link_fields_point_at_the_right_doctype` resolves every `Link` in every JSON to the actual related model's doctype |

**The schema tests read the Frappe JSON directly** rather than restating it. Transcribing
a schema by hand and then asserting my transcription matches my transcription proves
nothing; these compare the model to the source file, field by field, and skip loudly if
the source is missing.

**Also closed here:** phase 0's owed item — criterion 1 was tested against a stand-in
doctype because spec §9 forbade building `CRM Lead`. It now runs against the real one
(`test_lead_is_listable_with_the_criterion_1_request_shape`).

### Two defects I found in my own phase-0 work

- **`register_doctype` only worked for `BaseDocument` subclasses.** `User` derives from
  `AbstractBaseUser` (Django requires that of `AUTH_USER_MODEL`), so it had no
  `get_doctype()`. Every `Link`-target check against `User` therefore resolved to `None`
  and **passed vacuously**. Found by writing the FK-target test, which failed on 12
  doctypes at once. The decorator now attaches the accessor to any registered model.
  A test that only ever passes is worse than no test, and this one was one line from
  being exactly that.

- **Registering `User` and `Email Account` exposed credentials.** The generic serializer
  used `fields="__all__"` and the list endpoint honoured `fields=["*"]`, so
  `GET /api/resource/User?fields=["*"]` would have returned `password` — the hash — to
  any authenticated caller. Phase 0 was safe only because no model with a credential was
  registered yet. Added `frappe_core/field_security.py`, applied in **both** places that
  can emit a column (serializer and `query.resolve_fields`), plus `order_by`/`group_by`.
  Nine tests, including one that reads the JSON and asserts every `Password` fieldtype in
  the source is declared `SENSITIVE_FIELDS` — so a future agent adding one cannot forget.

### Codex findings

13 findings. **11 fixed, 1 disputed, 1 already-known.** Every fix has a regression test.

> **Read this caveat first.** Codex could not read the repo (the sandbox defect at the
> top), so for the controllers it **searched the web and read `frappe/crm` on GitHub
> `develop`**. This checkout is `main`. I therefore re-verified **every** finding against
> the local source before acting, and cite the local line numbers below. Two of its
> findings would have been wrong if taken at face value against the wrong branch; as it
> happens both areas agree between branches, but the risk was real and is the reason
> none of these were applied on Codex's word alone.

**Three findings were caused by my own tooling, and that is the lesson of this gate.**
My JSON inspection script truncated `options` at 50 characters. I then transcribed the
visible prefix and *guessed nothing* - I simply did not notice the values were cut off:

| Field | I had | Source actually has |
|---|---|---|
| `CRM Lead/Deal Status.color` | 9 colours, ending `yellow` | 13 - also `cyan`, `teal`, `violet`, `purple` |
| `CRM Fields Layout.type` | `...Data Fields, Grid Settings` | `...Data Fields, Grid Row, Required Fields` |
| `FCRM Settings.service_provider` | free `CharField` | a `Select` with 4 fixed providers |

I inspected the source through a lossy view and treated the result as the source. There
is now a test, `test_select_options_match_the_json_exactly`, that reads the **full**
`options` string for every `Select` on every ported doctype and fails if the model's
choices do not cover it - so a truncated transcription cannot pass again.

**The two substantive behavioural findings:**

- **`CRM Lead` name derivation was wrong in four ways** (`crm_lead.py:113-135`).
  `set_full_name` **mutates `lead_name`** and runs *before* `set_lead_name`; it fires
  only when `first_name` is set; it **includes the salutation**; and the email fallback
  uses the **local part** (`ada@example.com` → `ada`), not the whole address. My version
  returned a value nobody called, omitted the salutation, and stored the full address.
  `lead_name` is the primary display field on the busiest screen in the product, so this
  would have been visible on every lead. Six tests.

- **`CRM Call Log` could not be created manually** (`crm_call_log.py:50-54`). Upstream's
  `before_insert` generates a 12-char hash when `id` is blank and defaults
  `telephony_medium` to `"Manual"`. Without it, `field:id` naming raises - so the "log a
  call" flow would have failed outright. Three tests.

Also fixed: `CRM Product.set_product_name` (blank name falls back to the code),
`CRM Organization.update_exchange_rate` (ported with the settings read and the FX call
injected, since both are later phases), and `CRM Notification.on_update` (now a named
phase-6 seam rather than a silent omission - `PHASE_6_REALTIME.md` §2 lists that event
as in scope).

**Disputed — `facebook_lead_id` / `facebook_form_id` on `CRM Lead`.** Codex said these
should be absent because Facebook lead sync is phase-7 deferred. They are **plain `Data`
columns on `crm_lead.json`**, not part of the deferred `facebook_*` *doctypes*. Dropping
them would delete real columns from a doctype that is in scope and lose data on any
imported lead. Kept.

**Reversed my own decision — `FCRM Settings.access_key`.** I had marked it
`SENSITIVE_FIELDS` because it is an FX-provider credential. Codex pointed out the JSON
declares it `Data`, unhidden - upstream shows it in the settings UI, so the settings
screen reads it back. Blocking it would have broken that screen in exchange for a
hardening the source does not make. Reverted to readable, and flagged below rather than
diverged from silently.

**Already known:** Codex's remaining findings are the unported `validate` hooks on
`CRM Lead` and `CRM Deal` (default status selection, status-change-log append,
owner share/assign, primary-contact sync, Won `closed_date`). These were already listed
under Concerns before the review ran, and they remain the largest gap in phase 1. They
are not fixed here — see Concerns.

**Not ported, newly noted:** `CRM Call Log.links` is a `Table` of Frappe's `Dynamic Link`
platform doctype, which is outside the nine platform models in scope. Recorded as a gap.

### Decisions made without you

11. **Three child tables cannot take a foreign key.** `PHASE_1_MODELS.md` §3 says child
    tables get "FK to parent + parenttype, parentfield, idx". `CRM Products`,
    `CRM Status Change Log` and `CRM Rolling Response Time` are each embedded by **two**
    doctypes (`crm_lead.*` and `crm_deal.*`), so there is no single target. Verified by
    dumping every `Table` field across all 39 JSONs. Those three use Frappe's own
    polymorphic `parent` + `parenttype`; the other six child tables do get a real FK.
    Parents declare the polymorphic ones via `POLYMORPHIC_CHILD_TABLES`.

12. **Five Link targets are modelled as `CharField`, not tables.** `Salutation`,
    `Gender`, `Currency`, `Address` and `DocType` are Frappe platform lookups outside
    `PHASE_1_MODELS.md` §1's list of nine. The stored and transmitted value is identical
    (`"Mr"`, `"USD"`, `"CRM Lead"`), so the wire contract is unaffected. Creating five
    more platform tables would have been scope the spec explicitly warns against
    ("do not reimplement Frappe's platform").

13. **Platform doctype naming is the weakest evidence in the port.** The CRM repo shows
    which platform fields exist but never their `autoname`. `ToDo`/`Communication`/
    `Comment`/`File` are hash-named, `Email Template`/`Tag` prompt-named,
    `Email Account` field-named, and **`Contact` is named from its full name with a
    numeric suffix on collision**. Contact is the risky one — the frontend routes on it
    (`/contacts/:contactId`) — and it is a guess constrained by usage, not read from
    source. Flagged for review.

14. **`from` and `to` are Python keywords.** `CRM Status Change Log` and `CRM Call Log`
    both have fields with those names. Installed via `Model.add_to_class` so the wire
    name stays exact; access them with `getattr(obj, "from")` or `filter(**{"from": x})`.
    Renaming them would have silently broken any ported query.

15. **Singletons are pinned to a fixed PK string**, not `pk=1` — our PKs are strings.
    `SingletonMixin.load()` is the accessor. Keeps the singleton reachable through the
    same generic endpoint as everything else.

16. **`CRM Territory` and `CRM Sales Hierarchy` keep `lft`/`rgt` as plain columns.**
    `PHASE_2_PERMISSIONS.md` §3 calls for django-treebeard. Phase 1 ports the schema
    faithfully (both are indexed for the range scan) and **leaves the tree behaviour to
    phase 2**, which is where the performance requirement actually bites and where the
    subtree query gets written. Deferring keeps phase 1 mechanical, as its spec asks.
    Phase 2 should decide treebeard-vs-nested-set with the query in front of it.

### Deviations from spec

- Child-table FK rule — decision 11.
- Five unmodelled Link targets — decision 12.
- Tree implementation deferred to phase 2 — decision 16.
- **`CRMDeal.validate_forecasting` takes the flag as a parameter** rather than reading
  `FCRM Settings` itself, so the rule is testable and the caller owns the settings
  lookup. Upstream reads the singleton inline (`crm_deal.py:249`). Phase 3 must call it.
- **SLA lifecycle is a named no-op** (`apply_sla`). Upstream calls it from `before_save`;
  the columns are ported, the arithmetic is phase 5 per `PHASE_5_ASYNC.md` §4.

### Concerns

- **Lifecycle porting is partial and this is the biggest gap in phase 1.** The
  validations that raise are ported verbatim and tested. What is *not* ported:
  `crm_lead.share_with_agent` / `assign_agent` (they create ToDo and DocShare rows on
  owner change), `add_status_change_log`, `crm_deal.update_default_probability` /
  `update_expected_deal_value`, and the whole `convert_to_deal` path. These are real
  behaviour, they live in the two 500-LOC controllers the spec told me to read line by
  line, and a later phase will assume they exist. **Phase 3 or a phase-1 follow-up must
  finish them.**
- **`Contact` naming is a guess** — decision 13. It decides a URL.
- **No lifecycle signal wiring for `_comments` / `_user_tags`.** `_assign` is kept in
  sync with `ToDo`; the other two underscore caches are columns with no writer yet.
  `Comment` and `Tag` exist, so phase 3 can wire them.
- **`crm_products` totals are not computed.** `amount`, `net_amount`, `total`,
  `net_total` are ported as columns; upstream computes them from qty × rate less
  discount. Not wired.
- **The polymorphic child tables have no referential integrity.** `parent` is a string,
  so deleting a lead leaves its product rows orphaned. Frappe has the same property, but
  Frappe also has a `on_trash` cascade that this port does not yet.
- **`FCRM Settings.access_key` is readable by any authenticated user.** That is faithful
  to the source (`Data`, unhidden) but it is an FX-provider API key. If you want it
  restricted, that is a **product decision that diverges from upstream** and needs the
  settings screen changed too — one line in `SENSITIVE_FIELDS` on the model.
- **`CRM Call Log.links`** (a `Table` of Frappe's `Dynamic Link`) is not ported;
  `Dynamic Link` is a platform doctype outside the nine in scope. Upstream uses it to
  attach notes/tasks/leads/deals to a call. Phase 3 will need it.
- **My JSON inspection truncated `options` and I did not notice.** Three wrong `Select`
  field definitions reached the review because of it. A test now covers that class of
  mistake, but it is worth knowing that the schema I transcribed by eye was checked by a
  tool I had also written — and the tool was the thing that was wrong.

### Gate

1. `pytest` — **610 passed, 31 skipped, 0 failed**
2. Migrations — `makemigrations --check` clean; applied to `opencrm`; rebuilt from empty
   on every test run
3. Codex review — ran, 13 findings, acted on above (with the branch caveat recorded)
4. Commit — `6e18bd8`

---

## Phase 2 — PASS   [branch: phase-0-foundation]
Started: 2026-08-14 03:25   Finished: 2026-08-14 04:05   Commit: `<below>`

**Built:** The row-level permission engine — `crm_app/permissions/`. The six-step rule
order for CRM Lead and CRM Deal, CRM Notification's own separate rule, nested-set
maintenance for `CRM Sales Hierarchy`, and a per-request memo so the subtree lookup does
not run per row. Registered through the phase-0 extension points; **no phase-0 code was
edited to make the rules fit** — the only phase-0 changes were two security fixes found
by probing (below).

**Tests:** **666 passing**, 31 skipped. `test_permissions.py` alone is 60 tests.

The full spec §6 matrix is covered, for CRM Lead *and* CRM Deal:

| User | Hierarchy | In tree | Sees | Test |
|---|---|---|---|---|
| Administrator | either | either | all | `test_administrator_sees_everything` |
| System Manager | either | either | all | `test_system_manager_sees_everything` |
| Sales Manager | off | no | all | `test_sales_manager_hierarchy_off_sees_everything` |
| Sales Manager | on | no | all | `test_sales_manager_hierarchy_on_but_not_in_tree_sees_everything` |
| Sales Manager | on | yes | own + subtree + subtree-assigned | `test_sales_manager_in_tree_sees_own_and_subtree` |
| Sales User | off | no | own + directly assigned | `test_sales_user_hierarchy_off_sees_only_own` |
| Sales User | on | yes | own + subtree + subtree-assigned | `test_sales_user_in_tree_sees_own_and_subtree` |

Row 4 is the one worth naming: **a Sales Manager who is not placed in the tree keeps the
legacy see-everything behaviour.** That is deliberate upstream (`org_hierarchy.py:30`),
and it is why the rule order is load-bearing — moving that check below the tree
evaluation would silently narrow access for every unplaced manager.

Other criteria: cancelled ToDos grant nothing; **closed** ToDos still do (the permission
filter excludes only `Cancelled`, unlike the display list); `has_permission` and list
filtering are asserted to agree **row by row, per user**, in both hierarchy modes;
create is permitted for unsaved documents; the subtree lookup is proved not to N+1; and
`fields` / `order_by` / `group_by` / `filters` / `or_filters` are each probed for a
bypass.

### Two security holes I found by probing, before the review

Both were in **phase-0 code**, exposed only once real rules existed.

- **`POST /api/resource/<DocType>` never asked the create hook.** The org-hierarchy rule
  returns `True` for `create`, so leads and deals were unaffected and the gap was
  invisible — but `CRM Notification`'s rule returns **`False`**, and any authenticated
  user could POST a notification addressed to anyone else. Now checked before save.
  Codex independently reported this as **High** on a snapshot taken just before the fix,
  which is a useful confirmation that it was real and not over-caution.

- **Kanban column resolution bypassed the permission layer.** `get_data` enumerated the
  Link target's rows through the plain manager; upstream uses `frappe.get_all`, which
  applies permissions. Grouping deals by `lead` therefore listed every lead's name to a
  user who could see one. Now routed through `base_queryset`.

### Codex findings

Two, on the pre-fix snapshot.

- **High — Notification create not enforced.** Already fixed (above). Confirms it.
- **Medium — list and object rules disagree when `to_user` is blank.** Real, and it
  mirrors upstream (`crm_notification.py:55-56`), but it is **unreachable here**:
  `to_user` is `reqd=1` in the JSON so the column is NOT NULL. Rather than diverge from
  the source by deleting the branch, or leave a latent hole, I pinned the constraint
  that makes it unreachable — `test_to_user_is_not_nullable_which_is_what_makes_the_blank_branch_unreachable`
  fails with an explanatory message if anyone makes the column nullable.
  `test_list_and_object_agree_for_every_real_notification` covers the rows that can
  actually exist.

Codex found **no** `fields` / `order_by` / `group_by` bypass, and confirmed the rule
order and the ToDo-not-`_assign` backing match upstream.

### Decisions made without you

17. **Nested-set rebuild instead of django-treebeard.** `PHASE_2_PERMISSIONS.md` §3
    suggests treebeard. I did not use it: treebeard owns its own columns and expects
    node creation through `add_root`/`add_child`, but our rows arrive through the generic
    `/api/resource/` endpoint with `reports_to` set, and the schema we must match is
    Frappe's `lft`/`rgt`. Adopting treebeard would have meant a second tree
    representation to keep in sync with the one the wire format already fixes. Instead
    `tree.py` recomputes the whole tree on hierarchy writes — O(n) on write, one indexed
    range scan on read. Hierarchies are one row per user and change rarely; list queries
    run constantly, so the cost is deliberately on the write side. **This is a deviation
    from the spec and the reasoning should be checked.**

18. **The subtree query is one cached bounds lookup plus one subquery.** Upstream's
    range self-join has no clean correlated-subquery form in the ORM. The manager's
    `(lft, rgt)` is fetched once per request and memoised, then used to build a single
    `IN (SELECT ...)`. The memo key includes the user — `test_the_cache_does_not_leak_between_users`
    exists because a memo keyed without it would hand one user another's subtree.

19. **`lead_owner`, not `owner`, is the access column** — and this surprised me. A Sales
    User who creates a lead and leaves `lead_owner` blank **cannot see it afterwards**.
    That is upstream's rule (`org_hierarchy.py:34,54`); upstream's UI always sets
    `lead_owner`, which is why it rarely surfaces there. Two phase-1 tests had to be
    corrected because their setup was unrealistic. **Any phase-3 endpoint that creates a
    lead or deal must set the owner field**, or the record vanishes for its author —
    `test_a_lead_without_a_lead_owner_is_hidden_from_its_creator` pins it down.

### Concerns

- **The hierarchy rebuild is not concurrency-safe.** Two simultaneous writes to
  `CRM Sales Hierarchy` could interleave and produce inconsistent bounds. Writes are
  rare and admin-only, but this wants a lock or a serialised task before production.
- **`_get_object` distinguishes 403 from 404**, so a user can tell whether a record they
  cannot see exists. Upstream behaves the same way, so this is faithful, but it is an
  existence oracle and worth a deliberate decision.
- **Only the three upstream doctypes have row rules.** Everything else — organizations,
  tasks, notes, call logs, contacts — is visible to every authenticated user, exactly as
  upstream. That is a much larger surface than it sounds like, and it is worth
  confirming it is what you want rather than inheriting it by default.
- **`has_permission` runs one query per object check.** Fine for a detail route; a
  phase-3 bulk operation that checks N items will issue N queries. `delete_bulk_docs`
  is specced to permission-check per item, so that path needs batching.
