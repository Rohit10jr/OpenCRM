# Conversion run 5 — breadth, and a reversed policy

Branch `react-conversion-5`, cut from `react-conversion-4`. **23 commits, ~7,600 lines
across 68 files.** The React client went from 5,500 lines to **13,144**, against the Vue
app's 52,837.

Two instructions shaped this run, and both were the owner's:

1. **"Ignore the testing for now."** No manual verification loop, no browser harness. The
   only gate was `tsc --noEmit` plus `npm run build`, both green at every commit.
2. **"If something is missing in our backend, ignore it and make progress anyway — but
   raise those flags in md files."** Then, when asked: *breadth over depth*, and *call the
   real path and fail visibly* rather than mock or disable.

**Nothing in this run is `verified`. Everything is `written`.** That is not hedging: it is
the accurate word. The code compiles and builds; no screen in it has been clicked. Runs 1–4
used `verified` to mean "opened in a browser and exercised", and stretching it here would
make the earlier runs' claims worthless too.

`frontend/` and `backend/` are byte-identical to `main`. The 33 unit tests from run 4 still
pass.

---

## The policy reversal, and why it was right

Runs 1–4 refused to build UI for an endpoint the backend does not serve, on the reasoning
that a Send button which 404s is worse than no Send button. The owner reversed that.

It turned out to matter far less than expected, because **the premise was wrong**. Dumping
`frappe_core.whitelist.all_methods()` in the first twenty minutes showed roughly a hundred
endpoints served, including every subsystem runs 2 and 3 had written off as "blocked,
unmeasured": telephony, WhatsApp, ERPNext, the dashboard, notifications, the exchange rate.
Nobody had looked. Two runs planned around an assumption that one command falsified.

So most of this run is not building against gaps at all — it is building against endpoints
that were sitting there. The genuinely missing ones are down to a handful, all in
`BACKEND_GAPS.md`, and the components that need them render a banner naming the exact dotted
path before you can click the thing that fails.

---

## What landed

### New screens

| Screen | Notes |
|---|---|
| **16 settings screens** + a nested settings shell | Six go through one `DoctypeListSettings` |
| **Dashboard** | Metadata-driven tiles; plain-SVG donut and bars, no charting library |
| **Notifications** | Live, with an unread badge in the sidebar |
| **Data import** | History works; upload blocked on `upload_file` |
| **Welcome / onboarding** | Checklist derived from real state, not a stored flag |
| **Live call panel** | Exotel, socket-driven, mounted app-wide |
| **Call log detail** | Dialog, not a route — a call log has no record screen |

### Record screen

Emails, comments, calls, tasks, notes, attachments, WhatsApp, status change with the
lost-reason dialog, lead conversion, assignment, likes, linked documents, the deal contacts
section, the SLA clock, and a contact's linked deals.

Tasks and notes can be created, edited and deleted from the record they belong to. Emails
render as cards with sanitised bodies and attachments. Calls show direction, duration,
recording and the note.

### List engine

Quick filters and their picker, group-by, the full saved-view menu (rename, duplicate, pin,
publish, set default), kanban board settings, and a Columns menu that is a real write with
add, remove and reset.

### Everything else

TipTap with DOMPurify on every render; a responsive layout with no parallel mobile tree;
code splitting that took the entry chunk from 1,100 kB to 669 kB.

---

## Four bugs found by asking the same question

The most productive thing in this run was not writing screens. It was repeatedly asking:
**what does the API actually return, and what does the client actually branch on?**

1. **Emails rendered as the word "communication".** `get_activities` returns them as
   `activity_type: "communication"` with the whole message in `data` (`activities.py:294`).
   The timeline had no branch for that shape and fell through to a default that prints the
   type. Every email on every deal, showing as one wrong word.
2. **`added` entries rendered as the word "added"**, same cause. And **grouped versions were
   silently dropped**: consecutive changes by one person collapse server-side into one entry
   with the rest on `other_versions` (`activities.py:322`), and the client rendered the first
   and discarded the rest. A record's history was incomplete and looked complete.
