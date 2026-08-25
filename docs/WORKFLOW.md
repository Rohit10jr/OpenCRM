# How work is handed to an agent

**A portable version of the process this repo arrived at over eight phases.** It is written
to be copied into another project: replace the examples, keep the shape.

Everything here was assembled from failures. Nothing in it was designed up front, and the
section at the end — [What this cost](#what-this-cost-to-learn) — gives the commit dates, so
you can see which parts are load-bearing and which are decoration.

---

## 1. The shape

Every planning document does exactly **one** of six jobs. If a file does two, split it; if it
does none, delete it.

| Role | Job | Written | Changes |
|---|---|---|---|
| **Standing rules** | Rules that hold for every unit of work | Once, day 1 | Rarely |
| **The plan** | Inventory, contracts, settled decisions | Once, day 1 | Almost never |
| **Unit spec** | *What* to build for one unit | Up front, all units | Revised as reality lands |
| **Living state** | What is *actually* true now | Grows with each unit | Constantly |
| **Handoff** | *How* to run this one unit | Fresh, each unit | Per unit |
| **Agent output** | What the agent understood, and what it did | By the agent | Never edited after |

A "unit" is whatever you hand over in one go: a phase, a milestone, a timeboxed run.

### Give every spec a status, and flip it

Specs written up front are guesses. Mark them **Provisional**, and **flip the header to
Authoritative when that unit's gate passes.** A spec still claiming to be provisional after
its unit shipped is worse than no status at all — the reader cannot tell which half of the
folder to trust, so they trust none of it.

Keep the statuses in one index (`specs/README.md`), so the folder can be read at a glance.

### The file layout

```
CLAUDE.md                      standing rules  (auto-loaded by Claude)
AGENTS.md                      standing rules  (auto-loaded by Codex — reviewer brief)
PLAN.md                        the plan
specs/
  README.md                    index + status of every unit spec
  AS_BUILT.md                  living state — WHAT EXISTS. authoritative
  <UNIT>.md                    one spec per unit
docs/
  WORKFLOW.md                  this file
  TASK.md                      the entry point. one line of substance
  RUNBOOK_<UNIT>.md            the handoff for the unit now running
  ORIENTATION_<UNIT>.md        written by the agent BEFORE any code
  PROGRESS_<UNIT>.md           written by the agent AFTER the gate
```

---

## 2. The precedence rule

**This is the load-bearing part.** Without it, specs written on day 1 become lies by unit 5
and the agent has no way to know which sentence to believe.

Write it down in every document it governs, not once:

> Where a spec and `AS_BUILT.md` disagree, **`AS_BUILT.md` wins** — the specs were written
> first.
>
> Where `TASK.md` and the runbook disagree, **the runbook wins**.
>
> Where a document and the source disagree, **the source wins.** Read it. Never invent
> behaviour.

With this rule, stale specs are survivable. Without it, every stale sentence is a live trap,
and you will spend more time reconciling documents than writing code.

---

## 3. The handoff chain

```
  TASK.md  ──►  RUNBOOK_<UNIT>.md  ──►  Step 0  ──►  work  ──►  gate  ──►  PROGRESS_<UNIT>.md
   (stable       (rewritten            (agent                  (review)     (agent writes,
    name)         each unit)            writes                               human reads
                                        ORIENTATION)                         first)
```

### `TASK.md` is a stable filename, not a document

Its entire job is to let the terminal prompt stay identical forever:

```
Read docs/TASK.md and follow it.
```

It says which runbook to read, gives the repo path and branch, and states the precedence
rule. Everything else it contains is a summary that the runbook restates properly. **Keep it
under ~100 lines.**

### The runbook supersedes, but inherits

Each unit gets a fresh runbook. It does **not** copy forward the permanent lessons — it
points at them:

> Supersedes `RUNBOOK_<PREV>.md`. **Step 0 and "How to work here" in that file still
> apply** — read them there; they are not repeated here.

Copying them forward means they drift, get re-worded, and quietly lose their sharpest
clause. Pointing at them means the permanent rules have exactly one home.

The runbook is therefore only the **delta**: this unit's scope, this unit's already-settled
decisions, this unit's traps, this unit's review prompt.

### The bookends

The single highest-value practice here. The agent writes a file **before** code and a file
**after**.

**Before — `ORIENTATION_<UNIT>.md`.** Read the listed documents, then write down what you
understood, *including what you think is stale or wrong*. It is not paperwork:

> The two most expensive bugs of the last review both came from an agent (and later, a
> human) trusting a sentence that had quietly stopped being true.

In this project, orientation caught **4 stale claims** before one unit and **5** before the
next. Each was a document that had been true when written.

**After — `PROGRESS_<UNIT>.md`.** Fixed sections, and one of them matters more than the rest:
*Concerns — what I am unsure about*. A review found **eight** security holes by pulling
threads a progress file left dangling. That file was useful *because* it admitted its gaps.

---

## 4. The gate

Mechanical, checkable, no "close enough". Adapt the items; keep the property that **every one
is either true or false without argument**.

1. **Tests pass.** Full suite, nothing skipped or weakened.
2. **Migrations / build clean** from an empty state.
3. **Independent review** — see §5. State which tier ran.
4. **Commits** — one per meaningful change, each standing alone with a green suite.
5. **Walk the thing yourself, and say how.** Not a script. The real interface, by hand.

Item 5 exists because this project shipped the same failure **three times in two units**: a
green suite and a passing end-to-end script over code that nobody had exercised through the
actual UI. *"Every backend test passed. The end-to-end walk passed 26 of 26 steps. Neither
runs a browser."* Write your own version of that sentence into the gate, naming your own
near-miss — a generic "please test it" does not survive contact with a deadline.

### Fail-stop

> **If the gate fails twice on the same unit, STOP.** Write down what failed, the actual
> error, what you tried, and your best read of the cause. Then halt.
>
> Do not work around a failing gate. Do not skip ahead. **Do not disable or weaken a test to
> make it pass** — that is the worst available outcome, because it hides the failure instead
> of reporting it.

Then a **concrete trade, re-costed for the unit at hand**. This is the part that actually
carries the rule; the abstract instruction erodes with every rewrite, the trade does not:

> *"A clean stop with three integrations landed is far more useful than five unverified
> ones."*
> *"Login working and password reset half-built, honestly reported, beats four screens
> nobody has walked."*

---

## 5. Independent review — the tier ladder

The point is a reviewer that **does not share the writer's blind spots**. Try in order, stop
at the first that genuinely works, and **record which tier ran** — a unit reviewed at tier 3
has had a weaker check and the reader must be able to tell.

| Tier | Reviewer | Strength |
|---|---|---|
| **1** | Codex (different model), reading the repo itself | **Preferred** |
| **2** | Same reviewer, fallback shell | Equivalent, worse ergonomics |
| **3** | Fresh subagent, same model | **Degraded** |

**Why tier 3 is degraded, precisely.** A fresh subagent does not carry the writer's context —
that part is fine. The weakness is that it shares the writer's **model** (same priors, same
failure modes) and its **inputs** (the same spec). When a spec was wrong about a framework
detail, only the different model caught it, by reading the framework source instead of
trusting the sentence. Since the weakness is model correlation, isolating context further
buys nothing. Only a different model does.

