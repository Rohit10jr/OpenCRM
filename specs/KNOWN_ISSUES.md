# Known issues

Things that are wrong, or not yet trustworthy, and are **not** recorded elsewhere.

Not a substitute for the per-phase progress files — those record what a phase built and
what it left. This is for problems that outlive a phase: flaky tests, half-built features,
and anything a future agent would otherwise rediscover the hard way.

| # | Issue | Status |
|---|---|---|
| 1 | A WebSocket test fails intermittently under full-suite load | **Unexplained** — do not paper over |
| 2 | `crm.api.accept_invitation` is not implemented; invitation links 404 | **Open** — phase 8; the security half is disarmed |
| 3 | `Communication`, `File` and `Comment` leak content from records the caller cannot open | **Confirmed, unfixed** — fix specified below |

---

## 1. `test_subscribing_to_a_missing_document_is_refused_the_same_way` fails intermittently

**Where:** `tests/test_phase6_realtime.py:321`

Fails with `TimeoutError` from `asgiref/timeout.py` on
`await communicator.receive_from(timeout=5)`. Passes when run alone, and passed on an
immediate full re-run. Observed twice, weeks apart, both times only under a full-suite run.

**What is known:**

* it is unrelated to whatever change was in flight when it appeared — the test subscribes
  to `CRM Lead` and a nonexistent doctype, and both sightings followed changes that
  touched neither;
* the machine it runs on has been memory-constrained before (PostgreSQL was killed twice
  by `ERROR_NO_SYSTEM_RESOURCES` with 0.2 GB free), so load-dependent timing is plausible;
* the suite runs ~1250 tests in roughly five minutes, and the WebSocket tests are near the
  end, which is where contention would be worst.

**What is not known:** whether the five-second wait is genuinely too short under load, or
whether a previous WebSocket test leaves a connection un-torn-down and this one inherits
the mess. Those want different fixes.

### Do not just raise the timeout

That converts a question into a silence. If the cause is a leaked connection, a longer
wait makes the failure rarer and no less real, and the next person to see it has less
information than we do now.

**How to settle it:** run the full suite ten times and count. Roughly 1 in 20 says slow
machine, and raising the wait is then a legitimate fix with evidence behind it. Anything
like 1 in 3 says the teardown is wrong, and the fix is in `_connect`/`disconnect`, not the
timeout. Ten runs is about an hour of wall-clock and nobody has to watch it.

---

## 2. `crm.api.accept_invitation` was never implemented

**Where:** `crm_app/tasks.py:214` sends the link; nothing serves it.
Upstream implements it at `crm/api/__init__.py:83`.

Inviting a colleague sends an email containing
`/api/method/crm.api.accept_invitation?key=...`. **That URL 404s.** So the invitation flow
is broken end to end: you can invite someone, they receive the mail, and they cannot join.

It is not recorded in any phase's progress file — the endpoint appears to have been missed
rather than deferred. Phase 8 owns auth and desk, so it belongs there.

### The security half is already disarmed

An invitation row carries the **role being granted** and a **`key` that redeems it**, and
upstream redeems by key alone — unauthenticated, with no binding to the caller. Upstream
also lets any Sales User read that table (bug #21), so reading a pending System Manager
invitation is enough to become one.

This port now gates `CRM Invitation` to managers and keeps `key` off the wire entirely
(`crm_app/permissions/platform_docs.py`, `CRMInvitation.SENSITIVE_FIELDS`). Both were put
in place **before** the endpoint exists, deliberately, so that implementing it cannot
quietly open the hole.

**Whoever builds the endpoint:** the protection is already there, so do not remove it to
make redemption easier. Redemption needs the key from the *email*, not from the API.

---

## 3. `Communication`, `File` and `Comment` leak content from invisible records

**Confirmed by driving the real route as a plain Sales User**, against a deal she is
refused. Not yet fixed — this is the top of the A7 backlog.

```
GET /api/resource/CRM Deal/<bob's deal>   -> 403

GET /api/resource/Communication  -> 200  content='We can go down to 400k if they push back.'
GET /api/resource/File           -> 200  file_url='/private/files/signed-contract.pdf'
GET /api/resource/Comment        -> 200  content='Client is desperate, hold firm on price.'
POST /api/resource/Comment       -> 201  (forged onto that same deal)
```

These are the three widest remaining holes, and they are **worse than the record they
hang off**. A deal row leaks a number; its Communications leak the negotiating position in
prose, and its Comments leak what colleagues say to each other privately.

### Severity, stated accurately

* **`Communication` — the worst.** Full email bodies, subjects, senders and recipients.
  Every email ever exchanged about any lead or deal, readable by anyone with a login.
* **`Comment` — read and write.** Reading exposes internal remarks. Writing is the part
  worth noticing: a forged comment appears on a colleague's record under whatever
  authorship the row claims, on a record the author cannot see.
* **`File` — metadata today, documents tomorrow.** The row leaks the filename, the private
  URL and which record it hangs off. **Nothing currently serves the bytes** — there is no
  upload or download route in this port at all (`config/urls.py` has only `admin/` and
  `api/`). So today this is a metadata leak. **The day a file-serving route is added, that
  leaked URL becomes a live document link**, and whoever adds it must check permission at
  the serving layer as well as fixing the row rule.

### The fix, and it is one fix

All three carry `reference_doctype`/`reference_name` (`attached_to_doctype`/
`attached_to_name` on `File`), so the rule is the same in each case:

> **Defer to the referenced document.** Read it if you can read the parent; write it if
> you can write the parent.

Upstream already does exactly this for `File`, and the implementation is directly portable
— our model carries every field it reads:

```python
# frappe/core/doctype/file/file.py:908
if not doc.is_private and ptype in ("read", "select"):
    return True                                   # public files are public
if user != "Guest" and doc.owner == user:
    return True                                   # your own upload
if doc.attached_to_doctype and doc.attached_to_name:
    ref_doc = frappe.get_doc(doc.attached_to_doctype, doc.attached_to_name)
    if ptype in ["write", "create", "delete"]:
        return ref_doc.has_permission("write", user=user)
    return ref_doc.has_permission("read", user=user)
return False
```

Upstream protects `Communication` with a hook too
(`get_permission_query_conditions_for_communication`), but on a **different axis** — it
filters by which email accounts the user owns, not by the referenced document. That suits
a mail client; it does not suit a CRM where the question is "may I see this deal?".
Porting it verbatim would be faithful and wrong here. **Follow `File`'s shape for all
three.**

`Comment` has no hook upstream at all — it relies on the doctype's role permissions, which
grant only System Manager and Website Manager. That is the same "no hook means no
protection" trap as bug #14: upstream had a layer this port does not model.

### Two things to get right

1. **The list route needs `permission_query_conditions`, not just `has_permission`.**
   Deferring per row would be an N+1 across every timeline; the query hook has to express
   "referenced document is visible to me" as a subquery. `org_hierarchy` already builds
   that shape for Leads and Deals and is the thing to reuse.
2. **`get_activities` must keep working.** It already checks read on the parent
   (`_require_readable`) and then reads Comments and Communications over the ORM, so it is
   unaffected by a wire-level rule — but it is the regression to watch, because it is the
   one legitimate consumer of all three.
