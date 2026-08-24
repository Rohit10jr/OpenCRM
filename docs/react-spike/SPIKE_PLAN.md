# React spike — plan

**A spike, not a feature.** It exists to answer questions, and it ends when they are
answered. Read `FINDINGS.md` first; the numbers below come from there.

---

## Why this is happening

The backend was ported deliberately over seven phases. The frontend was **copied**, and it
is Vue. That is a problem for one specific reason, and the reason determines what "done"
means here:

> The owner of this project is fluent in React, shadcn, TanStack and axios, and not in
> Vue. A portfolio project you cannot read is a portfolio project you cannot defend.

So success is **not** "the screen renders". But it is also not "can you explain every
line on day one" — nobody can do that with code they did not write, including code they
wrote themselves six months ago. The point is not instant recall. It is that the code is
**learnable**, in a stack already familiar, so that time spent reading it compounds instead
of being spent on Vue's syntax first.

The useful test is therefore about **where the difficulty sits**:

> **Read a file you have not seen. When something is hard to follow, is it hard because
> the *problem* is hard, or because of how the code is written?**

Domain difficulty is expected and fine. The list engine is genuinely intricate — filters,
saved views, kanban and pagination against one endpoint — and no amount of good style makes
that a five-minute read. **Difficulty that comes from the code itself is the defect**: an
invented abstraction, an unfamiliar pattern where a conventional one existed, indirection
with one caller.

That distinction is what the work is optimised for, and it is the reason for small commits,
for conventional idioms over clever ones, and for stopping after two screens.

**The trap to name out loud:** if an agent writes 46,000 lines of React and nobody reads
them, "cannot explain Vue" has become "cannot explain React I did not write" — the same
position, now with a stronger claim attached to it. The review is the point, not the
overhead.

---

## The questions this spike answers

| # | Question | How it is answered |
|---|---|---|
| 1 | **What does one list screen cost?** | Measure the first, then the second. They differ by ~4× and both numbers matter |
| 2 | **Does `createResource` → TanStack Query map cleanly?** | ~90 call sites depend on one pattern. If it is awkward, everything downstream is awkward |
| 3 | **Is the output learnable?** | Read it. Sort what was hard into *domain hard* and *code hard*. The second list is the answer |
| 4 | **Where does the shadcn mapping actually break?** | The inventory looks clean. Something always is not |
| 5 | **Can React and Vue run side by side during a migration?** | Determines whether this can be incremental or must be a big bang |

Question 3 decides whether to continue; the others decide how. Note what it is not asking:
not whether every line is obvious on first read, but whether the difficulty that remains is
the CRM's rather than the code's. The first kind gets easier with time. The second does
not.

---

## Scope

**Two screens, in this order.** Not one — one screen cannot answer question 1.

### Screen 1: Deals list — ~2,500 lines

Deliberately the hardest thing in the app, because an easy screen teaches nothing about
the other 320 files. It exercises, in one place:

* the list engine (`crm.api.doc.get_data`) — filters, sort, columns, pagination
* saved views and quick filters
* a data table
* the kanban board
* row selection and bulk actions

It drags `ViewControls.vue` (1,365 lines, shared by 7 pages) with it. **That is expected
and is the point** — the first screen pays for the engine.

### Screen 2: Leads list — ~600 lines

The same engine, a different page. **This is the number that matters for planning**,
because screens 3–7 look like this one, not like screen 1.

If screen 2 is not dramatically cheaper than screen 1, the engine was built wrong, and
that is a finding worth having after two screens rather than after twenty.

### Explicitly out of scope

Everything else. No settings screens, no modals beyond what Deals needs, no telephony, no
realtime beyond what the list already subscribes to. **Do not tidy adjacent files.**

---

## Stack

Fixed, because familiarity is the entire purpose:

| Layer | Choice |
|---|---|
| Framework | React 18 + TypeScript |
| Routing | TanStack Router |
| Data | TanStack Query + axios |
| Components | shadcn/ui |
| Styling | Tailwind (already in the Vue app; the config ports) |
| Table | TanStack Table |
| Toast | sonner |
| Rich text | TipTap React bindings |
| Build | Vite |

**Where it lives:** a new `frontend-react/` beside `frontend/`, not replacing it. Both
speak to the same Django API on the same port. The Vue app keeps working throughout, which
is what makes this reversible.

---

## What to port versus what to rewrite

A distinction worth making before starting, because it decides where the agent should be
faithful and where it should be idiomatic.

