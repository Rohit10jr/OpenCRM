# Parity exceptions — where `backend_v2` answers differently on purpose

The rebuild's rule is **same status, same body** as `backend/`
(`backend_v2/docs/API_CONTRACT.md`). This file is the only place that rule may be broken,
and every break is written here **before** the code that makes it. A difference found in
testing that has no entry here is a bug in `backend_v2`, not an exception.

**Paths are from the repository root.**

## What earns an entry

- **An old-backend defect not worth copying**, such as a request that answers 500. A 500
  is never part of the contract, but replacing it with a proper error is still a change a
  client can see.
- **A decision the old backend deferred** and the owner has now taken.
- **A default that differs between library versions** (Django 5.1 → 5.2, S17) where
  matching the old output would mean fighting the framework.

Not an entry:

- **A value that legitimately differs between two servers** (generated names, timestamps,
  tokens). The body diff normalises those, and `API_CONTRACT.md` lists them.
- **The new URL, HTTP method and reshaped inputs of a route.** Those change by design
  (REBUILD_PLAN S6, S7) and are recorded in the route map in `PORT_MAP.md`. An entry here
  is for a difference in what comes back — status, body, behaviour — not in how it is
  asked for.

## How an entry is written

**Who does what:**

1. **The building agent proposes.** When it finds something it thinks should answer
   differently from the old backend, it adds an entry under **Register** below, with status
   `proposed`.
2. **It keeps building the parity version** — the old behaviour — in the meantime, never the
   change.
3. **It tells the owner**: in its progress report, and in chat during a session.
4. **Only the owner approves or rejects.** The code changes only once the entry says
   `approved`.

Each entry has this shape:

```
### PE-<n>. <one-line summary>

- **Status:** proposed | approved | rejected — only the owner approves
- **Where:** the method path or doctype, and the `.http` block that shows it
- **Old backend:** what it answers today, with the file and line that decides it
- **backend_v2:** what it will answer instead
- **Why:** the reason, and what a client could notice
- **Recorded by:** unit and date
```

An `approved` entry changes the expectation. The `.http` block that shows the difference
is named, its REST copy in `backend_v2/http/` expects the new answer, and the body
comparison skips that block.

---

## Register

*No entries yet.*

---

## For after the rebuild — not exceptions

### The eight doctypes the old backend left "awaiting review" (REBUILD_PLAN S21)

Open to every authenticated user today, each with the question the old backend recorded
against it (`backend_v2/docs/PORT_MAP.md`, Old protection column). **Decided: `backend_v2`
keeps the same access.** The questions below are revisited after the rebuild; until then
nothing here is an exception.

| DocType | The recorded question | Unit |
|---|---|---|
| Contact | Shared across leads and deals; upstream relies on role permissions | CONTACTS |
| CRM Organization | Is organization data meant to be company-wide? | CONTACTS |
| CRM Product | Catalogue data; writes change prices used in deal totals | SALES |
| Email Template | Writes change the wording of mail the system sends on your behalf | ACTIVITIES |
| Tag | Low risk, but writes are unconstrained | ACTIVITIES |
| CRM Service Level Agreement | Writes change response deadlines | SLA |
| CRM Call Log | Call history references leads and deals; recording URLs are on the row | ACTIVITIES |
| CRM Telephony Agent | Holds colleagues' phone numbers | INTEGRATIONS |

### Candidates from `specs/KNOWN_ISSUES.md` — check they are still open first

Recorded against the old backend before the rebuild began. Some may have been fixed
since; confirm against `backend/` before proposing an entry.

| Known issue | What a `backend_v2` entry would change | Unit |
|---|---|---|
| §7 — an email subject containing a line break answers **500** on the inline send path | A 417 `ValidationError` instead. Needs a sentence upstream does not have, which is why the old backend left it | ACTIVITIES |
| §7 — `assign_to.remove_multiple` clears every assignee; upstream's limit of 5 leaves the sixth | Matching upstream would reintroduce its limit; keeping it is parity with the old backend. Probably no entry | ACTIVITIES |
| §6 — logout cannot revoke an access token already issued | A token-version check (the issue's option 3) changes no response body, only whether a stale token is accepted. Needs the owner's decision either way | ACCOUNTS |
