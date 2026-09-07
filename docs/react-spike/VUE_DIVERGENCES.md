# Where the React client differs from the Vue one

**Every place `frontend-react/` behaves differently from `frontend/`, and why.** The backend
port keeps `UPSTREAM_BUGS_PHASE_*.md` for the same reason and it earned its place there: when
something behaves oddly, the first question is *"is that a port bug, or did we mean that?"*
and this file is where the answer lives.

**Numbering is one sequence.** Continue from the highest number here, never from the number a
runbook happens to quote.

## What belongs here

* **A deliberate behaviour change.** React does something the Vue client did not, and we
  chose it. Record what a user would notice.
* **A Vue bug we did not reproduce.** State how you know it is a bug, and check nothing reads
  the behaviour before diverging.
* **A Vue bug we *did* reproduce**, because a user sees the result and matching it matters
  more than fixing it.
* **A gap** — Vue does something we have not built yet. Not a divergence forever, but it is
  one today, and an unrecorded gap reads as a bug to the next person.

## What does not belong here

Per-run narrative. The runs' own reports (`CONVERSION_RUN_<N>.md`) carry what happened, what
Codex raised, and where the code was weak. **This file carries only what is still true**, so
it can be read on its own without reading every report that preceded it.

> **A note on where these come from.** Entries 1–4 were raised by Codex during run 1 and
> recorded only inside `CONVERSION_RUN_1.md` §5. That is a per-run document, so by run 3 they
> would have been invisible without re-reading an old report. Lifted here so they survive.

---

## 1. ~~A named saved view renders with default parameters~~ — CLOSED in run 2

Both halves landed: `frontend-react/src/list/useViews.ts` resolves the view client-side and
sends its stored parameters, and the picker creates and deletes `CRM View Settings` rows.
Asserted in the harness by loading a saved view's URL cold, with no `filters=` in it, and
getting the filtered rows back.

Kept rather than deleted because the entry above it explains what "closed" means, and a
reader who remembers this gap needs to find that it is gone.

## 2. A revisited filter state can serve from cache

**Where:** `frontend-react/src/api/hooks.ts` — `staleTime: 30_000`

Vue's `createResource` refetched on every parameter change. TanStack Query serves a cached
result for 30 seconds when the same key comes back — so filtering to X, back to Y, then to X
again inside half a minute shows the first X response rather than a fresh one.

**Us:** *Diverge, deliberately.* It is what the library is for, mutations invalidate, and the
window is short. Recorded because it **is** a user-visible behaviour change and the next
person should not find it by surprise and "fix" it.

**If it ever bites:** the symptom is stale rows after someone else edits a record, within 30
seconds, on a filter you have already visited. That is the trade, not a bug.

## 3. `keepPreviousData` is on `useGetData` only

**Where:** `frontend-react/src/api/hooks.ts` — not on `useDocList` or `useMethod`

Changing parameters on those two blanks the list to a loading state instead of holding the
previous rows.

**Us:** *Gap, currently inert.* No caller of either changes its params today, so nothing shows
it. **It becomes a real defect the first time one does** — which is worth knowing before the
next ninety call sites get written, rather than after.

## 4. A failed token refresh redirects; Vue only cleared and threw

**Where:** `frontend-react/src/api/client.ts` vs `frontend/src/auth/jwtRequest.js`

Vue cleared the tokens and let the error propagate; its router guard then bounced the user to
Login on the next navigation. React redirects to `/login` from the interceptor.

**Us:** *Diverge, deliberately.* Same user-visible outcome by a shorter path — there is no
equivalent always-mounted guard here. Recorded because the *mechanism* differs, and anyone
tracing "why did I end up at Login" should find this rather than reverse-engineer it.

## 5. Kanban cards move between columns but cannot be reordered within one

**Where:** `frontend-react/src/list/KanbanBoard.tsx` vs `frontend/src/components/Kanban/KanbanView.vue`

Run 3 added cross-column drag: dropping a card writes the board's `column_field` on that
record, which is what a user means by moving a card.

**Still a gap:** the Vue board also *reorders* cards inside a column and persists that order
into `CRM View Settings`, which the server honours through `get_records_based_on_order`
(`doc.py:531`). React does not.

**Us:** *Partial.* The useful half is done and stands alone; the ordering half is cosmetic
until someone asks for it.

## 6. Currency is formatted client-side from the row's own currency field

**Where:** `frontend-react/src/list/Cell.tsx`

Frappe formats currency server-side with per-user precision settings. React reads the row's
`currency` and falls back to a plain number.

**Us:** *Diverge, knowingly incomplete.* Better than the hardcoded USD it replaced, and wrong
for any user whose precision settings differ from the default. Fix it when a real user has
non-default precision, not before.

