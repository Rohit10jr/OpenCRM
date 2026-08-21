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
| [`PHASE_8_AUTH_AND_DESK.md`](PHASE_8_AUTH_AND_DESK.md) | Auth UI and the rest of the Desk | — | **Parked** |

**Phase 7 shipped** on `phase-7-integrations` — all five integrations, each behind its own
flag, all off by default. See `../docs/internal/PROGRESS_PHASE_7.md`, and read its
**Concerns** before extending any of them: `get_recording_url` is deliberately unported and
is the most security-sensitive single function in the phase.

**Phase 8 is parked, not scheduled.** It is also the only phase that ports nothing:
Frappe ships a Desk (auth screens, generic admin UI) alongside the CRM app, and this port
dropped it. Blocking consequence recorded there — **there is currently no way to onboard
a second user**, because accepting an invitation redirects to a Desk-hosted set-password
page. Do not start it before phases 0–7 are done.

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
