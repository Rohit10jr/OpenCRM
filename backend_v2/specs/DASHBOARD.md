# DASHBOARD — dashboard layouts and charts

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

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
- `docs/FINDINGS.md` entries 20 and 21; `docs/UPSTREAM_BUGS_PHASE_3-6.md` on the
  period comparison
- Tests: `test_dashboard_charts.py`, `test_dashboard_periods.py`

## 4. Must not be lost

- **All nineteen of upstream's charts** exist (finding 20: six were missing, and a tile
  using one rendered `Invalid chart name`).
- **Who sees which numbers.** Only the three CRM roles may call the dashboard at all. A
  plain Sales User always gets their own figures, whatever `user` they send; a manager may
  ask for anyone's (`crm_app/api/dashboard.py:64-68`, `111-118`). CRM Dashboard itself
  is open — it holds chart definitions, not data.
- **`reset_to_default` is System Manager only.**
- **A date that does not parse is a 417** with upstream's sentence, not a 500
  (finding 21).
- **The comparison period is genuinely the same length as the chosen one** — a recorded
  divergence from upstream's baseline, which is a day short (`dashboard.py:128` onwards,
  pinned by `test_dashboard_periods.py`).
- **The funnel puts a status with no position first.**

## 5. Acceptance

- pytest for each chart's figures on a fixed data set, as a Sales User and as a manager.
- `docs/http/10_dashboard.http` in full; the dashboard blocks of
  `11_permissions_matrix.http`.
- The body diff over the same blocks.

## 6. Open questions

None yet.
