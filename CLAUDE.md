# frappe_django_crm

Porting **Frappe CRM** (Python/Frappe framework) to **Django + DRF**, keeping the
existing Vue frontend.

## What to read, and when

Nothing needs reading for a question, a docs edit or a git task. Before a change, read
the rows that match it — not the whole list. What these files record is settled;
re-deciding it creates divergence. If you think a decision is wrong, say so instead.

| Before you… | Read |
|---|---|
| change any backend behaviour | the section of **`specs/AS_BUILT.md`** for that area: what exists and why |
| touch a permission rule or what fields a user can see | **`specs/SECURITY_MODEL.md`** — required |
| add or register a doctype | the doctype checklist in `specs/AS_BUILT.md`, and `specs/UNROUTED_DOCTYPES.md` |
| touch `clear_old_versions` or change history | `specs/VERSION_HISTORY.md` — its name invites a change that deletes the timeline |
| change the frontend, or what it sends and receives | `PORT_PLAN.md` §3 and `frontend/JWT_PATCH.md` |
| diagnose something that looks broken | `specs/KNOWN_ISSUES.md`, then `UPSTREAM_BUGS.md`: it may be known, or upstream's own |
| change what a phase built, when `AS_BUILT.md` does not say why it is that way | that phase's spec, found through `docs/history/SPECS_README.md` |
| work on an upstream bug or pull request | the entry in `UPSTREAM_BUGS.md` |

## Upstream source: which copy, and when

| Copy | Path | Read | Use it to |
|---|---|---|---|
| **CRM, the port's base** | `D:\02_Personal\01_OpenSource\03_Applications\CRM\crm\crm` | the working tree (tag `port-base`) | see what the port should do: every porting and port-bug question |
| **Framework** | `D:\02_Personal\01_OpenSource\02_FrameWorks\frappe` | `git show version-15:<path>`, never the working tree (it is on `develop`) | explain what the CRM code does not: save, rename, delete, permissions, Data Import |
| **CRM, the owner's fork** | `D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe_crm` | `upstream/develop` | upstream bug work only: does an `UPSTREAM_BUGS.md` entry still exist, and its fix |

* **The port's base is frozen.** The clone is on the owner's `docker-setup` branch; its
  tip, `port-base` (`6583bfcdc`), is upstream v1.82.0 (`48cb3ccce`, 26 Aug 2026) plus
  Docker docs that change no CRM code. Every upstream line number in the specs is from
  it. Never switch its branch or pull.
* **Do not read `develop` for port work,** in either repository: it is v16 pre-release,
  and code read from it has got into the port before (`docs/FINDINGS.md` 90). The fork is
  the only place `develop` is right, because that is where CRM pull requests go. Never
  copy port code from it.
* **Read upstream whenever behaviour is unclear. Never invent semantics** — match the
  source, or flag the ambiguity in your report. If something looks impossible, suspect a
  missing framework mechanism before suspecting your own code.

**When upstream is wrong** — and it sometimes is; **83 cases** are recorded in
`UPSTREAM_BUGS.md` — diverge only on bugs nothing can observe, and reproduce user-visible
ones. Check whether anything actually reads the field before deciding, and record the
choice.

**Security is the standing exception to that rule.** Upstream protects most doctypes with
DocType role permissions, a layer this port does not model, so "upstream registers no
hook" means "upstream had protection we do not". Five findings across four phases came
from reading a missing hook as a missing requirement. `specs/SECURITY_MODEL.md` has the
per-doctype detail and the two questions that settle each case.

## Hard rules

1. The frontend wire protocol (`PORT_PLAN.md` §3) is a fixed external contract. JWT
   auth, the WebSocket transport and the boot-values call (`frontend/JWT_PATCH.md`) are
   the only three sanctioned deviations.
2. *Retired 12 Nov 2026* (phase fan-out: the phases are finished). Numbers are kept
   because code and tests cite rules 4 and 7.
3. No two concurrent agents edit the same file.
4. Preserve `frappe.throw` and `msgprint` text verbatim — it is user-facing copy.
5. Work on a branch, not directly on `main`, unless the owner asks for `main` for that
   change. (Owner, 7 Nov 2026.)
