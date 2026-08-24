# frappe_django_crm — React worktree, agent brief

**This worktree converts the Vue frontend to React.** The Django backend is finished and is
a fixed contract here. The backend port itself lives in a sibling worktree and is not the
subject of any review in this directory.

## Read before working

| File | What it is |
|---|---|
| `docs/react-spike/FINDINGS.md` | What the Vue frontend actually is, measured — 321 files, ~46,800 lines |
| `docs/react-spike/SPIKE_PLAN.md` | Scope, stack, the gate, and the acceptance test |
| `PORT_PLAN.md` §3 | The frontend wire contract |
| `PORT_PLAN.md` §6 | The API surface — 51 whitelisted endpoints |
| `specs/AS_BUILT.md` | What the backend actually serves |

**Ignore** `specs/PHASE_*.md` and `docs/internal/*`. They are backend-port history — correct,
kept deliberately, and irrelevant to React. `docs/internal/TASK.md` and `RUNBOOK_PHASE_8.md`
are live instructions for a different agent in a different worktree.

## Source of truth

Port from **`frontend/`** — this repo's Vue app, which is not stock. Upstream is readable
for intent:

```
D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\frontend\src
```

Where the two differ, ours wins; the difference is usually deliberate and recorded.
**Never invent semantics.**

## Hard rules

1. `backend/` does not change. If it looks like it must, that is a finding to report.
2. `frontend/` does not change. React goes in `frontend-react/` beside it; the Vue app must
   keep building and passing its vitest suite throughout.
3. Branch `react-spike`, never `main`, and no merge to `main` during the spike.
4. One commit per meaningful change. The owner reads every one — a commit too large to
   review in a sitting has failed regardless of whether the code is right.
5. Conventional beats clever. Anything surprising is a defect even when it works.
6. `auth/tokens.js`, `auth/jwtRequest.js` and `socket.js` are **ported, not reinvented** —
   refresh-once-on-401 and the phase-6 reconnect logic (backoff, jitter, re-subscribe) are
   load-bearing and tested. Pinia stores, `createResource` and composables are rewritten.

## Stack

React 18 + TypeScript · TanStack Router / Query / Table · axios · shadcn/ui · Tailwind ·
sonner · TipTap React bindings · Vite.

## Your role in this repo

You are usually invoked as a **reviewer**, giving a second opinion on code written by
Claude. Be specific — cite file and line. Say plainly when something is right; do not
manufacture findings.

Prioritise, in order:

1. **Contract adherence.** Does the React client call paths that exist, with the request
   and response shape `get_data` actually returns? `test_every_frontend_dotted_path_resolves`
   in `backend/tests/test_phase3_endpoints.py` enforces the path half of this — check the
   shape half yourself.
2. **Behaviour parity with the Vue screen being replaced.** Read both. A React screen that
   renders is not a React screen that behaves.
3. **Readability against the acceptance test.** The owner is fluent in React and not in
   Vue, and must be able to *learn* this code. Flag anything that would need
   reverse-engineering: an invented abstraction, an unfamiliar pattern where a conventional
   one existed, indirection with a single caller. Difficulty that belongs to the CRM's
   domain is fine; difficulty created by the code is the defect.

### Trap shapes for this particular port

There is no track record of frontend defects here yet — the backend port's failure modes
were about permissions and do not transfer. These are the shapes worth suspecting instead:

* **Vue reactivity quietly lost.** Watchers, `computed`, and debounce on filter inputs have
  no automatic React equivalent. A filter that fires per keystroke instead of on settle is
  a real regression that looks correct in review.
* **`createResource` and `useQuery` are not the same thing.** Auto-fetch on mount,
  refetch-on-change, cache lifetime and `enabled` semantics all differ. This is ~90 call
  sites of one pattern — a subtle mismatch here is subtle everywhere at once.
* **`v-model` → controlled components.** Two-way binding becomes a value/onChange pair, and
  a dropped `onChange` produces a field that renders but never updates.
* **Special-casing the first screen.** `ViewControls.vue` is 1,365 lines shared by *seven*
  pages. A list engine written around Deals specifically will pass screen 1 and fail
  screen 2 — which is exactly what the two-screen scope exists to catch. Check that shared
  behaviour is shared, not copied.
* **Silently diverging from a deliberate upstream bug.** `UPSTREAM_BUGS_PHASE_0-2.md` and
  `UPSTREAM_BUGS_PHASE_3-6.md` hold the upstream findings, several citing Vue files by line
  (`Settings.vue:214-218`, `UserEmailSettings.vue:139`, `LeadModal.vue:187`). Some are
  reproduced on purpose. If a rewritten screen behaves differently from its Vue original,
  grep those files before calling it a fix.
