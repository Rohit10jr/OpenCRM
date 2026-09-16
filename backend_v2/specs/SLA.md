# SLA — service level agreements and response tracking

**Status: Provisional, 2026-09-16.** Written before FOUNDATION exists: the scope is right,
the details are guesses. **Rewrite against `backend_v2/docs/AS_BUILT.md` before running.**
Paths are from the repository root.

## 1. Scope

App `sla`. The `PORT_MAP.md` rows under **SLA**:

- **Doctypes:** CRM Service Level Agreement, CRM Holiday List; child tables CRM Service
  Day, CRM Service Level Priority, CRM Holiday, CRM Rolling Response Time
- **No method paths.** An SLA acts when a lead or deal is saved: it sets the response
  deadline and tracks first response and rolling response times.

## 2. Depends on

SALES — the SLA fields sit on Lead and Deal.

## 3. Read in `backend/` first

- `crm_app/models/sla.py`
- `crm_app/models/core_sales.py` — the SLA fields mixin, and where Lead and Deal call
  into the SLA on save
- Tests: the SLA cases in `test_crm_models.py`, `test_crm_behaviour.py` and
  `test_phase5_async.py` — `grep -il "service level\|sla" backend/tests/*.py`
- The upstream controller, `crm/fcrm/doctype/crm_service_level_agreement/`, where the
  old backend leaves a question open

## 4. Must not be lost

- **Which SLA applies** to a document — default, conditions, priority — and **the
  deadline it computes**, including holidays and working days.
- **A save with no SLA configured behaves exactly as it does today**; most databases have
  none.
- **SLA is computed on write, and there is no scheduled sweep.** Upstream has none, and
  adding one would make list views disagree with upstream's for the same data. The old
  backend pins this with `test_no_sla_job_exists_in_the_beat_schedule`
  (`backend/config/celery.py:1-11`); carry the test over.
- **CRM Holiday List is open reference data. CRM Service Level Agreement is open to every
  authenticated user today, with a question still owed** (`PARITY_EXCEPTIONS.md`): its
  writes change response deadlines.

## 5. Acceptance

- pytest over the deadline calculation, with fixed dates, holidays and weekends.
- `docs/http/07_views_and_metadata.http` reads SLA field metadata and turns green once
  this unit exists.
- The lead and deal blocks of `03_leads.http` and `04_deals.http` whose responses carry
  SLA fields.

## 6. Open questions

- O3 for CRM Service Level Agreement.
