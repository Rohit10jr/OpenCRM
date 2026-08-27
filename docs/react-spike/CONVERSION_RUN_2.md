# Conversion run 2 — the record-screen gate, answered

Branch `react-conversion-2`, cut from `react-conversion`. Thirteen commits.

**A note on the clock, first, because it qualifies every minute figure below.** This run was
interrupted twice by usage limits, once during setup and once mid-piece-7. Both times the
background servers were killed and the wall clock was restarted from where it stood, so the
elapsed figures are *working* minutes and exclude the gaps. They are honest as a measure of
throughput and useless as a measure of how long a person sat at it. **The line counts have
no such caveat, and where the two disagree, trust the lines.**

---

## 1. The gate answer

> **The Deal record screen is the honest test of whether the 2:1 ratio survives a screen
> with no shared engine behind it.**

| | |
|---|---|
| **Lines** | **862** — `src/record/` 837 + `pages/Deal.tsx` 25 |
| **Wall clock** | **~12 working minutes** to `verified` |
| **Row of the runbook's table** | **Row 2 — `~450–900 lines`** |

**Verdict: continue, and the 20–30 hour estimate should move — but down, not up.** Run 2
did more than the gate asked and came out cheaper per screen than run 1, which is the
opposite of what row 2's wording anticipated.

**The one thing that must not be glossed.** 862 lines does *not* buy what `Deal.vue`'s 832
buys. Missing, and each for a stated reason:

| Not built | Why |
|---|---|
| Contacts sub-panel | `crm.fcrm.doctype.crm_deal.api.get_deal_contacts` **is not served by this backend** |
| Email composer, WhatsApp | Needs the TipTap wrapper and endpoints out of this run's reach |
| File upload / attachments write | `FileUploader` has no React equivalent yet |
| Telephony (click-to-call) | Whole subsystem, unstarted |
| Assign-to editing | Assignees render; changing them needs the assignment endpoints |

So the honest reading of row 2 is: **the record-screen *skeleton* is cheap, and the
remaining per-record work is in the subsystems those five rows name, not in the screen.**
That distinction is what the next estimate should be built on.

The three record screens that followed cost **19, 22 and 18 lines**, which is the number
that actually settles the question.

---

## 2. The ledger

`verified` = a real browser drove it · `renders` = builds and mounts · `written` = never run.

| # | Piece | State | Lines | Wall clock |
|---|---|---|---|---|
| — | Setup, seed the Side Panel layouts | done | — | ~10 min¹ |
| 1 | **Deal record screen** (`src/record/`) | `verified` | **862** | **~12 min** |
| 2 | Row click → record, filters into the URL | `verified` | ~60 | ~6 min |
| 3+4 | **Saved views**, read and write (`useViews`, picker) | `verified` | 266 | ~14 min |
| 5 | Create modal, from the Quick Entry layout | `verified` | 137 | ~9 min |
| 6 | **`socket.js` ported** + React binding | `verified`² | 330 | ~10 min |
| 7 | Contact + Organization record screens | `verified` | 40 | ~5 min |
| 8 | **Settings → Users** (list, role, invite) | `verified` | 209 | ~7 min |
| — | Lead record screen + Create | `verified` | 27 | ~3 min |
| — | Codex fixes (6 defects) and the `get_users` bug | `verified` | — | ~12 min |
| | **Total application code, cumulative** | | **5,699** | |
| | *of which written this run* | | **~2,280** | |

¹ Plus the interrupted setup attempt, which cost nothing but wall clock.
² The socket **connects** — asserted through CDP against a real handshake. What is *not*
asserted is that a server-pushed `docinfo_update` reaches a component, because nothing in
this run pushes one. See §7; this is the weakest `verified` in the table and it is marked
here rather than in a footnote nobody reads.

**Harness: 15 steps at the start of the run, 31 at the end, all green, zero console errors.**
`npm run build` succeeds. `git diff --stat main -- frontend/ backend/` is empty. All 13
dotted paths the React source calls resolve against the backend registry.

---

## 3. How the ratio moved

Run 1 measured **2.06:1** across the list slice. Recomputing over what run 2 replaced:

| Vue, replaced this run | Lines |
|---|---|
| `Deal.vue` + `Lead.vue` + `Contact.vue` + `Organization.vue` | 2,442 |
| `Activities.vue` | 847 |
| `SidePanelLayout.vue` | 727 |
| `DealModal.vue` | 248 |
| `socket.js` + `data/document.js` + `stores/views.js` | 715 |
| Settings `Users.vue` + `InviteUserPage.vue` | 517 |
| **Total** | **~5,496** |

