# Change history — what is recorded, what is pruned, and where we differ

`Version` rows are the field-change audit trail: one row per save that alters a tracked
field, holding `{"changed": [[field, old, new], ...]}`. The timeline renders them as
*"Alice changed Deal Value from £100,000 to £250,000"*.

Two questions decide everything here, and they have different answers:

1. **Which doctypes record history?** — `TRACKED_FIELDS` on the model
2. **Which history gets deleted?** — `crm_app.tasks.clear_old_versions`, nightly at 00:10

Getting (2) wrong deletes the timeline. This file exists because that nearly happened.

---

## The near-miss worth reading first

`clear_old_versions` is named as though it prunes the audit table. **It does not, upstream
or here.** Upstream deletes exactly one doctype's rows:

```python
# crm/fcrm/doctype/crm_view_settings/crm_view_settings.py:308
frappe.db.delete("Version", {
    "ref_doctype": "CRM View Settings",          # <- only this
    "creation": ("<", add_days(now_datetime(), -days)),
})
```

Its own docstring in this port used to say *"a no-op, and it will stay one until `Version`
is modelled… the day `Version` lands, the body is three lines."* `Version` landed during
the phase-4 review, and the obvious next step — implement it as a general pruner — would
have **silently erased every timeline entry older than 14 days.**

`test_lead_and_deal_history_is_never_pruned` is the guard, written as the failure: a
one-year-old Lead version that the job must not touch.

---

## Which doctypes record history

| Doctype | Upstream | Displayed where? | Us | Why |
|---|---|---|---|---|
| **CRM Lead** | ✅ | timeline | ✅ | The point of the feature |
| **CRM Deal** | ✅ | timeline | ✅ | The point of the feature |
| **CRM Twilio Settings** | ✅ | Desk only | ✅ **added** | Credentials — see below |
| CRM Product | ✅ | Desk only | ❌ | Write-only here |
| FCRM Note | ✅ | Desk only | ❌ | Write-only here |
| CRM View Settings | ✅ | Desk only | ❌ | Pure churn — see below |

### Why upstream records six and we record three

Upstream's activities module has exactly two entry points — `get_deal_activities` and
`get_lead_activities`. **Nothing in the Frappe CRM frontend displays history for the other
four.** They are readable only through Frappe's **Desk**, the generic admin UI, because
`track_changes` is a doctype-level checkbox and the Desk renders history for any document.

**This port has no Desk.** So for Product, FCRM Note and View Settings, recording history
would be data written for a reader that does not exist.

### The exception: `CRM Twilio Settings`

Kept because these are **credentials**, and without a version row a change to them leaves
no trace anywhere in this port. Phase 4's A4 work restricted *who* may write them, which is
what makes *"which manager changed the telephony account, and when"* a question someone
will eventually ask. Upstream can answer it through the Desk; we could not answer it at
all.

**The secrets themselves never enter a version row.** `api_secret` and `auth_token` are
deliberately absent from `TRACKED_FIELDS`: the audit question is *that* a credential
changed, not what it used to be. Recording the old value would put a plaintext secret in a
second table, outside `SENSITIVE_FIELDS` and outside the encryption that A3 added.
`test_the_secret_itself_never_enters_the_version_row` pins it.

### Why not `CRM View Settings`

Saved views are edited constantly. Every column drag, filter tweak and sort change is a
save, and each save would write a row holding **two copies of the full column JSON**. A
minute of adjusting a list view produces about five of them.

Nobody reads the history of a list view — and upstream's own behaviour says so: it is the
one doctype it bothers to delete after 14 days. Recording churn purely so a nightly job can
remove it is cost with nothing on the other side.

**Decided deliberately, not overlooked.**
`test_it_deletes_nothing_today_because_we_do_not_track_saved_views` fails if anyone adds
`TRACKED_FIELDS` to `CRMViewSettings`, and points back here.

### One further narrowing, from phase 3

Even for Lead and Deal, **we record a declared field list where upstream records every
field.** Full parity would mean an extra INSERT on every save forever and a timeline entry
for every corrected typo. `status` is excluded on purpose — it already reaches the timeline
through `CRM Status Change Log`, which additionally carries the duration spent in each
status.

Widening the set is one line per model.

---

## Which history gets pruned

| | Upstream | Us |
|---|---|---|
| Lead / Deal history | **never pruned** | **never pruned** |
| Twilio Settings history | never pruned | never pruned |
| View Settings history | deleted after 14 days | *not recorded, so nothing to delete* |
| Job target | `CRM View Settings` only | `CRM View Settings` only |
| Schedule | daily | daily, 00:10 |

The job is **implemented rather than left as `return 0`**, so its body matches its name and
turning view tracking on later needs no second change. It deletes nothing today, and the
reason is *not* the one the old docstring gave — `Version` exists; we simply never create
the rows it targets.

`VERSION_CHURN_DOCTYPE` is a named constant so the narrowness is visible at the call site
rather than buried inside a filter.

---

## Where we differ from upstream, in one table

| # | Difference | Direction | Reason |
|---|---|---|---|
| 1 | Three tracked doctypes, not six | **less** | Three of upstream's six are visible only through a Desk this port does not have |
| 2 | `CRM Twilio Settings` tracked | **same as upstream** | Credentials; the only audit record in the port |
| 3 | `CRM View Settings` not tracked | **less** | Churn nobody reads, which upstream itself deletes |
| 4 | Declared field list, not every field | **less** | An INSERT per save forever, and a timeline entry per typo |
| 5 | `status` excluded from Lead/Deal tracking | **less** | Already in the timeline via `CRM Status Change Log`, with durations |
| 6 | Secrets excluded from tracked fields | **stricter** | The old value would be a plaintext secret in an unprotected second table |

**Net: we store strictly less than upstream and lose nothing a user can see.**

---

## If you are changing something here

- **Widening the prune** — don't. Read the near-miss above. If a genuine growth problem
  appears, the answer is a retention policy on a doctype whose history nobody reads, not a
  blanket age cutoff across the audit trail.
- **Adding a tracked doctype** — ask what displays it. If the answer is "nothing", the
  Twilio exception is the bar: it earns its place because credentials with no audit record
  are worse than rows nobody reads.
- **Tracking a secret** — no. See difference 6.