**Degraded is not useless.** Tier 3 is weak at finding *different* bugs, not at finding
bugs. In one unit here the writing agent re-read its own work *after* the tier-1 reviewer
signed off, and found two real defects it had missed — including the most serious one in the
phase. Same-model review covers less new ground; it still covers ground. **A reviewer
signing off is not a reason to stop looking.**

If you land on tier 3, add one instruction the other tiers don't need:

> *"Assume the author was competent and the obvious things are right. Look for what a reader
> who shares the author's assumptions would skip."*

### Two mechanics that make this work

**Pre-write the review prompt in the runbook.** Do not make the running agent compose it —
it will write a prompt shaped by the same understanding that produced the code. Name the
specific files and the specific claims to check.

**Never trust the exit code.** `codex exec` exits 0 having run nothing; a spawn failure is
reported to the model, not the process. Treat the review as **FAILED** if the output contains
any of `CreateProcessAsUserW failed`, `windows sandbox: runner failed`, `SpawnChild`,
`I couldn't complete the review`, or if the reviewer asks you to paste files in. Also fail it
if it does not return in ~10 minutes: re-run once with a **narrower** prompt, then escalate a
tier. **A review that never returned is not a review that passed.**

**Act on findings.** Fix what is real. Where you disagree, record the disagreement and the
reasoning — never silently ignore it, and never apply a fix you believe is wrong to make a
reviewer happy.

