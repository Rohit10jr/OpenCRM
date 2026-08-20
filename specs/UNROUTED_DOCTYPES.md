# Doctypes withheld from `/api/resource/`

Registering a model publishes it. `@register_doctype("X", routable=False)` withholds the
generic REST route while leaving everything else — the model, its permissions, every
internal caller — untouched.

**This file is the record of which, and why.** Read it before adding a flag, and before
removing one.

| Doctype | Since | Why | Anything call it? |
|---|---|---|---|
| `ToDo` | phase 4 review | Assignment rows grant record access; a writable route let any user grant themselves | No — frontend uses `assign_to.add` |
| `Version` | phase 4 review | Audit rows carry old and new values, so the trail leaked the money on records the caller is refused | No — timeline uses `get_activities` |

Enforced by `tests/test_unrouted_doctypes.py::test_the_unrouted_set_is_exactly_what_we_intend`,
so the table above and the code cannot drift apart.

---

## Why a flag, and not commented-out code

The obvious way to disable one doctype's route is to comment it out. **There is nothing
to comment.** `/api/resource/<doctype>` is a single pair of views — `ResourceListView`
and `ResourceDetailView` in `frappe_core/views.py` — serving all 38 routable doctypes off
a registry lookup. Commenting out `post()` removes create for *every* doctype.

So the exclusion has to be data. Given that, a flag beats commented code on the one axis
that matters later:

> **A flag is testable.** `test_every_verb_is_404` fails the moment the route returns.
> Commented-out code cannot be tested, rots silently as signatures change around it, and
> can be uncommented by accident with nothing to catch it.

It is also reversible in one word, and the reason sits at the registration site where
somebody re-enabling it will actually look.

## Why not just delete the doctype

`ToDo` is load-bearing. `org_hierarchy` queries it on every list and every read of a Lead
or Deal; `_assign` is a cache of it; `assign_to.add` writes it. Only the **HTTP route** is
unwanted. `routable=False` removes exactly that and nothing else.

## 404, not 403

An unrouted doctype answers with the same error as a doctype that does not exist. A
prober therefore cannot enumerate which doctypes are registered by reading the difference
between "forbidden" and "unknown". Child tables have answered this way since phase 1; this
follows the precedent.

---

# `ToDo` — the full reasoning

## Short version

`org_hierarchy` grants access to a Lead or Deal when a `ToDo` row says you are assigned to
it. `ToDo` had no permission rule, so any authenticated user could `POST /api/resource/ToDo`
a row assigning themselves to any document — and then read it. Nothing in the frontend
calls that route, so it is withheld.

## What made it worse than an ordinary permission bug

**The permission check was never bypassed. It passed.**

By the time the second request arrived, the caller genuinely *was* assigned to that deal,
so the system answered correctly. No denial, no exception, nothing unusual in a log. The
check was working perfectly on data the attacker had supplied.

That is why no existing test caught it. Phase 2 tested the permission rules — they pass.
Phase 3 tested `assign_to.add` — it is properly gated. Both were testing the front door,
which is locked. Nobody tested whether the table underneath had its own door.

## The exploit, as observed

Alice is a plain **Sales User**. Bob is a rep on another team. Run against the real HTTP
route with a genuine JWT, before the flag:

```
GET  /api/resource/CRM Deal/CRM-DEAL-2026-00001        → 403
GET  /api/resource/CRM Deal                            → 0 rows

POST /api/resource/ToDo
     {"allocated_to": "alice@example.com",
      "reference_type": "CRM Deal",
      "reference_name": "CRM-DEAL-2026-00001"}         → 201 Created

GET  /api/resource/CRM Deal/CRM-DEAL-2026-00001        → 200
     deal_value: 4242424
```

Deal names are sequential (`CRM-DEAL-2026-00001`, `00002`, …), so this walks the whole
pipeline one row at a time. `DELETE` was ungated by the same route, so the assignment
could be removed after reading.

Pinned as `test_a_user_cannot_self_assign_their_way_into_an_invisible_deal`, written as
the attack so it fails loudly if the route returns without a rule.

## Upstream has this too

Recorded as `UPSTREAM_BUGS_PHASE_3-6.md` #16. Five guards could have stopped it upstream
and none does:

| Guard | What it actually does |
|---|---|
| `todo.json` permissions | Role **`All`**: `create/read/write/delete = 1` |
| `todo.py:163` `has_permission` | Non-System-Manager falls through to `doc.allocated_to == user` — **true when self-assigning** |
| `todo.py:38` `validate()` | Builds the assignment message. Never looks at the reference document |
| Link validation (`base_document.py:830`) | `frappe.db.get_value(doctype, docname, "name")` — existence only, no permission |
| REST create (`api/v1.py:43`) | `frappe.new_doc(doctype, **data).insert()` → `check_permission("create")` only |

And `crm/permissions/org_hierarchy.py:41` reads the table the same way we do —
`Todo.allocated_to == user` grants `Todo.reference_name`.

**The root cause is a conflated table.** Upstream `ToDo` serves two purposes: a personal
task list, which every user must be able to write, and assignment records, which grant
access and must be privileged. One table, one permission setting, and the permissive
purpose wins.

Frappe CRM does not even use the first purpose — CRM tasks are a separate doctype,
`CRM Task`. The permissive default is inherited from Frappe Desk, which this port has no
equivalent of, so nothing here justifies it.

**Traced in source, not executed.** Every step above was read from
`frappe` (`version-15`) and `crm` (`main`); no Frappe instance was run, because this
machine cannot run one — which is why the port exists. Worth a two-minute confirmation if
an instance ever comes up.

