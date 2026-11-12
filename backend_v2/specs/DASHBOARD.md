# DASHBOARD — dashboard layouts and charts

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

## 1. Scope

App `dashboard`. The `PORT_MAP.md` rows under **DASHBOARD**:

- **Doctype:** CRM Dashboard
- **Method paths (3):** `crm.api.dashboard.get_dashboard`, `get_chart`,
  `reset_to_default`

## 2. Depends on

SALES — every number on the dashboard is a count or sum over leads and deals.

## 3. Read in `backend/` first

- `crm_app/api/dashboard.py` — all nineteen charts
- `crm_app/models/metadata.py` (CRM Dashboard)
- `docs/FINDINGS.md` entries 20 and 21; `UPSTREAM_BUGS.md` on the
  period comparison
- Tests to read and write again: `test_dashboard_charts.py`, `test_dashboard_periods.py`
- **Tests to port** (REBUILD_PLAN S14): this unit's routes in `test_phase3_endpoints.py`;
  no other old API test is the dashboard's alone. The spec check confirms the list.

## 4. Must not be lost

- **All nineteen of upstream's charts** exist (finding 20: six were missing, and a tile
  using one rendered `Invalid chart name`).
- **Who sees which numbers.** Only the three CRM roles may call the dashboard at all. A
  plain Sales User always gets their own figures, whatever `user` they send; a manager may
  ask for anyone's (`sales_user_only` and `resolve_scope` in `crm_app/api/dashboard.py`).
  CRM Dashboard itself is open — it holds chart definitions, not data.
- **`reset_to_default` is System Manager only.**
- **A date that does not parse is a 417** with upstream's sentence, not a 500
  (finding 21).
- **The comparison period is genuinely the same length as the chosen one** — a recorded
  divergence from upstream's baseline, which is a day short (`_period_before` in
  `dashboard.py`, pinned by `test_dashboard_periods.py`).
- **The funnel puts a status with no position first.**

## 5. Acceptance

- pytest: the ported tests passing with their expected answers unchanged, and each chart's
  figures on a fixed data set, as a Sales User and as a manager.
- `docs/http/10_dashboard.http` in full; the dashboard blocks of
  `11_permissions_matrix.http`.
- The body diff over the same blocks.

## 6. Open questions

None yet.
