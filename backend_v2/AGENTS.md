# backend_v2 — reviewer brief

**Read together with the repository-root `AGENTS.md`**, which still applies: its hard
rules, its list of past failures, and its **How to report** section, unchanged. Where the
two differ, **this file wins for `backend_v2/`**. **Paths are from the repository root.**

## What you are reviewing

A rebuild, not a port. `backend/` already serves the Frappe CRM frontend by re-creating
Frappe's request layer inside Django. `backend_v2/` serves **the same API with the same
JSON** as a conventional Django project: one app per domain, explicit URLs, DRF ViewSets
and serializers. The author is moving behaviour out of `backend/` into that shape.

The two ways this goes wrong are **losing something the old backend did** and **changing
something the old backend did**. Both are silent: the author's own tests test the new
code, not the old.

## Read before reviewing

| File | What it tells you |
|---|---|
| `backend_v2/docs/API_CONTRACT.md` | What must be identical on the wire |
| `backend_v2/docs/PORT_MAP.md` | Each doctype's and method path's old source, protections and unit |
| `backend_v2/docs/REBUILD_PLAN.md` | The decisions — Settled, Proposed and Open |
| `backend_v2/docs/PARITY_EXCEPTIONS.md` | The only differences that are allowed |
| `backend_v2/docs/AS_BUILT.md` | What exists, and the conventions it set |
| `backend_v2/specs/<UNIT>.md` | The unit under review |

## Source of truth — different from the root brief

1. **The old backend in `backend/`** decides behaviour and JSON. For a method path,
   `PORT_MAP.md`'s Old source column names the file and line.
2. **The Frappe source** (both repositories, listed in the root `AGENTS.md`) only where
   the old backend leaves a question open.

Compare the new code against the old code, not against the spec. The spec was written
before the code, by someone who could share the author's misreading.

## What to check, in this order

1. **Parity.** For every endpoint touched: the status code, every key, every value type,
   and every message, verbatim, against `backend/`. The known traps are a decimal that
   is a string in a document but a number in a list row; an `exc_type` or status that
   drifted to DRF's default (400 instead of 417); and a 403 that should be a 404, or the
   reverse. Unknown, child-table and withheld doctypes must all answer the same 404.
2. **Protections carried over.** For every doctype touched, each item in its
   `PORT_MAP.md` row: the list rule *and* the object rule; each sensitive, restricted,
   read-only and encrypted field, enforced in the response and in `fields`, `filters`,
   `or_filters`, `order_by` and `group_by`; the create check against the payload rather
   than an empty instance; the destination re-check on update for rows that point at
   another document. For guest endpoints: no enumeration, single-use keys, the lockout on
   every password check, webhook signatures verified.
3. **Every door.** A doctype is reachable through `/api/resource/`, `frappe.client.*`,
   `get_data`, `search_link` and the bulk actions. Each must go through the same ViewSet
   queryset and field policy. **A protection enforced on one door and not another is the
   failure this project has found most often.**
4. **Nothing published by side effect.** Every route is in an app's `urls.py`; the doctype
   map is literal code; allowlists are explicit lists, not "every field except".
5. **Conventional Django.** The user passed explicitly, never read from ambient state;
   logic in models and services rather than views; migrations that apply from empty;
   tests that would fail without the code they cover.
6. **A behaviour change with no approved `PARITY_EXCEPTIONS.md` entry** is a finding,
   even when the change is an improvement.

## Failure shapes specific to a rebuild

- **A protection lived in the old generic layer** — `backend/frappe_core/query.py`,
  `field_security.py`, `views.py` — and the new path does not pass through anything
  equivalent. The old endpoint never mentioned it, so the port of that endpoint does not
  either.
- **A test asserts the author's transcription** instead of what `backend/` answers. It
  passes against the new code and proves nothing about parity.
- **A message copied approximately** — reworded, re-capitalised, a missing `<strong>`.
- **A document read matches, and the list row for the same record does not**, because
  they are rendered by different paths.

## Do not report

- Differences with an **approved** entry in `PARITY_EXCEPTIONS.md`.
- Values that legitimately differ between two servers: generated names, timestamps,
  tokens.
- Style preferences with no bearing on the checks above.

## How to report

As the root `AGENTS.md` says: first line `REVIEW NOT PERFORMED` if you cannot read the
repository; no test results you did not produce; one block per finding, most severe
first. In **Evidence**, cite the `backend/` file and line you compared against, and the
upstream line as well where it matters.
