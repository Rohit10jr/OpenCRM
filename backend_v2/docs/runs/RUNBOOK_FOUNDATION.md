# Runbook — FOUNDATION

**Status: not ready to run.** It waits on the owner's review of
`backend_v2/specs/FOUNDATION.md`, and on the open questions that spec lists in section 7 —
REBUILD_PLAN O2 (baseline data), O5 (filter and sort design), O6 (the route map) and O7
(where the generic operations live). When they are settled, update this header, the spec's
status and the row in `backend_v2/specs/README.md`, in one commit.

This file is the handoff for one run. **What** to build is the spec; **how to run it**
is here, and nothing here changes the spec's scope. **Paths are from the repository
root.**

---

## Scope

`backend_v2/specs/FOUNDATION.md`, all of it. Nothing from any other unit, even where it
looks small and adjacent — later units assume FOUNDATION did exactly its own scope.

**One agent.** Subagents may research — read the old backend, the Frappe source — but
one agent writes every file, because this unit sets the conventions everyone copies.

## Step 0 — orientation, before any code

Read, in order: the root `CLAUDE.md` (its "Every task" section and "Working on
`backend_v2/`"), `backend_v2/docs/REBUILD_PLAN.md`,
`backend_v2/docs/API_CONTRACT.md`, `backend_v2/specs/FOUNDATION.md`, then the old files
the spec's tables name.

Then write `backend_v2/docs/runs/ORIENTATION_FOUNDATION.md` and commit it on its own,
**before** writing any code:

1. **What you understood** the unit to be, in your own words, in under a page.
2. **What looks stale or wrong** in the plan, the contract or the spec, checked against
   `backend/`. Each with the file and line that shows it. The phase-7 and phase-8
   orientations of the old backend found four and five false claims; finding none is
   more likely a sign of not looking than of none being there.
3. **The decisions the spec leaves to you** (spec section 6), and what you intend for
   each, before building on them.
4. **Anything that stops the run.** If one exists, stop after this file and say so.

## How to work

- **One commit per meaningful change**, each with what and why — the skeleton, the error
  layer, the filter backend, the ViewSet base, authentication, the map and resource
  route, each guard test, the parity tool. A dozen commits is right; one is wrong.
- **Write the test that should fail, see it fail, then write the code.** A test that
  cannot fail proves nothing: twice in the old backend's first phases a test passed with
  or without the fix (`specs/AS_BUILT.md` section 7).
- **Copy messages verbatim** from `backend/`. Search for the sentence rather than
  retyping it.
- **When the old backend and the contract disagree**, the old backend wins: correct
  `API_CONTRACT.md` in its own commit, and say so in the progress report.
- **A behaviour you want to change** is a proposed entry in
  `backend_v2/docs/PARITY_EXCEPTIONS.md`, not a change. Build the parity version.
- **Record as you go** in `backend_v2/docs/AS_BUILT.md`, not at the end.

## The gate

Spec section 5, all six items. Run in this order, and record each result with the
command that produced it:

1. `manage.py check`; migrations from an empty `opencrm_v2`.
2. pytest in `backend_v2/`.
3. `backend/` on port 8000 and `backend_v2` on port 8001; `backend_v2/scripts/parity_diff.py`
   over the FOUNDATION blocks of `docs/http/01_auth.http` — the originals to `backend/`,
   the translations through the route map to `backend_v2`.
4. Each guard test broken on purpose, seen to fail, restored.
5. Independent review, tier 1 first (root `CLAUDE.md`), with the root `AGENTS.md` as the
   reviewer's brief. State the tier that worked. Report findings to the owner, including
   where you disagree; do not apply them unasked.

**Never pass `--mark` to `backend/scripts/run_http.py`** if you use it against
`backend/`: it writes into `docs/ROUTES.md`.

Before step 3, check the ports: `netstat -ano | findstr :8000` and `:8001`. A stale server
from an earlier attempt answers with old code.

## Fail-stop

**If the gate fails twice, stop.** Write what happened in the progress report and hand
back. A foundation with a known hole, honestly reported, costs less than twelve units
built on a foundation believed to be sound.

**Also stop** — after writing the orientation — if Step 0 finds that a Settled decision
cannot hold, or that the contract cannot be met with DRF's extension points without a
registry.

## When it is done

Write `backend_v2/docs/runs/PROGRESS_FOUNDATION.md`, never edited afterwards:

1. **Built** — what exists, by app
2. **Tests** — counts, and the commands run
3. **Gate** — each item, with its result
4. **Review** — the tier, the findings, what was applied and what was declined, and why
5. **Decisions taken without the owner** — each, with the reason
6. **Deviations** from the spec or this runbook
7. **Not done** — and the unit it now belongs to
8. **`01_auth.http` blocks left for ACCOUNTS**, by number
9. **Concerns** — what you did not check, and what you would check next. **This section is
   read first**; a thin one is a warning sign, not a good result

Then: flip FOUNDATION to Done in `backend_v2/specs/README.md`, mark its rows in
`backend_v2/docs/PORT_MAP.md`, and commit the bookkeeping on its own.
