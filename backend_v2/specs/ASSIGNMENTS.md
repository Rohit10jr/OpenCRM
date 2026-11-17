# ASSIGNMENTS — ToDo, the Assignment Rule model, and the assignment engine

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

Split out of SHARED_ACTIONS and ACTIVITIES on 16 Nov 2026 (decided on the owner's behalf,
`temp` A-7): SHARED_ACTIONS' spec check found the engine cannot be built without the
models ACTIVITIES was to build, and SALES, which calls it on save, comes before
ACTIVITIES (`tasks/SHARED_ACTIONS_00_spec_check_verdict.md`, findings 1, 12, 13).

## 1. Scope

In app `activities` (the models and the engine; ACTIVITIES later adds the routes in the
same app, as FOUNDATION and ACCOUNTS share `accounts`), and in `core` (`render_template`).
The `PORT_MAP.md` rows under **ASSIGNMENTS**, plus the Assignment Rule model:

- **Doctypes:** ToDo (withheld — no route), Assignment Rule (the model and its declared
  fields; its routes and route protection are ACTIVITIES'), Assignment Rule Day and
  Assignment Rule User (child tables).
- **`assign_to_user`** — the port of `backend/frappe_core/assignment.py`: creating,
  closing and cancelling a ToDo, and the document's `_assign` cache.
- **The assignment engine** — the port of `backend/crm_app/assignment_rules.py` without
  `bulk_apply` (ACTIVITIES'): Round Robin, Load Balancing, Based on Field and Weighted
  Distribution (`:216-288`), assignment days, priority order, the assign / unassign /
  close / reopen transitions (`:315-389`), rendered descriptions, due dates (`:413-436`),
  and the rule cache.
- **Its generic save hook**: the old one attaches to every non-child doctype except ToDo,
  Assignment Rule and Version (`assignment_rules.py:45-50, 486-516`; `crm_app/apps.py:49-54`).
  Lead and Deal instead call `run_after_save` directly after owner sync
  (`crm_app/models/core_sales.py:453-466, 694-704, 1028-1042`) — SALES makes that call.
- **`render_template`** in `core`: the Jinja2 sandbox renderer
  (`backend/crm_app/api/email_template.py:23-70`), a plain function with no model. The
  engine uses it once (`assignment_rules.py:303`); ACTIVITIES' Email Template calls it.
- **ToDo's save side effects**: owner sync for Lead/Deal and the assignee's notification
  (`backend/crm_app/async_signals.py:319-338, 380-413`).

## 2. Depends on

ACCOUNTS (User and its roles), NOTIFICATIONS (a ToDo notifies its assignee),
SHARED_ACTIONS (the conditions evaluator, `core/conditions.py`).

## 3. Read in `backend/` first

- `crm_app/assignment_rules.py`, `frappe_core/assignment.py`, `frappe_core/doc_caches.py`
- `frappe_platform/models.py` — ToDo, Assignment Rule, Assignment Rule Day / User
- `crm_app/async_signals.py` (the ToDo handlers), `crm_app/apps.py:49-54`
- `crm_app/api/email_template.py:23-70`
- `specs/UNROUTED_DOCTYPES.md` (ToDo), `UPSTREAM_BUGS.md` #16
- The framework, only where `backend/` is silent:
  `frappe/automation/doctype/assignment_rule/assignment_rule.py`,
  `frappe/desk/form/assign_to.py` (`git show version-15:<path>`)
- Tests to read and write again: `test_assignment_engine.py`, `test_assignment.py`,
  `test_assignment_notifications.py`, and the ToDo half of `test_doc_caches.py`. The
  spec check confirms the list and which cases need Lead/Deal (those go to SALES).

## 4. Must not be lost

- **A malformed or unevaluable rule condition** raises `ConditionError`, is logged as
  `Auto assignment failed: <reason>` at warning level, and the rule is treated as
  non-matching (`assignment_rules.py:145-160`). Only that error is swallowed: the old
  engine does not catch every failure around assignment (spec check finding 13).
- **ToDo has no route** (bug #16). `ToDo.assignment_rule` is read-only.
- **The `_assign` cache is written with a plain update** that never bumps `modified`.
- **Assigning notifies the assignee** (FINDINGS 18).
- **A rule's description renders in the sandbox** — template text is user-authored.
- Add ToDo to FOUNDATION's reference-cleanup table in `core/children.py`.
- **Two models without routes** (owner, 17 Nov 2026) — follow AS_BUILT "Writing a row
  rule" (the six-point list) for both:
  - **ToDo, permanently withheld:** an entry in `core/withheld.py`, the guard's exact
    withheld set updated, and a link-scan classification (it is already in
    `IGNORE_LINKS_ON_DELETE`, `core/delete.py:22` — confirm that suffices).
  - **Assignment Rule, withheld only until ACTIVITIES routes it:** this unit lists it in
    `core/withheld.py` with `ROW_RULES` or an explicit ignore, so the served-or-withheld
    and link-scan guards pass; ACTIVITIES removes both when it adds the routes (its
    "Carried from ASSIGNMENTS").

## 5. Acceptance

- pytest: the rewritten engine and assignment tests, with their expected answers
  unchanged, on `tests_support` documents and the real ToDo/Assignment Rule models; the
  hook's skip list; the condition-error path.
- No `.http` block of its own: the assignment blocks are ACTIVITIES' and SALES'.

## 6. Questions — after the spec check, before the first build brief

Design choices inside the plan: decided at the spec review by the supervising session
with Codex/agy (owner, 17 Nov 2026; DECISIONS 20), summarised for the owner in
`temp\SPEC_REVIEWS.md`. Supervisor's early view on the second: yes.


- **How the generic save hook is wired** without a registry (S24): a `post_save` signal
  connected per model in `activities/apps.py`, or an explicit call from `BaseDocument`'s
  save into a hook list `core` knows. Lead/Deal call the engine directly instead.
- **ToDo's Lead/Deal owner sync** needs `sales`, built later: does ASSIGNMENTS leave the
  sync to SALES (SALES connects its own handler), so `activities` never imports `sales`?

## 7. Carried from ACCOUNTS

- The old User document carries `assignmentruleuser_set` (an accident of reverse-FK
  discovery, `backend/frappe_core/children.py:38-51`); ASSIGNMENTS' spec check decides
  whether v2 emits the real rows or records a parity exception, and v2 never accepts
  writes to it through User. Until then `UserSerializer` emits it empty
  (`backend_v2/accounts/serializers.py`, `EMPTY_CHILD_KEYS`).