**Say whether the agent may act on them, and be consistent.** This project's standing rules
said *"report findings to me, don't auto-apply them"* while the runbook said *"act on the
findings"* — correct for an attended session and an unattended run respectively, and a
straight contradiction to an agent reading both. An orientation file caught it and followed
the runbook. Decide per mode, and make the runbook say which mode it is written for.

---

## 6. How to work here — the permanent rules

Nine rules. **Each one is a bug that shipped.** They are not style preferences, and the
section only grows when something actually goes wrong — that is what keeps it readable.

1. **Verify the premise before following an instruction.** A docstring said *"the day
   `Version` lands, the body is three lines."* `Version` landed. Following it would have
   silently deleted every timeline entry older than 14 days. **A document is evidence, not
   proof.** When an instruction tells you to do something, check that the reason it gives is
   still true.

2. **A claim you write will be trusted.** A progress file said a workaround *"is deleted."*
   It was not — it was still serving three endpoints. Before you write "X is done", check
   that X is done. Before you write "nothing uses Y", grep for Y.

3. **Verify a test fails without the thing it tests.** A test asserting a disabled user could
   not re-enable themselves **passed with the mechanism removed** — the account was rejected
   earlier, so the test never reached its own subject. For anything load-bearing: remove the
   mechanism, confirm the test fails, put it back. One minute, and it is the difference
   between a test and a decoration.

4. **Record what you did not check.** **A gap you record is a decision. A gap you omit is a
   bug someone finds later.** The most useful documents in this project are the honest ones.

5. **Investigate before applying a pattern.** Three near-identical cases got three different
   correct answers. Deciding by resemblance would have got two of the three wrong. Two cheap
   questions usually settle it — cheaper than designing a rule.

6. **Measure rather than assert.** *"Connections are being reused"* was verified by watching
   the process ID across six calls. *"The flaky test is rare"* was verified by running the
   suite six times and counting. If a claim can be measured in five minutes, measure it.

7. **Do not widen scope silently.** While fixing a flaky test, a real production problem
   surfaced. It was **recorded first and applied as its own decision**, not folded into the
   flake fix. Changes that arrive as a side effect of something else are how nobody remembers
   deciding.

8. **Update the document in the same commit as the code.** Every stale claim in this project
   was true when written. Nobody wrote them to mislead — they changed the code and left the
   sentence behind. If your change makes a sentence somewhere false, fix the sentence in the
   same commit. **Cheapest rule here, and it has cost the most.**

9. **When you disagree with a review finding**, record the disagreement and your reasoning.
   Never silently ignore it, and never apply a fix you believe is wrong.

### The promotion rule — read this if you take nothing else

**A rule survives only by being moved into the always-loaded file.** The runbook is
disposable by design; the next unit is told to skip it. Anything meant to outlive the unit
must be promoted to `CLAUDE.md` / `AGENTS.md` **before the unit closes.**

In this project, exactly one rule made that jump — *"one commit per meaningful change"* — and
it travelled with its origin story attached, which is why it stuck. The nine above stayed in
a per-unit runbook, and when the work moved to a new area they were left behind: the only
copy sat in a file the new context was explicitly told not to read.

