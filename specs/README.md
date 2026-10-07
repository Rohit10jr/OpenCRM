# Phase Specs — Frappe CRM → Django Port

One spec per phase.

> **Read [`AS_BUILT.md`](AS_BUILT.md) before anything else.** It records what phases
> **0-6** actually built, as opposed to what these specs predicted. Where a spec and
> `AS_BUILT.md` disagree, **`AS_BUILT.md` wins** — the specs were written first.
>
> Two companions are not optional before adding a doctype:
> [`SECURITY_MODEL.md`](SECURITY_MODEL.md) (what protects each one, and the 11 places we
> deliberately differ from upstream) and [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) (problems
> that outlive a phase — check before re-diagnosing something).

Then **`../PORT_PLAN.md`** — it holds the source inventory,
the frontend contract, and the settled architecture decisions. These specs assume it.

| Spec | Phase | Agents | Status |
|---|---|---|---|
| [`AS_BUILT.md`](AS_BUILT.md) | **What exists today** — read first | — | Authoritative |
| [`PHASE_0_FOUNDATION.md`](PHASE_0_FOUNDATION.md) | Foundation, generic API, auth | **Single agent** | ✅ Shipped |
| [`PHASE_1_MODELS.md`](PHASE_1_MODELS.md) | Platform + CRM models | Fan out by cluster | ✅ Shipped |
| [`PHASE_2_PERMISSIONS.md`](PHASE_2_PERMISSIONS.md) | Row-level permission engine | **Single agent** | ✅ Shipped |
| [`PHASE_3_ENDPOINTS.md`](PHASE_3_ENDPOINTS.md) | 51 API endpoints | Fan out by module | ✅ Shipped |
| [`PHASE_4_METADATA.md`](PHASE_4_METADATA.md) | View settings, field layouts | Fan out | ✅ Shipped |
| [`PHASE_5_ASYNC.md`](PHASE_5_ASYNC.md) | Celery jobs and schedules | Fan out | ✅ Shipped |
| [`PHASE_6_REALTIME.md`](PHASE_6_REALTIME.md) | Django Channels | Fan out | ✅ Shipped |
| [`PHASE_7_INTEGRATIONS.md`](PHASE_7_INTEGRATIONS.md) | ERPNext, Twilio, Exotel, Facebook, WhatsApp | Fan out | ✅ Shipped |
| [`PHASE_8_AUTH_AND_DESK.md`](PHASE_8_AUTH_AND_DESK.md) | Auth screens (scope A) | — | ✅ Shipped |

## The port is complete

**All eight phases have shipped.** ~1,644 backend tests and 162 frontend tests, every phase
reviewed independently at tier 1.

Phase 8 closed the last thing that stopped the product being usable by more than one person:
**a second user can now be onboarded**. Invitation acceptance, password reset and a login
page all existed only in Frappe's Desk, which this port dropped — so the invitation email
led nowhere. That flow is now walked end to end by
`backend/scripts/walk_auth_flow.py`, which is worth running after any change to auth.

**Read before extending anything:**

* Phase 8's own report said its screens had no component tests and nobody had clicked
  them in a browser. Since then every screen has been clicked through and the results are
  in `../docs/BROWSER_TESTING.md`; the Playwright suite under `frontend/tests/e2e` covers
  the sign-in flows. (The report itself was removed with the other run records on 7 Oct
  2026 and is in git history.)
* `get_recording_url` is deliberately unported and is the most security-sensitive single
  function in phase 7. Port it *with* upstream's IP pinning and per-hop redirect
  validation, or not at all.
* `SECURITY_MODEL.md` — per-doctype, and the recurring finding that appeared in five
  separate phases: **a doctype's endpoints are not its attack surface.**
* `../UPSTREAM_BUGS_PHASE_0-2.md` and `../UPSTREAM_BUGS_PHASE_3-6.md` — 38 defects found in
  Frappe and Frappe CRM while porting, each with evidence and our stance. When this port
  behaves differently from upstream, the answer to "is that a port bug?" is in there.

**What is deliberately not built**, and is a product decision rather than an omission:
scope B (CRM screens for the Desk-linked doctypes — assignment rules, holiday lists, SLA
policies) and scope C (a generic admin UI over the doctype registry). Both are sized in
`PHASE_8_AUTH_AND_DESK.md`.

## What "Provisional" means

Phases 3–6 were specced before phase 0 existed, then revised twice — once by the phase-0
agent, and again after phases 0–2 shipped and their review concerns were resolved. They
are much closer to reality than they were, but no human has reviewed the revisions.

**Flip your spec's header to Authoritative when its gate passes.** A spec still claiming
to be provisional after its phase shipped is worse than no status at all.

`AS_BUILT.md` is the exception: it describes shipped code and is authoritative.

## Source of truth

When a spec is ambiguous, the Frappe source wins. Both repositories are readable:

```
CRM app    D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm    (main)
framework  D:\02_Personal\01_OpenSource\02_FrameWorks\frappe           (version-15)
```

The framework was unavailable during phases 0-2; several defects were only findable
in it. Do not read `develop` - it is v16 pre-release.

Read it. Do not invent behaviour. If the source is genuinely ambiguous, use the
Docker oracle (`PORT_PLAN.md` §9) and record the finding in the spec.

## Non-negotiables for every agent

1. The frontend wire protocol (`PORT_PLAN.md` §3) is a hard contract. JWT auth is the
   only sanctioned deviation.
2. String primary keys, never auto-increment integers.
3. No two concurrent agents edit the same file. Split on cluster/module lines.
4. Flag uncertainty in your report. Do not invent semantics.