## 7. There is no email composer, because the backend does not serve the send

**Where:** `frontend/src/components/CommunicationArea.vue:216` — `call('frappe.core.doctype.communication.email.make', …)`

That dotted path is **not in this backend's whitelist**. Checked against
`frappe_core.whitelist.all_methods()` in run 3, not inferred: the registry has
`crm.api.settings.create_email_account` and `crm.api.contact.search_emails`, and nothing that
sends a message.

**Us:** *Blocked, not deferred.* A composer could be built and would 404 on the Send button,
which is worse than its absence. Run 2's report made "build the email composer" the condition
on run 3; that condition **cannot be met without a backend change**, and `backend/` is fixed
in this worktree.

**To unblock:** whitelist a send endpoint. Everything else the composer needs — the record
context, the recipient list, the activity feed it writes into — already exists.

## 8. Attachments can be listed and deleted, but not uploaded

**Where:** `frontend/src/components/Activities/AttachmentArea.vue`, `composables/useAttachments.js`

`crm.api.delete_attachment` and `crm.api.get_file_uploader_defaults` are whitelisted.
**Frappe's `upload_file` is not**, and `config/urls.py` routes only `/api/resource/*` and
`/api/method/*` — there is no upload route at all.

**Us:** *Blocked, same shape as entry 7.* The Attachments tab lists what
`get_activities` returns and offers no way to add one.

**To unblock:** a multipart upload route plus a `File` doctype write path.

## 9. ~~Sort and filter options come from `fields`~~ — CLOSED in run 3

`ViewControls` calls `crm.api.doc.sort_options` and `crm.api.doc.get_filterable_fields`
now, which are the curated subsets Vue has always used. Columns still come from the
payload, because the column set *is* the payload's.

**One thing found doing it, still true:** both endpoints can return the same `fieldname`
twice — `name` appears in the standard fields and again in the doctype's own, and the
server does not merge them. `useFieldOptions.ts` dedupes, first occurrence winning.
Without it React warns about duplicate keys and may drop one.

**Still open from that entry:** `get_quick_filters` and `get_group_by_fields` are served and
unused. Quick filters are a row of one-click filters above the list that React has no
equivalent of at all; group_by uses a hardcoded `owner` rather than offering the fields the
endpoint returns.

## 10. ~~Comments are plain text; the Vue client writes HTML~~ — CLOSED in run 5

**Where:** `frontend-react/src/record/CommentBox.tsx`, `ActivityTimeline.tsx`

`add_comment` stores `content` verbatim. React used to post plain text from a textarea and
render every comment as text, never as HTML, because a comment written in the Vue client is
HTML authored by another user and `dangerouslySetInnerHTML` on it is stored XSS.

**Closed the way the entry said it had to be closed** — a sanitiser *plus* the editor,
never an unescape. `components/RichText.tsx` holds both halves; `RichTextView` runs
DOMPurify on every render and there is no unsanitised path in that file on purpose.

---

## 11. Settings rows are edited through one generic form, not a per-doctype editor

**Where:** `frontend-react/src/pages/settings/DoctypeList.tsx`

Six Vue settings screens have a hand-written editor each — `EditEmailTemplate.vue` is 246
lines, and `EmailTemplate/`, `Sla/`, `Hierarchy/`, `LeadSyncing/`, `AssignmentRules/` and
`EmailAccountList.vue` come to roughly 1,400 lines between them, most of it the same
list-and-dialog. `DoctypeListSettings` is one component behind all six, and editing goes
through the same field list as creating.

**Us:** *Diverge.* The shared form is the right trade for six screens that are the same
shape, and it is why editing arrived on all of them in one change rather than six.

**What is genuinely lost**, and worth knowing before someone calls it a bug:

* ~~**The email template body is a plain textarea**~~ — **closed in run 6.** It was the one
  case where the shared form was not merely plainer but *wrong*: `response` is HTML the
  composer inserts verbatim, so a textarea produced plain-text emails. Email templates now
  have their own screen (`settings/EmailTemplates.tsx`) with the rich-text editor, the
  `use_html` toggle and both body columns.

  **Correction to this entry as first written:** it claimed Vue offers "`{{ doc.field }}`
  variable insertion". It does not — `EditEmailTemplate.vue` has no picker of any kind. You
  type `{{ field }}` by hand, and it shows examples as placeholder text. Ours does the same
  with a hint line. The gap that was recorded here was half imagined, which is its own
  lesson: a divergence written from a glance at a screenshot is a guess.
* **No per-doctype validation before save.** The server still validates; the difference is
  that the message arrives as a toast after the round trip rather than beside the field.
* **`name` is read-only once a row exists.** Renaming a document is a separate operation in
  Frappe and this form does not do it.