3. **Half the fieldtypes fell through to a single-line text box.** Every Django `TextField`
   maps to `Small Text` (`frappe_core/metadata.py:181`) — descriptions, addresses, notes. A
   `JSON` column rendered `[object Object]` in every row.
4. **A docstring lied.** `EmailComposer` claimed `search_emails` was wired for recipients. It
   was not; the endpoint had no caller anywhere.

That last one prompted the exhaustive version: every dotted path the Vue client mentions,
diffed against every path this backend whitelists. It found two more gaps nobody had reached
— the deal-contact *writes*, and `create_lead_from_call_log`. `BACKEND_GAPS.md` is now the
full list rather than the list of what happened to be built.

**The lesson worth keeping:** a screen-by-screen pass finds what is in front of you. Diffing
the contracts finds what nobody has walked up to yet. The second is cheap and was left until
hour four.

---

## Review

**Tier 1, Codex.** The first attempt wandered into the backend, ignored the files it was
given, and was killed past CLAUDE.md's ten-minute bar. The retry — four named files,
searching explicitly forbidden, a max of five findings — came back in about a minute with
two, both in `CallPanel`, both real, both fixed in `ab09589`.

Both were the same missing idea: the panel had no notion of "this is a different call". A
call that has ended stays on screen until dismissed and the next one does not wait, so the
second call inherited the first one's contact and could finish showing the first one's
duration. `CallSid` distinguishes them now.

The narrower prompt is the transferable part. Codex given a directory explores it; Codex
given four paths and told not to search reads them.

---

## What is deliberately not here

Named so nobody has to rediscover them:

* **A parallel mobile tree.** Vue has `MobileLayout`, `MobileSidebar`, `MobileAppHeader` and
  four `Mobile*` pages beside the four they mirror. Breakpoints do it in one tree; four
  screens to keep in step is how they drift apart.
* **Column reordering and per-column width.** Both stored, both real, both their own work.
* **Twilio's browser softphone.** Not a backend gap — an in-browser WebRTC dialer needing
  `@twilio/voice-sdk`. `BACKEND_GAPS.md` §8.
* **Dragging the call panel around**, and a custom audio player with playback speed. The
  browser's own player does the part that matters.
* **`PersonaForm.vue`** — a survey that writes one boolean.
* **The layout editors** (`FieldLayoutEditor`, `SidePanelLayoutEditor`). Admin tooling for
  rearranging the metadata that drives every other screen.
* **Form scripts.** `get_data` returns `form_script` and `list_script`, and the Vue client
  executes them. Running server-supplied JavaScript is a decision, not an oversight — it
  should be made deliberately by someone, not inherited by a port.
* **Nested AND/OR filter groups** (`ConditionsFilter/`).

---

## Next up, in order

1. **Click every screen.** This is the whole of the next session and it is not optional —
   twenty-three commits of unverified UI is exactly the debt this project's rules exist to
   prevent. Nothing below matters until it is done.
2. **Whitelist `convert_to_deal`.** `conversion.py:263` is implemented and complete; one
   decorator turns a 404 into a working button. Still the cheapest item on the list.
3. **Decide about email send and file upload.** They gate the two most-used things in a CRM,
   and every other part of both features is built and waiting.
4. Column reordering; the email template's rich-text body and its variable picker.

---

## Files to read, in order

1. `docs/react-spike/BACKEND_GAPS.md` — what is missing, why, and what to do about it
2. `docs/react-spike/VUE_DIVERGENCES.md` — where React deliberately differs from Vue
3. `frontend-react/src/record/RecordScreen.tsx` — the busiest file, and how tabs compose
4. `frontend-react/src/list/ViewControls.tsx` and its four neighbours — the list toolbar
5. `frontend-react/src/telephony/callStatus.ts` — the one pure function worth reading twice
