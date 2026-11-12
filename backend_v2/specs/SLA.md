# SLA — service level agreements and response deadlines

**Status: Provisional** — the scope is right, the details are guesses. **Rewrite against
`backend_v2/docs/AS_BUILT.md` before building.** Paths are from the repository root.

## 1. Scope

App `sla`. The `PORT_MAP.md` rows under **SLA**:

- **Doctypes:** CRM Service Level Agreement, CRM Holiday List; child tables CRM Service
  Day, CRM Service Level Priority, CRM Holiday, CRM Rolling Response Time
- **No method paths.**
- **The deadline calculation**, as a service: given a record's details, it picks the SLA
  that applies and works out the response deadline, first response and rolling response
  times.

**It comes before SALES.** Saving a lead or deal calls this service, and the SLA's own
models need nothing from leads or deals. Built first, SALES simply calls it — nobody has to
go back into the sales code later to hook it in. The SLA fields themselves sit on Lead and
Deal, so SALES owns them.

## 2. Depends on

FOUNDATION, and SHARED_ACTIONS for the conditions evaluator that picks which SLA applies.

## 3. Read in `backend/` first

- `crm_app/models/sla.py` (the doctypes) and `crm_app/sla.py` (the deadline calculation)
- `crm_app/conditions.py` — how an SLA's condition is evaluated, as data (FINDINGS 80)
- `crm_app/models/core_sales.py` — the SLA fields mixin, and where Lead and Deal call into
  the SLA on save
- Tests to read and write again: the SLA cases in `test_crm_models.py`,
  `test_crm_behaviour.py` and `test_phase5_async.py` —
  `grep -il "service level\|sla" backend/tests/*.py`. None of the old API tests is SLA's
  alone; the spec check confirms that.
- The upstream controller, `crm/fcrm/doctype/crm_service_level_agreement/`, where the old
  backend leaves a question open

## 4. Must not be lost

- **Which SLA applies** to a record — default, conditions, priority — and **the deadline
  it computes**, including holidays and working days.
- **With no SLA configured, a save behaves exactly as it does today**; most databases have
  none.
- **SLA is computed on write, and there is no scheduled sweep.** Upstream has none, and
  adding one would make list views disagree with upstream's for the same data. The old
  backend pins this with `test_no_sla_job_exists_in_the_beat_schedule` (the note at the
  top of `backend/config/celery.py`); carry the test over.
- **CRM Holiday List is open reference data. CRM Service Level Agreement has a list rule
  and an object rule** in `backend/` (decided on `main` after this spec was written;
  REBUILD_PLAN S21): its writes change response deadlines. Carry the rule over as
  `PORT_MAP.md` records it.

## 5. Acceptance

- pytest over the deadline calculation on its own — fixed dates, holidays, weekends, and a
  stand-in record — since leads and deals do not exist yet.
- **The `.http` checks come with SALES**: the lead and deal blocks of `03_leads.http` and
  `04_deals.http` whose responses carry SLA fields, and the SLA metadata in
  `07_views_and_metadata.http`.

## 6. Open questions

None yet.
