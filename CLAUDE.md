# frappe_django_crm

Porting **Frappe CRM** (Python/Frappe framework) to **Django + DRF**, keeping the
existing Vue frontend.

## Read these first

| File | What it is |
|---|---|
| **`specs/AS_BUILT.md`** | **What already exists. Read this first** |
| `PORT_PLAN.md` | Source inventory, frontend contract, settled architecture decisions |
| `specs/README.md` | Index of per-phase specs and their status |
| `specs/PHASE_<N>_*.md` | Your phase's spec |
| **`specs/SECURITY_MODEL.md`** | **Required before touching any permission rule or field-visibility declaration.** Per-doctype comparison with upstream, the four field tools and when each applies |
| `specs/UNROUTED_DOCTYPES.md` | Doctypes withheld from `/api/resource/`, and why |
| `specs/VERSION_HISTORY.md` | What change history is recorded and pruned. **Read before touching `clear_old_versions`** — its name invites a change that deletes the timeline |
| `specs/KNOWN_ISSUES.md` | Problems that outlive a phase — flaky tests, half-built features. Check before re-diagnosing something |

**Do not start work without reading `PORT_PLAN.md` and your phase spec.** They encode
decisions that are already settled — re-deciding them creates divergence.

## Source of truth

Two repositories, both readable:

```
CRM app    D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm    (main)
framework  D:\02_Personal\01_OpenSource\02_FrameWorks\frappe           (version-15)
```

That pairing is what the CRM's own CI uses — do not read `develop`, it is v16 pre-release.
The framework was unavailable during phases 0–2, and several defects were only findable
in it.

Read them whenever behaviour is unclear. **Never invent semantics** — match the source,
or flag the ambiguity in your report. If something looks impossible, suspect a missing
framework mechanism before suspecting your own code.

**When upstream is wrong** — and it sometimes is; **38 cases** are recorded across the
`UPSTREAM_BUGS_PHASE_*.md` files (1–9 and 36–38 in the `0-2` file, 10–35 in the `3-6`
file, which despite its name now spans phases 3–8) — diverge
only on bugs nothing can observe, and reproduce user-visible ones. Check whether anything
actually reads the field before deciding, and record the choice.

**Security is the standing exception to that rule.** Upstream protects most doctypes with
DocType role permissions, a layer this port does not model, so "upstream registers no
hook" means "upstream had protection we do not". Five findings across four phases came
from reading a missing hook as a missing requirement. `specs/SECURITY_MODEL.md` has the
per-doctype detail and the two questions that settle each case.

## Hard rules

1. The frontend wire protocol (`PORT_PLAN.md` §3) is a fixed external contract. JWT
   auth and the WebSocket transport are the only two sanctioned deviations.
2. Phases 0 and 2 are single-agent. Everything else fans out by cluster/module.
3. No two concurrent agents edit the same file.
4. Preserve `frappe.throw` message text verbatim — it is user-facing copy.
5. Work on a branch, never directly on `main`.
6. **One commit per meaningful change, never one per phase.** An earlier run was told
   "one commit per phase" and produced single commits of 25,000 lines — unreviewable,
   unbisectable, unrevertable. Commit when a coherent piece of work is done and the suite
   is green; a dozen commits in a phase is correct. Each must stand alone, with a message
   saying what changed and **why**.
7. **Registering a doctype publishes it.** Every field is readable, filterable and
   writable through `/api/resource/` unless something says otherwise. Before adding one,
   read the checklist in `specs/AS_BUILT.md` — two tests will fail on you otherwise, by
   design.

## Keep shell commands short

**A long command cannot be security-scanned, so it escalates to human review — which
stalls an unattended run indefinitely.** This has already cost a run. It is not about
what the command does; the harness simply refuses to approve text it could not read, so
no permission rule can pre-approve it. The only fix is to keep commands short.

Long *content* belongs in a file. The command that uses it stays tiny.

**1. Commit from a file, never inline.**

```bash
# Write the message with the Write tool, then:
git commit -F .git/COMMIT_MSG
```

Roughly 35 characters regardless of message length. Do **not** use
`git commit -m "$(cat <<'EOF' … EOF)"` — that puts the whole message in the command, and
these messages run to 2,000 characters.

**2. Never inline a script.** Write `scratch/patch.py`, then `python scratch/patch.py`.
No `python - <<'PY' … PY`.