**Commits, since that is the rule that earned promotion:** one per meaningful change, never
one per unit. An earlier run here was told "one commit per phase" and produced single commits
of ~5,000 lines each — unreviewable, unbisectable, unrevertable. A dozen commits in a unit is
correct.

---

## 7. Resolving ambiguity, and being wrong well

The rules in §6 are about not shipping a mistake. These are about what to do when the
answer genuinely is not written down anywhere.

### The ladder — work down it, do not skip to the bottom

1. **Read the source you are porting or integrating with.** It is the truth and it is right
   there.
2. **Read the layer underneath it.** The framework, the library, the platform. Several
   defects in this project were *only* findable one level down, in code nobody thought to
   open.
3. **Read the consumer.** What does the caller expect back? The existing client is a
   specification nobody wrote down.
4. **Choose the option that matches existing behaviour, implement it, and log the decision.**

**Never invent semantics to make something easier.** If a choice would be expensive to
reverse and the evidence is genuinely ambiguous, prefer to stop and ask over guessing — log
it and halt. That is a legitimate outcome; a guess baked into a contract is not.

### When the thing you are porting is wrong

It sometimes is. The rule that governed every divergence here:

> **Diverge on bugs nothing can observe. Reproduce bugs that are user-visible.**

Before diverging, **check whether anything actually reads the field or behaviour.** One
field was corrected because nothing read it; an odd guard was faithfully reproduced because
users see the result. Record either choice **in the code, with the source line**, and add an
entry to the divergence register.

### When something looks impossible

**Suspect a missing mechanism before suspecting your own code.** A feature of the framework
had never been ported, and the symptom — "converted records have a contact but no email" —
looked like a conversion bug for an hour. Check whether the thing you are reimplementing
already exists one layer down.

### Suspect your tools

An inspection script silently truncated a field at 50 characters, and the agent transcribed
the visible prefix without noticing. Three option lists shipped wrong. **When the data looks
odd, check the thing that showed it to you before you check the data.**

### What your own tests cannot catch

Across four units here, the same defect class surfaced four times in four disguises, and an
independent reviewer found every one. The writer's summary is worth quoting:

> *"In every case my own tests passed, because they tested the endpoint I had just written."*

Your tests cover what you wrote. They cannot cover what you forgot to write. That is not a
discipline problem and more testing does not fix it — it is the argument for §5, and it is
why a recurring defect class should be named **once, in a durable place**, the moment you
notice it repeating.

---

## 8. Running unattended

Everything above assumes nobody is watching. Four things make that work.

### Do not idle

The stated failure mode is stalling, not moving too fast. §4's fail-stop is about a *failing
gate* — it is not permission to stop when the work gets awkward.

- **Fan out where the work is independent.** Never two agents in one file; several files at
  once is fine.
- **Blocked on one piece? Move to another.** Do not serialise on a parkable question.
- **Never wait on an external service.**
- **Do not re-litigate settled decisions.** Log the disagreement and keep going.
- **When a gate passes, start the next unit immediately.** The gate exists to keep the work
  honest, not to provide a stopping point.

### Keep commands short

**A long shell command cannot be security-scanned, so it escalates to human review — which
stalls an unattended run indefinitely.** This has already cost a run here. It is not about
what the command does; the harness refuses to approve text it could not read, so no
permission rule can pre-approve it.

**Long content belongs in a file; the command that uses it stays tiny.** Write the commit
message with a file tool and `git commit -F <path>`. Write the script to a file and run the
file. Never pipe a heredoc into anything.

### Say what is already set up, and forbid reconfiguring it

Put an explicit *Environment* block in the runbook: which services are running, which
database, which credentials file, where the reference sources live. Then: **do not
reconfigure it.** Without that block an agent will spend its first hour rebuilding a working
environment.

### If a reviewer cannot see it, it did not get recorded

