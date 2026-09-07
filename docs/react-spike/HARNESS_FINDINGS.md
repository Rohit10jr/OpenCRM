# What broke when the React client was actually run

**Branch `react-conversion-6`.** The first time run 5's 23 commits met a real browser and a
real Django backend.

Two tools, both new here, both permanent:

| Command | What it does | Needs servers |
|---|---|---|
| `npm run check:api` | Every dotted path in `src/` vs. the backend's whitelist | no — ~1 second |
| `npm test` | 48 unit tests over the pure functions | no |
| `npm run verify` | 67 browser steps against the real API | yes |

**Final state: 67 steps green, 0 problems, 1 known gap.** Everything below is what it took
to get there.

---

## Part 1 — Frontend bugs, found and fixed

### 1. The Call button did not exist, anywhere, silently

**Where:** `record/CallButton.tsx:29`, `pages/settings/Telephony.tsx:33`

**How it broke:** the client called `crm.api.is_call_integration_enabled`. The served path
— and the one the Vue client uses — is `crm.integrations.api.is_call_integration_enabled`.

**Why nobody noticed.** Three things lined up:

* `tsc` passes. It is a string.
* The query sets `retry: false`, so React Query fails once and stays quiet.
* `CallButton` renders nothing unless the server says an integration is enabled — and a
  404 reads as *not enabled*.

So the button hid itself on every record, the Telephony settings screen agreed with it, and
nothing anywhere said why. **Telephony looked unimplemented and was one typo from working.**

**Fixed**, and `npm run check:api` now makes this class of bug impossible to ship quietly.

### 2. Creating a task or note refreshed nothing

**Where:** `record/LinkedRecords.tsx`

**How it broke:** after a create, edit or delete it invalidated `keys.doc.all` — that is
`['doc']`. The rows arrive inside the record's `get_activities` payload, which lives under
`['activities', name]`.

**Why:** the two key spaces never intersect. The mutation succeeded on the server every
time; the tab just never re-fetched. **Every write looked like it had silently failed** —
you would only see your task after reloading the page by hand.

The harness caught it because its task step reloads before asserting. Without that reload
it would have passed on a feature that does not work.

**Fixed:** invalidate `['activities', parentName]`.

---

## Part 2 — Backend gaps, confirmed against the running server

`npm run check:api` compares all 64 dotted paths the client calls against the 102 the
backend serves. **Four are missing, and all four were already in `BACKEND_GAPS.md`** — no
new ones, and no phantom ones.

| Path | Screen | Status |
|---|---|---|
| `frappe.core.doctype.communication.email.make` | Email composer, Send | §1 — no send endpoint exists |
| `upload_file` | Attachments, Attach | §2 — no multipart route at all |
| `crm.fcrm.doctype.crm_deal.api.get_deal_contacts` | Deal side panel | §3 — reads *and* writes missing |
| `crm.fcrm.doctype.crm_lead.crm_lead.convert_to_deal` | Lead → Convert | §5 — implemented, never whitelisted |

Only one of them fires during a normal run. The browser confirms it with the server's own
words:

```
404 /api/method/crm.fcrm.doctype.crm_deal.api.get_deal_contacts
    why: frappe.exceptions.DoesNotExistError:
         Method crm.fcrm.doctype.crm_deal.api.get_deal_contacts not found
    during: the record shows its side panel fields; the activity timeline renders;
            a comment posts and appears in the timeline; the Emails tab; …
```

The others need a click to fire, which is the run-5 policy working as designed: the banner
names the path before you reach the button.

**Everything else the client calls is served.** Telephony, WhatsApp, ERPNext, dashboard,
notifications, exchange rate — all confirmed live, not assumed.

### One transient worth recording

`404 /api/resource/FCRM Settings/FCRM Settings` appeared once, during `/settings/brand`,
and never again across five later runs. `FCRM Settings` is a Frappe **Single** — one
document named after its doctype — and the likeliest reading is that the row did not exist
until something created it on first access. **Not reproduced, not diagnosed.** Recorded
because a 404 that fixes itself is worth knowing about before someone meets it on a fresh
database.