6. **One commit per meaningful change** — never one big commit for a whole piece of work
   (one run made 25,000-line commits that could not be reviewed or reverted). Commit when
   a coherent piece is done and its tests are green; each commit stands alone, with a
   message saying what changed and **why**.
7. **Registering a doctype publishes it.** Every field is readable, filterable and
   writable through `/api/resource/` unless something says otherwise. Before adding one,
   read the checklist in `specs/AS_BUILT.md` — two tests will fail on you otherwise, by
   design.
8. **Keep every difference from upstream visible.** This port is not the final version;
   a later Django rewrite will need the full list of where and why it differs. In code
   copied from upstream, never delete what you replace: keep it commented, prefixed
   `Upstream:`, with a line on why and the finding or `UPSTREAM_BUGS.md` entry; mark new
   code `Port only:`. Record frontend differences in `frontend/JWT_PATCH.md` and
   behaviour differences in the finding and `UPSTREAM_BUGS.md`. (Owner, 17 Oct 2026.)

## Keep shell commands short

The rules are in the global `~/.claude/CLAUDE.md` ("Shell"): a command too long to be
security-scanned waits for a human and stalls the run, so long content goes in a file
and the command stays under ~400 characters. Here that means:

* **Commit messages:** write `.git/COMMIT_MSG` with the Write tool, then
  `git commit -F .git/COMMIT_MSG`. After a Codex build the message is
  `tasks/COMMIT_MSG` instead.
* **Scripts and probes** go in the session scratchpad, then run that file.
* **PR bodies** go in a file, then `gh pr create --body-file <file>`.

## Long runs: the test suite, Codex and subagents

The backend suite (`python -m pytest -q` in `backend/`) outlasts the shell tool's
ten-minute foreground limit, so run it in the background with its output in a log, and
read the log. Run Codex, and any long subagent task, the same way. A single test file is
fast and can run in the foreground. (Owner, 12 Nov 2026.)

* **Never stop a run abruptly**, and never on time alone.
* **Every 15 minutes, look and decide.** Read the log or output so far, tell the owner
  where it is, and judge whether it is still making progress: tests still passing, Codex
  still reading the right files.
* **45 minutes is the upper limit for that routine.** Past it, decide from the result
  and the evidence: what the run has done, whether it is still progressing, and what
  stopping would lose. Stop only a run that is stuck or has wandered into unrelated work,
  and say why. A stuck Codex run is re-run once with a narrower prompt, naming the exact
  files and claims, before escalating a tier.
* **Do not report a result the log does not contain.**

## Stack

Django + DRF + SimpleJWT, PostgreSQL 17, Redis, Celery, Django Channels,
django-treebeard (nested-set trees). Python 3.13.

The frontend loads some framework screens (Data Import among them) from `../../frappe/ui`,
i.e. `D:\02_Personal\01_OpenSource\03_Applications\CRM\frappe`, a junction that must point
at `02_FrameWorks\frappe_ui_v15` (v15.126.0, as CI), not the `develop` checkout:
`develop`'s screens import `FeatherIcon`, which frappe-ui 1.0 dropped, and the app
crashes after login. If `yarn dev` or a build reports a missing frappe-ui export, check
the junction first. (Repointed 9 Nov 2026.)

---

# Codex (see the codex skill)

**Builder mode is in force here (owner, 15 Oct 2026):** Codex writes the code from
briefs in `tasks/`; Claude plans, reviews and commits, and does not write feature code
itself. Codex's side of the contract is `AGENTS.md` "When building".

- A brief also names the finding, the upstream files and lines (framework via
  `git show version-15:<path>`), and the records to update.
- Run builds with `network_access=true`, which is what lets tests reach PostgreSQL.
  Codex leaves its commit message in `tasks/COMMIT_MSG`.
- Reviews of anything Claude writes use the skill's three tiers. For tier 3, point the
  subagent at the Frappe source rather than the spec: a wrong spec misleads writer and
  reviewer alike (`PHASE_0_FOUNDATION.md` once called `field:` PKs "slugified").
