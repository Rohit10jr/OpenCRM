# frappe_django_crm — agent brief

Porting **Frappe CRM** (Python/Frappe framework) to **Django + DRF**, keeping the
existing Vue frontend.

## Read before working

| File | What it is |
|---|---|
| `PORT_PLAN.md` | Source inventory, frontend contract, settled architecture decisions |
| `specs/README.md` | Index of per-phase specs and their status |
| `specs/PHASE_<N>_*.md` | The spec for the phase you were asked about |

These encode decisions that are already settled. Do not re-litigate them; if you
believe one is wrong, say so in your report rather than working around it.

## Source of truth

The Frappe original:

```
D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm
```

Read it whenever behaviour is unclear. **Never invent semantics.**

## Hard rules

1. The frontend wire protocol (`PORT_PLAN.md` §3) is a fixed external contract. JWT
   auth and the WebSocket transport are the only two sanctioned deviations.
2. String primary keys per the six `autoname` strategies in
   `specs/PHASE_0_FOUNDATION.md` §2 — three doctypes are genuinely autoincrement.
3. `_assign` is a denormalised cache of `ToDo` records. Never use it for access control.
4. Preserve `frappe.throw` message text verbatim — it is user-facing copy.
5. Postgres, not MariaDB: map Frappe's `like` to `ilike`/`icontains`.

## Stack

Django + DRF + SimpleJWT, PostgreSQL 17, Redis, Celery, Django Channels,
django-treebeard. Python 3.13.

## Your role in this repo

You are usually invoked as a **reviewer**, giving a second opinion on code written by
Claude. Prioritise, in order: correctness against the Frappe source, permission/security
correctness, and adherence to the phase spec. Be specific — cite file and line. Say
plainly when something is right; do not manufacture findings.