## Divergence from upstream

Upstream posts a comment to the document's timeline when an assignment is created
(`todo.py:65`, `add_assign_comment`) — *"Alice self assigned this task"*. Our port
refreshes `_assign` but does **not** post that comment, so an assignment made here leaves
one trace where upstream leaves two.

That gap is unrelated to this fix and survives it. Worth closing, because visibility is
the only thing that limited the damage in either codebase.

---

# The alternative: a permission rule

Kept here in full so that publishing `ToDo` again does not mean re-deriving it. **This is
the right answer for any doctype the frontend does use** — un-routing only works because
nothing calls this one.

Register it the way `crm_app/permissions/metadata_docs.py` registers its three, and write:

```python
def todo_has_permission(doc, ptype="read", user=None):
    # The write path is the whole point: a ToDo that points at a document grants access
    # to it, so creating one must require the permission that assign_to.add requires -
    # write on the referenced document.
    if ptype in ("create", "write", "delete"):
        if not doc.reference_type or not doc.reference_name:
            return True          # a personal task, referencing nothing, harms nobody
        return permissions.check_object_permission(
            registry.get_entry(doc.reference_type).model._default_manager.get(
                pk=doc.reference_name
            ),
            "write",
            user,
        )
    # Read: upstream's rule verbatim (todo.py:163) - your own ToDos only.
    return doc.allocated_to == user or doc.assigned_by == user


def todo_query_conditions(doctype, user=None):
    # Upstream's todo.py:148. System Manager sees all.
    return Q(allocated_to=user) | Q(assigned_by=user)
```

Two things to get right, both easy to miss:

1. **`create` must be checked against the *referenced* document, not the ToDo.** An
   unsaved ToDo passes any check applied to itself — that is what made the original hole
   invisible.
2. **Write and read are the same thing at row level in this port.** `org_hierarchy`
   (`_has_permission`, upstream line 91) runs the same visibility query for every `ptype`
   other than `create`. So "can write the deal" reduces to "can see the deal". Do not
   assume a stricter write check exists to lean on.

## To re-enable the route

1. Delete `routable=False` from the registration in `frappe_platform/models.py`
2. Add the rule above
3. Remove `ToDo` from `UNROUTED` in `tests/test_unrouted_doctypes.py` and from the table
   at the top of this file
4. Keep `test_a_user_cannot_self_assign_their_way_into_an_invisible_deal`, changing the
   expected `404` to `403` — the attack must still fail, only the reason changes

---

# `Version` — the audit trail

## Short version

`Version` records one row per tracked field change, holding the **old and new values**.
Nothing reads it over HTTP — the timeline gets field changes from
`crm.api.activities.get_activities`, which checks read on the referenced document first
(`_require_readable`) and then queries `versions_for` over the ORM. So the route is
withheld.

## This one was mine

A2 added the doctype and did not ask whether it needed a rule — the exact mistake this
file exists to catalogue, made by the person cataloguing it. The result:

```
GET /api/resource/CRM Deal/CRM-DEAL-2026-00001   → 403
GET /api/resource/Version                        → {"changed": [["deal_value", 100, 8888888]]}
```

A deal the caller is refused, with its value in the audit trail. Worth stating plainly:
**adding a doctype is adding a public CRUD surface**, and knowing that is not the same as
remembering it at the moment you write `@register_doctype`. That is why A6 is a test and
not a convention.

## Upstream is stricter still

`frappe/core/doctype/version/version.json`: System Manager gets **read only**,
Administrator read and delete, and `in_create: 1` means it is never created through the
API at all. Nobody else has any access. Withholding the route is the closest equivalent
this port has, and a smaller surface than a rule.

---

# The wider surface

`ToDo` was found while auditing phase 4, and it is not the only one. At the time of
writing **38 routable doctypes, 6 with row rules** — the other 32 are full CRUD to any
authenticated user, confirmed by driving the route as a Sales User.

The triage question is the cheap one:

> **Does anything actually call this route?**

- **No** → un-route it. Smaller surface, no rule to maintain or get wrong.
- **Yes** → it needs a real permission rule; roughly 12 are in this group, because the
  Vue app addresses them directly (`CRM Task`, `Contact`, `CRM Organization`, `FCRM Note`,
  `Email Account`, `User`, `File`, `Comment`, `Email Template`, `CRM Invitation`,
  `FCRM Settings`, `CRM Telephony Agent`).

A1–A5 are now closed: `ToDo` and `Version` un-routed, and rules on `User`,
`Email Account`, the settings singles and `CRM Sales Hierarchy`. The hierarchy was the
worst of them — the org tree is an *input to the permission engine*, so a Sales User could
add themselves and reparent a colleague underneath, taking that colleague's whole pipeline
in one call.

**The standing test now exists** — `tests/test_route_surface.py`. It does not decide
whether a doctype is safe; it makes the *absence of a decision* fail. Registering a new
doctype breaks the build until somebody records which of three things it is: ruled,
reviewed-and-open with a reason, or not-yet-reviewed with the question.

The current split, printed on every run:

```
route surface: 36 routable | 12 ruled | 10 reviewed-open | 14 awaiting review (A7)
```

Those 14 are A7, and each carries the question rather than a guess — a reason nobody
checked would defeat the point of writing them down. The test also asserts one invariant
outright, with no exceptions list: **a doctype declaring secrets must have a rule.** Hiding
a field from responses was never the same as stopping the record being rewritten, which is
exactly what A3 turned out to be.