One runbook obliged the agent to log every divergence in a register that was **gitignored**.
The orientation file caught it: *"a standing obligation to record every divergence in a file
that is never committed and that a reviewer cannot see."* The agent complied *and* mirrored
each entry into the tracked progress file.

Anything you require an agent to record must live somewhere a reviewer will actually read.

---

## 9. Skeletons

Copy these five files. Replace `<UNIT>` and the bracketed prompts.

### 9.1 `docs/TASK.md`

```markdown
# TASK — Start Here

Read `docs/RUNBOOK_<UNIT>.md` and follow it exactly. Where anything in this file
conflicts with it, the runbook wins.

    Repo:   <absolute path>
    Branch: cut <branch> from <base>   [and why that base, if it is not obvious]
    State:  <what is already done and merged; test counts>

## Step 0 comes before any code

The runbook opens with **Step 0: read the recorded reasoning, then write
`docs/ORIENTATION_<UNIT>.md`** saying what you understood — including **what you think is
stale or wrong** in what you read.

Do not skip it, and do not treat it as paperwork. The section where you disagree with the
documents is the one most likely to be worth reading.

The runbook also carries **"How to work here"** — <N> rules, each one a bug that shipped.
Read them before starting, not after your first review round.

## Read first, in this order

1. `specs/AS_BUILT.md` — what already exists. **Read this before writing any code.**
2. `CLAUDE.md` — project rules and the reviewer policy
3. `PLAN.md` — inventory, contracts, settled decisions
4. `specs/<UNIT>.md` — the spec
5. `specs/KNOWN_ISSUES.md` — problems that outlive a unit

`AS_BUILT.md` is first because the single biggest time-waster available to you is
rebuilding something that already exists.

## What to run

<the scope, as a table. and what is NOT in scope.>

Progress file: `docs/PROGRESS_<UNIT>.md`.

## The decisions are made — do not re-open

<list them, short. point at the spec for the full reasoning.>

## Commits

**One commit per meaningful change**, never one per unit. Commit when a coherent piece of
work is complete and the suite is green. A dozen or more commits is correct.

## The gate

<the five items, short. the full version is in the runbook.>

Fail twice on the same gate → write up what happened and **stop**.

## What the human will read first

`docs/PROGRESS_<UNIT>.md`. Make it scannable, and **write down what you are unsure about**.
```

### 9.2 `docs/RUNBOOK_<UNIT>.md`

```markdown
# Unattended Run — <UNIT>

**You are running without a human available. Read this whole file before starting.**

Supersedes `RUNBOOK_<PREV>.md`. **Step 0 and "How to work here" in that file still apply**
— read them there; they are not repeated here.

---

## Scope

<a table: what, from where, roughly how big, behind which flag>

## HARD STOP

**After this unit's gate passes, STOP.** Do not start the next one — <why it needs a human
decision>.

## Decisions the human has already made

Do not re-open these.

1. **<decision>.** <one line of reasoning, so the agent can tell when it does not apply.>
2. ...

## Environment — prepared. Do not reconfigure it

<services and ports, database name, where credentials live, where the reference sources
are and which branch/version of each. without this block the agent spends its first hour
rebuilding a working environment.>

## What is already built for you

<a table of existing helpers and seams, with paths. this section prevents the single most
expensive failure mode: rebuilding the layer underneath you.>

## The rules that govern this unit

<from the spec's acceptance criteria. these are criteria, not advice.>

---

## Step 0 — Understand what exists, and write down what you found

**Before writing any code.** Not a formality: an agent that skips this rebuilds a layer
that already exists, or trusts a document that has gone stale.

Read, in this order:

| # | File | What you are looking for |
|---|---|---|
| 1 | `specs/AS_BUILT.md` | What exists |
| 2 | ... | ... |

Then **write `docs/ORIENTATION_<UNIT>.md`** before starting. Six sections — the skeleton is
in `docs/WORKFLOW.md` §9.3.

---

## How to work here

<only if this is the first runbook. otherwise it lives in the previous one and you point at
it. see WORKFLOW.md §6 for the nine rules.>

---

## The loop

    1. Read specs/<UNIT>.md in full
    2. Implement it
    3. Write tests for its acceptance criteria — real tests, not assertions of intent
    4. Run the gate
    5. Gate passes → commit, write PROGRESS_<UNIT>.md
       Gate fails  → fix, re-run the gate (ONCE)
       Fails twice → STOP. Log and halt.

Fan out where the work is independent. **Never two agents in one file.**

## The gate

<the five items in full, with the exact commands to run>

### Independent review — three tiers

<the ladder, plus THE PRE-WRITTEN PROMPT FOR THIS UNIT, plus the failure strings>

## Fail-stop

**If the gate fails twice, STOP.** Write to `docs/PROGRESS_<UNIT>.md`: what failed, the
actual error, what you tried, your best read of the cause. Then halt.

Do not work around a failing gate. Do not skip ahead. **Do not disable or weaken a test.**

<the concrete trade, re-costed for this unit>

## `PROGRESS_<UNIT>.md`

<the template — see WORKFLOW.md §9.4>

## Two standing obligations

- **Record every divergence** in <register>, continuing from **#<N>**
- **Keep `specs/AS_BUILT.md` current** as you add shared helpers — it is what the next unit
  reads first
```