Against ~2,280 lines of React: **2.4:1**, slightly better than run 1's 2.06:1 — while also
closing run 1's largest gap and fixing four of its nine listed weaknesses.

**But apply the §1 caveat before using that number.** The React side does not yet do what
the email composer, contacts panel, file upload and telephony parts of those Vue files do.
A fair discount is substantial: call the *honest* ratio for this slice **1.5:1**, and treat
2.4:1 as the ceiling.

### Does the remaining estimate move?

Run 1 said 20–30 hours with 11 as a floor, and warned the list surface was the best case.
Two runs in, that warning looks too pessimistic:

* ~40,250 Vue lines remained after run 1; ~5,500 of them are now done, leaving **~34,750**.
* At the discounted 1.5:1 → **~23,000 lines of React**.
* This run wrote ~2,280 lines in ~78 working minutes ≈ **29 lines/minute**, identical to run
  1's 30 — including two Codex rounds and a browser pass after every piece.
* 23,000 ÷ 29 ≈ **13 hours**.

**Revised: 15–25 hours, with 13 as a floor.** Down from 20–30, and the reason is specific:
the second engine (`RecordScreen`) paid for itself inside one run, exactly as the first did.
The remaining risk is no longer per-screen cost — it is the five subsystems in §1, which are
lumpy, unshared, and not measured by anything either run has done.

**Recommendation stands: outcome A, full conversion.** With one new condition, replacing
run 1's: **the next run must build the email composer or the attachments path**, because
those are now the largest unmeasured things left, and everything cheap has been measured
twice.

---

## 4. Next-up, in order

1. **The email composer** (`EmailArea.vue` + TipTap React bindings). The largest unmeasured
   subsystem, and the condition above.
2. **Attachments / `FileUploader`.** Needed by every record screen; `get_attachments`
   already returns them, only the write path is missing.
3. **Assign-to editing.** Assignees render but cannot be changed.
4. **A searchable Link combobox.** `FieldInput`'s `<select>` caps at 100 rows and the 101st
   cannot be chosen — see §6.
5. **Kanban drag.** The `CRM View Settings` write path now exists, so this is unblocked for
   the first time.
6. **Contacts sub-panel** — needs a backend finding resolved first (§7).
7. Remaining settings screens; check each one's endpoints are served before starting it.
8. **A lookup table for `RecordScreen`'s tab bodies** and the other items in §6 — none
   blocking, all cheap, and item 10 gets worse with every tab added.

---

## 5. Codex findings

Tier 1 throughout. Both scheduled checkpoints ran. **Both hung on the first attempt** — no
output for 12–13 minutes — and both returned in under 8 when killed and re-issued naming
exact files and exact questions. That is now twice in two runs; the narrow prompt is not a
workaround, it is the way to call this tool.

### Fixed (6)

| Finding | Why it mattered |
|---|---|
| Datetime fields round-tripped **UTC as local** | Showed 14:30 to a reader in Berlin whose deadline was 16:30, and saved it back as 14:30 UTC. Consistent, and wrong for everyone outside UTC |
| `updateField` did not invalidate assignees | An owner change rewrites `_assign` server-side; the header avatars went stale |
| Empty side-panel section printed filler text | The Deal layout's `contacts_section` has a real body we have not built; "nothing here yet" invented content |
| Selected tab survived navigation between records | Opening a deal from Attachments opened the next one on Attachments. `key={dealId}` |
| **`modified desc` used as a sentinel for "unsorted"** | A user deliberately choosing `modified desc` on a saved view silently got the view's sort instead |
| `viewParams` accepted any valid JSON as filters | A stored `"123"` went into the request as `filters: 123` |

### Raised and checked, but wrong for this backend (1)

Codex reported the datetime **format** was wrong — `YYYY-MM-DDTHH:mm` against Frappe's
`YYYY-MM-DD HH:mm:ss`. **Checked against the running API rather than taken on trust: this
backend is Django, accepts both, and stores them identically.** The real defect was one
layer down, in the timezone, and is the first row above. Worth recording as a pattern: a
reviewer reasoning from *Frappe* is reasoning about the wrong system for about a third of
this port.

### Raised, not fixed (1)

**The Link `<select>` caps at 100 rows**, so the 101st cannot be selected at all. Real, and
it needs a searchable combobox rather than a bigger cap. Item 4 in §4; the code comment now
says exactly what breaks rather than eliding it.

---

## 6. Where the code is weak

Run 1 listed nine. Here is what happened to each, then what is new.