---

## Part 3 — Harness bugs, and why they are listed separately

Six of the new steps failed on their first run. **Three were the harness's fault, not the
product's**, and that distinction is the whole difficulty of this kind of testing: a
failing step means the app is broken *or* the script is wrong, and a harness that cannot
tell them apart is worse than none, because it spends your morning on its own typos.

| Symptom | Actually |
|---|---|
| "no Emails tab" | The tab strip waits on `get_activities`; the step only waited for the URL |
| "the task dialog has no text input" | The dialog was probed before its Quick Entry layout landed |
| `title: This field is required` | The step set `input.value`; `FieldInput` commits on **blur**, so the draft never saw it |
| Three tab steps failing at once | They chained — one failure left a dialog open and took the next two down |
| Assignment intermittently failing | The picker's 5s bound; run 5 added queries to a record open |
| Dashboard "0 lines" then fine | The step measured `document.body` too early and **passed on zero** |
| `website: no more than 280 characters` | The step *appended* a stamp each run instead of replacing it, and after enough runs the field overflowed — the server rejecting data only the harness had ever written |

The dashboard one is the sharpest. The step counted content and reported success on an
empty page — the exact failure this harness exists to catch, committed by the harness. It
asserts on `<main>` now and fails loudly if a screen fetches cleanly and renders nothing.

The `website` one is the most instructive, because it was a **time bomb the harness itself
planted**. `click({ clickCount: 3 })` did not reliably select the whole value, so each run
added another `verify-NNNNN` rather than replacing the last, and it passed for as long as
the field still fit. Nothing about the failure pointed at the harness — the message was a
server validation error on a real field, and it was reproducible. **A step that writes to a
shared record has to leave it the size it found it**, which is the same rule as the
bulk-delete step's "a destructive step has to bring its own data", learned twice.

---

## Part 4 — What the harness now proves

**67 steps.** The 28 from runs 1–3 still pass unchanged, which is itself the answer to
"did run 5 break anything": no.

New coverage:

* **15 settings screens** render their own content, not just the shared nav
* **Dashboard** renders tiles; **notifications** render
* **Emails / Calls / Tasks / Notes** tabs — and a task **round-trips**: created on a deal,
  survives a reload, still attached to that deal
* **Adding, reordering *and resizing* a column persists across a reload** — proving all three are writes to
  the view and not component state
* Kanban board settings, quick-filter picker, organization related lists, call-log detail,
  data import, welcome
* **The sidebar is off-screen at 640px and slides in on the menu button** — the responsive
  layout, checked by geometry rather than by class name

### What it still does not prove

Being explicit, because "67 green" invites over-reading:

* **Nothing that needs a missing endpoint.** Email send, file upload, lead conversion and
  deal contacts are unreachable by definition.
* **Look.** It checks that content exists, not that anything is legible or aligned. Screenshots
  land in `scratch/shots/` for a human to judge.
* **The call panel's *mounting*** is checked; its *logic* is not, and cannot be — the panel
  is driven by an `exotel_call` socket event and nothing in a test run can make a real call
  happen. That branch logic is pinned by unit tests instead
  (`telephony/callStatus.test.ts`, 15 cases), which is the right tool for it: a pure
  function of a flat bag of strings needs no browser.
* **Most settings screens only render.** Fifteen prove they load; only Users is exercised.
* **One database, one user.** Everything runs as Administrator. Nothing here tests the
  permission layer, which is where a CRM's sharpest bugs live.

---

## How to run it tomorrow

```bash
# terminal 1
../frappe_django_crm/backend/.venv/Scripts/python.exe backend/manage.py runserver 8000 --noreload

# terminal 2
cd frontend-react && npm run dev

# terminal 3
cd frontend-react
npm run check:api    # ~1s, no servers needed
npm test             # 48 unit tests, no servers needed
npm run verify       # ~2 min, needs both
```

`check:api` alone would have caught the telephony bug the moment it was written. Run it
first; it is nearly free.