### 9.3 `docs/ORIENTATION_<UNIT>.md` — written by the agent, before code

```markdown
# Orientation — <UNIT>

Written after reading the documents listed in the runbook's Step 0, before any code.

## 1. What exists that I must not rebuild

<name the helpers and seams, with paths.>

## 2. The mechanisms, in my own words

<explain the core machinery back, and when each part applies. if you cannot, say so —
that is section 4.>

## 3. What I believe is stale or wrong in these documents

<the point of the exercise. every claim you checked and found false, with evidence.
an empty section here means you read passively.>

<include your own starting instructions in what you check. one orientation here found
that TASK.md said to branch from `main`, while the runbook it was told to follow lived
on a prep branch carrying six commits `main` did not have -- including the runbook
itself and a test the runbook said would fail on it. branching as instructed would have
silently discarded both. the handoff is a document like any other.>

## 4. What I do not understand yet

<name it now, cheaply, rather than guessing later and expensively.>

## 5. Risks I see in this unit specifically

## 6. Plan

<the order you intend to work in, and why.>
```

### 9.4 `docs/PROGRESS_<UNIT>.md` — written by the agent, at the gate

```markdown
# <UNIT> — <PASS | FAILED | STOPPED>   [branch: <name>]
Started: <time>   Finished: <time>   Commits: <n>

**Built:** 2-3 lines on what actually landed.

**Tests:** <count> passing (from <count>). Any acceptance criterion NOT covered by a test,
named.

**Review — tier <1 | 2 | 3>:** which reviewer actually ran, and why that tier (if not 1,
what failed). What it raised, what you fixed, what you disputed and why. If tier 3, say
plainly that this unit had a weaker check.

**How I checked — gate item 5:** what you exercised by hand, and how. Name what the
automated tests could not have caught.

**Decisions made without you:** every judgment call taken in the human's absence. What you
chose, and the evidence.

**Deviations from spec:** anything built differently, and why.

**Not done — named, not hidden:** what you left out. A gap you record is a decision.

**Concerns — what I would look at first with another hour:** be honest. **This is the most
valuable section**, and an empty one is not credible — it reads as a shallow review rather
than clean work.
```

### 9.5 `docs/FINAL_REPORT.md` — once, at the end of a multi-unit run

A progress file covers one unit. When a run spanning several units ends — or stops early —
one more file gathers what no per-unit file can show: the pattern across them.