**3. Never write file contents through the shell.** No `cat > file <<'EOF'`. Use the
Write and Edit tools — that is what they are for, and nothing gets scanned.

**4. Keep any single shell command under ~400 characters.** A blanket backstop for cases
1–3 do not cover. If a command is getting long, something in it belongs in a file.

Chained commands count as one command. Prefer several short calls over one long chain.

## Stack

Django + DRF + SimpleJWT, PostgreSQL 17, Redis, Celery, Django Channels,
django-treebeard (nested-set trees). Python 3.13.

---

# Reviewer policy — three tiers

You write the code; something that does **not** share your blind spots reviews it.
Try these in order, stop at the first that genuinely works, and always tell me which
tier you used.

| Tier | Reviewer | Notes |
|---|---|---|
| **1** | Codex via PowerShell 7 | Preferred — different model, reads the repo itself |
| **2** | Codex via PowerShell 5.1 | Same reviewer, fallback shell |
| **3** | Claude subagent | **Degraded** — same model and same spec, so correlated blind spots |

Full procedure: `docs/internal/RUNBOOK_PHASE_7.md` §3. (`RUNBOOK.md` covered the
phases 3-6 run and is now a record of it.)

## Tier 1 — Codex (default)

- codex-cli 0.147.0, on PATH as `codex`. Auth already configured.
- The interactive TUI needs a live terminal, so you **cannot** drive it. Use
  `codex exec` — headless: prompt in, report to stdout.
- Codex reads the repo itself. Point it at paths; don't paste code in.

```powershell
codex exec -s read-only "<review request>"   # review, cannot touch files
codex exec review                            # built-in review subcommand
codex exec resume --last "<follow-up>"       # continue the same Codex session
codex exec --approve-for-me "<task>"         # only if I ask Codex to make edits
```

## Never trust the exit code

**`codex exec` exits 0 even when it ran nothing.** If the output contains
`CreateProcessAsUserW failed`, `windows sandbox: runner failed`, `SpawnChild`, or Codex
asks you to paste files — the review **did not happen**. Escalate a tier; do not accept
it. Phases 0–2 were reviewed blind this way.

**Give a run up to 40 minutes; do not kill it at 10.** A review that names files and
claims takes anywhere from one to thirty minutes, and a run that is still reading the
right files is not a failure. At the 20-minute mark look at its output so far and tell
the user where it is. Only a run that passes 40 minutes, or one that has wandered off
into unrelated files, is treated as failed: re-run once with a narrower prompt — name
the exact files and the exact claims to check rather than asking it to go looking —
then escalate a tier if that times out too.

## Tier 3 — Claude subagent

Spawn a **fresh** subagent, not a `fork`. A fresh subagent receives only the task
prompt — no conversation history — so it is genuinely context-isolated. A `fork`
inherits the writer's full context including the reasoning that produced the bug, which
is the opposite of a second opinion.

**Why tier 3 is still degraded — and what it is not.** The weakness is *not* shared
context; a fresh subagent has none. It is:

1. **Same model** — same priors and same failure modes. If this model misreads a Frappe
   idiom once, a second instance reading the same code is likely to misread it the same way.
2. **Same inputs** — writer and reviewer read the same spec. When
   `PHASE_0_FOUNDATION.md` wrongly said `field:` PKs are "slugified", both would have
   inherited that error. Codex caught it only by going to the Frappe source instead.

Because the weakness is model correlation, **isolating context further does not help** —
`claude -p` buys nothing over a fresh subagent here. Only a different model does. Use
`claude -p` only if you are yourself a subagent and cannot spawn one.

Tier 3 is weak at finding *different* bugs, not at finding bugs. In phase 0 the writing
agent re-read its own work after Codex signed off and found two real defects Codex
missed, including the most serious one in the phase. Same-model review has real value;
it just covers less new ground.

**Compensate** by pointing tier 3 at the Frappe source rather than the spec wherever
they could disagree, and by adding: *"Assume the author was competent and the obvious
things are right. Look for what a reader who shares the author's assumptions would skip."*

## Always

- Blocking, ~1-2 min per call. Batch reviews rather than pinging after every edit.
- Each `codex exec` is fresh context — use `resume --last` for iterative rounds.
- Report findings to me, including where you disagree. Don't auto-apply them.