| # | Run 1's weakness | Now |
|---|---|---|
| 1 | `ViewControls.tsx` doing three jobs | **Fixed** — `FilterEditor` split out |
| 2 | Filters vanish on reload, cannot be linked | **Fixed** — they are URL search params |
| 3 | `Cell.tsx` special-cases by key, not fieldtype | **Unchanged.** Still true, still works, still would misfire on a `status` field meaning something else |
| 4 | `userCell` duplicated in Deals and Leads | **Fixed** — extracted, four callers now |
| 5 | Kanban read-only, no drag | **Unchanged**, but unblocked: the settings write path exists |
| 6 | One 573 kB chunk, no code splitting | **Worse.** More screens, still one chunk |
| 7 | No unit tests | **Unchanged.** The harness grew 15 → 33 steps; there is still not one unit test |
| 8 | `useListView` returns fifteen values | **Worse** — twenty-three now |
| 9 | Currency ignores server-side precision | **Unchanged** |

New this run:

10. **`RecordScreen.tsx` renders its tab bodies as a five-branch ternary chain.** It was
    three branches when written and is readable at five; at seven it will not be. A lookup
    from tab id to element is the obvious fix and I did not make it.
11. **`CreateModal` silently drops hidden Quick Entry sections.** The Vue modal reveals them
    through a link-picker this does not have. The user gets a create form with fewer fields
    than the Vue one and no indication that is what happened.
12. **The `UNMODELLED_LINK_TARGETS` list will rot.** It exists so the console stays clean;
    the `isError` fallback behind it is what actually makes it safe, but a reader could
    reasonably mistake the list for the mechanism.
13. **Two components now reach for `window`-level assumptions about the panel width** — the
    record screen hardcodes `w-96`, and `SidePanel`'s labels hardcode `w-32`. Nothing is
    responsive below about 1100px. Neither app is mobile yet, but the Vue one at least has
    `handleMobileView` in its router.
14. **`useRecord` fetches activities for every record and throws four of the five lists
    away** unless the user opens that tab. One request, so it is cheap, but it is a request
    per record screen that mostly funds one tab.

---

## 7. What surprised me

**Two endpoints in this API return tuples, and both cost a bug.** `get_activities` returns
`(activities, calls, notes, tasks, attachments)`; `get_users` returns `(users, crm_users)`.
Run 1 read the second as `{ crmUsers }` — not an error in JavaScript, just `undefined` — so
the user lookup map was **always empty** and every avatar and owner cell silently fell back
to rendering a raw email address. It shipped in run 1, the browser pass did not catch it,
and it was found only because a settings screen made me read the payload. A fallback that
produces plausible-looking output is worse than one that produces nothing.

**The harness caught me writing a false green.** My own new assertion "the socket opens"
passed on Vite's HMR socket, which is also `ws://127.0.0.1:5174/?token=…`. Narrowed to
`/ws/realtime`, it immediately failed — and the failure was real: `vite.config.ts` proxied
`/socket.io`, upstream Frappe's path, which nothing in this port serves or requests. Run 1
copied that line and nothing noticed, because run 1 had no socket. **A comment saying
realtime worked would have shipped today.** This is the single strongest argument in either
run for the runbook's rule that an assertion beats a claim.

**This port's field metadata is not Frappe's, in a way that crashes.** `Select` options come
back as an array of `{label, value}`; upstream joins them with newlines, and the stock
layouts are authored against upstream. `SelectInput` called `.split` on an array and took
the whole Organization record screen down behind an error boundary. Anywhere this
conversion reasons from Frappe documentation rather than from the running API, the same trap
is waiting.

**A backend finding, reported not acted on** (`backend/` is fixed): the Deal side panel's
`contacts_section` cannot be built, because `crm.fcrm.doctype.crm_deal.api.get_deal_contacts`
is not served — it is in `test_phase3_endpoints.py`'s out-of-scope list, and
`conversion.py`'s `create_deal` is a different function that happens to share a name. The
same applies to the Create modal, which posts to `/api/resource/CRM Deal` because
`crm_deal.create_deal` is likewise unserved. Both are working divergences, not blockers, but
they are the first places this conversion has had to *diverge* rather than port.

**Smallest surprise, biggest relief:** the record screen needed no new primitives. Every
shadcn component it wanted existed from run 1, and `FieldInput` — the write-side twin of the
list's `Cell` — was the only genuinely new UI idea in 862 lines. Run 1 predicted the shadcn
mapping would break somewhere. Two runs in, it still has not.