```markdown
# Final report — <units covered>

1. **What landed** — per unit: branch, commit SHAs, test counts.
2. **What was attempted and not finished**, and exactly where it stopped.
3. **Every skipped or unrun test**, with what it would need to run. Distinguish
   *skipped* (guarded, deliberate) from *never executed* — they are not the same and
   only one of them is honest by default.
4. **Every decision taken without the human**, gathered in one place. Split into
   "read from the source" and "deliberate deviation, with reason".
5. **Which review tier each unit actually got.**
6. **The recurring lesson** — the defect class that surfaced more than once, in
   different disguises. State it plainly, in one sentence, for whoever continues.
7. **For a human, before this continues** — ordered by how much you want it looked at.
8. **What the next session should tackle first.**
```

Item 6 is the one a per-unit file structurally cannot produce. In this project it was:
*"a doctype's endpoints are not its attack surface — the generic route is"*, and naming it
once was worth more than the four individual fixes.

---

## 10. Adopting this in a new repo

You do not need thirteen documents. You need the **roles**. Minimum viable version:

1. **`CLAUDE.md` + `AGENTS.md`** — standing rules, and a reviewer brief for the other model.
   Same repo, two entry points, so the reviewer arrives already knowing the rules.
2. **One plan file** with settled decisions and an explicit *do not re-open* list.
3. **One living-state file** doing `AS_BUILT.md`'s job, **with the precedence rule written
   inside it**.
4. **`TASK.md` → `RUNBOOK_<UNIT>.md`** per unit.
5. **The bookends** — orientation before, progress after, each with a mandatory *what I think
   is wrong* / *what I did not check* section.

Then, in order of how much they are worth:

| Practice | Why it pays |
|---|---|
| The precedence rule | Makes stale documents survivable instead of fatal |
| Orientation before code | Caught 4 and 5 stale claims in two consecutive units |
| The honest section | One dangling thread led to eight security findings |
| A different-model reviewer | Found defects the same model could not, repeatedly |
| One commit per meaningful change | The alternative is unreviewable |
| Promote rules before the unit closes | Otherwise they die with the runbook |

### Two things to get right on day 1

**Name the honest sections in the template, not in prose.** "Be honest about gaps" is
ignorable. `**Not done — named, not hidden:**` as a required heading is not.

**Prefer a category over a virtue.** Late in this project the "record what you did not check"
rule was replaced, for a timeboxed run, by three states every item must be labelled with:

> **`verified`** — exercised by hand. It works
> **`renders`** — builds and runs, not exercised end to end
> **`written`** — code exists, never run

That is strictly better. A category you are forced to pick beats a virtue you are asked to
remember, and it makes an optimistic report visibly wrong instead of merely generous.

---

## What this cost to learn

The workflow was **not** designed up front. It was assembled from failures, and the commit
history shows exactly when each piece was bought:

| When | What happened | What it produced |
|---|---|---|
| Day 1 | Plan + all unit specs + `CLAUDE.md` + `AGENTS.md` in one commit | The whole process was three files |
| Day 1 | *"Add unattended run runbook"*, then *"Add TASK.md as the run entry point"* | The two-file handoff |
| Day 2 | Specs had started rotting | **`AS_BUILT.md` is born** — the living-state layer |
| Days 2–3 | Four units ran, **one commit each**: ~5,000 lines, ~25 files apiece | Unreviewable. The bill arrives later |
| Days 4–7 | 30+ small remediation commits after review | `SECURITY_MODEL`, `KNOWN_ISSUES`, and two more state files — **all byproducts of findings, none planned** |
| Day 8 | *"…and fix the instruction that caused big commits"*, then *"Make the agent orient before coding, and write down the rules this cost us"* | **Step 0, the nine rules, and per-change commits — all at once, all as fixes** |
| Day 8+ | Next two units: **14 commits** and **9 commits**, both tier-1 reviewed | The process, working |

If you are starting a new project: take §2, §3 and §9 on day 1, and let §6 grow one rule at a
time as things go wrong. A rules list written before anything has broken is a style guide,
and it will be skimmed like one.