**Port faithfully — the behaviour is load-bearing and already correct:**

* `auth/tokens.js` and `auth/jwtRequest.js` — written for this port, not inherited. The
  refresh-once-on-401 logic and its edge cases are ours and are tested.
* `socket.js` — rewritten in phase 6 with backoff, jitter and re-subscribe on reconnect.
  The reconnect logic in particular was hard-won; **do not reimplement it from memory.**
* The `get_data` request and response shape.

**Rewrite idiomatically — the Vue version is a Vue answer to a Vue problem:**

* Pinia stores → TanStack Query keys. Most are a cached resource plus getters; React does
  not need a state library for that.
* `createResource` → `useQuery` / `useMutation`.
* Composables → hooks, which most of them already are in spirit.

---

## How the work runs

### Commits

**One per meaningful change**, same rule as the backend phases and for a sharper reason
here: the owner reads every one. A commit that cannot be reviewed in a sitting has failed
its purpose regardless of whether the code is right.

Roughly: the scaffold · the axios/auth layer · the query layer · each shadcn primitive
group · the table · the list engine · the Deals page · the kanban · then screen 2.

### Idioms

**Conventional beats clever.** If there are two ways and one is what a React developer
would expect, use that one — even if the other is shorter. Anything surprising is a defect
against the acceptance test even when it works.

Specifically: no custom state managers, no render props where a hook will do, no
abstractions invented for a second caller that does not exist yet.

### Comments

Explain **why**, not what. The backend's convention holds: a comment earns its place by
recording a decision or a trap, not by narrating the line below it.

---

## The gate

The spike is done when all of these are true:

1. **Both screens work against the real Django API — clicked by hand, in a browser.** Not
   mocks, and not a script either. Log in, list deals, filter, sort, switch to kanban, open
   one. Then the same for leads.

   *Why the wording is this specific:* phase 8 wrote an end-to-end walk that drove real HTTP
   against a real database and passed **26 of 26 steps** — and still shipped two bugs to
   review. The invitation email linked to the raw JSON API, and setting a password bounced
   the user straight back to the login screen. Every backend test passed; the walk passed;
   **neither runs a browser.** That was the third occurrence of the same shape in two
   phases. A green integration script is not this gate item.
2. **The dotted-path test passes against the React source.** Point
   `test_every_frontend_dotted_path_resolves` at `frontend-react/` and confirm every API
   path it calls exists. This is the contract, already enforced, and it is free.
3. **The Vue app still works.** Untouched, still building, still passing its 166 tests.
4. **Both numbers are written down** — the cost of screen 1 and of screen 2, in hours and
   in lines.
5. **The read-through happens, and what was hard is written down.** Not a memory test —
   read the files, and for anything that did not land, record *which kind* of hard it was:

   * **domain hard** — the list engine has a lot going on. Expected; note it and move on
   * **code hard** — a pattern that had to be reverse-engineered, an abstraction whose
     purpose was not obvious, something that would have been clearer written plainly

   **The second list is the valuable output of the spike.** Every entry on it is either a
   thing to rewrite before scaling up, or a convention to fix for the remaining 300 files.
   An empty list should be suspicious rather than pleasing — it more likely means the
   read-through was shallow than that the code is perfect.

---

## The decision this feeds

After the spike, three ways forward. The spike's job is to make the choice obvious rather
than to pre-empt it.

| | Path | When it is right |
|---|---|---|
| **A** | **Full conversion** — all 321 files | Screen 2 was cheap, the code reads well, and the arithmetic is tolerable |
| **B** | **Core flows only** — auth, leads, deals, kanban, one settings screen: ~40 files | Screen 2 was cheap but the total is too large. Enough to honestly claim a React frontend against this API |
| **C** | **Stop** | The output could not be defended, or the cost per screen makes the whole thing unserious |

**C is a real outcome, not a failure.** A spike that says "do not do this" has done its job
and cost two screens.

---

## Notes for whoever runs this

* The worktree is `frappe_django_crm_react/` on branch `react-spike`, cut from `main`. The
  phase-8 agent is working in the sibling directory on a different branch; **they share
  git history but not a working tree**, so neither disturbs the other.
* Do not merge to `main` during the spike. It is an experiment until the decision above is
  taken.
* The backend needs no changes. If it looks like it does, that is a finding worth writing
  down before acting on it — the API is a fixed contract and something is probably being
  misread.
