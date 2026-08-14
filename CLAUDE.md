# frappe_django_crm

Porting **Frappe CRM** (Python/Frappe framework) to **Django + DRF**, keeping the
existing Vue frontend.

## Read these first

| File | What it is |
|---|---|
| `PORT_PLAN.md` | Source inventory, frontend contract, settled architecture decisions |
| `specs/README.md` | Index of per-phase specs and their status |
| `specs/PHASE_<N>_*.md` | Your phase's spec |

**Do not start work without reading `PORT_PLAN.md` and your phase spec.** They encode
decisions that are already settled — re-deciding them creates divergence.

## Source of truth

The Frappe original lives at:

```
D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm
```

Read it whenever behaviour is unclear. **Never invent semantics** — match the source,
or flag the ambiguity in your report.

## Hard rules

1. The frontend wire protocol (`PORT_PLAN.md` §3) is a fixed external contract. JWT
   auth and the WebSocket transport are the only two sanctioned deviations.
2. Phases 0 and 2 are single-agent. Everything else fans out by cluster/module.
3. No two concurrent agents edit the same file.
4. Preserve `frappe.throw` message text verbatim — it is user-facing copy.
5. Work on a branch, never directly on `main`.

## Stack

Django + DRF + SimpleJWT, PostgreSQL 17, Redis, Celery, Django Channels,
django-treebeard (nested-set trees). Python 3.13.

---

# Collaborating with Codex

Codex CLI is installed and I want you to use it as a second opinion.

**Setup**
- codex-cli 0.147.0, on PATH as `codex`. Windows/PowerShell. Auth already configured.
- The interactive TUI needs a live terminal, so you **cannot** drive it. Use
  `codex exec` — headless: prompt in, report to stdout.
- Codex reads the repo itself. Don't paste code into the prompt; point it at paths and
  run from the repo root.

**Division of labor:** you write the code, Codex reviews it. Second opinion, not a
second editor.

**Commands**
```powershell
codex exec -s read-only "<review request>"   # review, cannot touch files
codex exec review                            # built-in review subcommand
codex exec resume --last "<follow-up>"       # continue the same Codex session
codex exec --approve-for-me "<task>"         # only if I ask Codex to make edits
```

**Caveats**
- Blocking, ~1-2 min per call. Batch reviews rather than pinging after every edit.
- Each `codex exec` is fresh context — use `resume --last` for iterative rounds.
- Report Codex's findings to me, including where you disagree. Don't auto-apply them.
