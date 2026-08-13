# Phase Specs — Frappe CRM → Django Port

One spec per phase. **Read `../PORT_PLAN.md` first** — it holds the source inventory,
the frontend contract, and the settled architecture decisions. These specs assume it.

| Spec | Phase | Agents | Status |
|---|---|---|---|
| [`PHASE_0_FOUNDATION.md`](PHASE_0_FOUNDATION.md) | Foundation, generic API, auth | **Single agent** | Authoritative |
| [`PHASE_1_MODELS.md`](PHASE_1_MODELS.md) | Platform + CRM models | Fan out by cluster | Authoritative |
| [`PHASE_2_PERMISSIONS.md`](PHASE_2_PERMISSIONS.md) | Row-level permission engine | **Single agent** | Authoritative |
| [`PHASE_3_ENDPOINTS.md`](PHASE_3_ENDPOINTS.md) | 51 API endpoints | Fan out by module | Provisional |
| [`PHASE_4_METADATA.md`](PHASE_4_METADATA.md) | View settings, field layouts | Fan out | Provisional |
| [`PHASE_5_ASYNC.md`](PHASE_5_ASYNC.md) | Celery jobs and schedules | Fan out | Provisional |
| [`PHASE_6_REALTIME.md`](PHASE_6_REALTIME.md) | Django Channels | Fan out | Provisional |
| [`PHASE_7_INTEGRATIONS.md`](PHASE_7_INTEGRATIONS.md) | ERPNext, Twilio, Exotel, Facebook | Fan out | Deferred |

## What "Provisional" means

Phases 3–6 were specced **before phase 0 was implemented**. They encode assumptions
about the registry, serializer, and permission APIs that phase 0 will finalise.

**The phase-0 agent owns these files.** On completing phase 0, it must revise every
provisional spec to match what was actually built, and flip the status to
Authoritative. Downstream agents must not start against a Provisional spec without
checking that phase 0 has landed.

Sections marked > **PROVISIONAL** call out the specific assumption at risk.

## Source of truth

When a spec is ambiguous, the Frappe source wins:

```
D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm
```

Read it. Do not invent behaviour. If the source is genuinely ambiguous, use the
Docker oracle (`PORT_PLAN.md` §9) and record the finding in the spec.

## Non-negotiables for every agent

1. The frontend wire protocol (`PORT_PLAN.md` §3) is a hard contract. JWT auth is the
   only sanctioned deviation.
2. String primary keys, never auto-increment integers.
3. No two concurrent agents edit the same file. Split on cluster/module lines.
4. Flag uncertainty in your report. Do not invent semantics.
