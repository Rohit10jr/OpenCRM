# Phase 2 — Permission Engine

**Single agent. Do not parallelise.** Needs phase 0 and phase 1 cluster 1 (platform).

Source: `crm/permissions/org_hierarchy.py` (368 LOC) and the `permission_query_conditions`
/ `has_permission` blocks in `crm/hooks.py`.

This is row-level security. Django's built-in permissions are model-level only, so
this layer is custom. Getting it wrong leaks other people's leads — treat it as the
security-critical phase it is.

---

## 1. Two hooks, registered for three doctypes only

Verified from `hooks.py` — upstream registers row-level rules for **`CRM Lead`,
`CRM Deal`, `CRM Notification`** and nothing else. Everything else uses plain
role permissions.

```python
def get_permission_query_conditions(doctype, user) -> Q | None   # list filtering
def has_permission(doc, ptype, user) -> bool | None              # single-object check
```

`None` means "no restriction". Both plug into the phase-0 extension points — **do not
edit phase-0 view code.**

Upstream implements `has_permission` by re-running the query conditions against the
single row (`WHERE name = doc.name AND <conditions> LIMIT 1`). Mirror that: one source
of truth for the rules, no chance of the two hooks drifting apart.

---

## 2. The rules — verified, in evaluation order

Owner field differs per doctype:

```python
_OWNER_FIELD = {"CRM Lead": "lead_owner", "CRM Deal": "deal_owner"}
```

Evaluate in exactly this order — order is load-bearing:

1. **`Administrator`** → unrestricted (`None`)
2. **`System Manager` role** → unrestricted
3. Compute `in_tree = hierarchy_enabled() and user_is_in_hierarchy(user)`
   - `hierarchy_enabled()` reads `FCRM Settings.enable_sales_hierarchy` (singleton)
   - `user_is_in_hierarchy(user)` = a `CRM Sales Hierarchy` row exists for that user
4. **`Sales Manager` AND NOT `in_tree`** → unrestricted
   *A Sales Manager who is not placed in the tree keeps the legacy see-everything
   behaviour. This is deliberate upstream, not a bug. Preserve it.*
5. **`in_tree`** → owner is the user **or any member of their subtree**, OR the record
   is assigned via `ToDo` to the user or any subtree member
6. **Default (Sales User)** → own records, plus records directly assigned to them via
   `ToDo`

### The ToDo assignment clause

Assignment lives in `ToDo`, not in `_assign`:

```sql
name IN (SELECT reference_name FROM ToDo
         WHERE reference_type = <doctype>
           AND status != 'Cancelled'
           AND allocated_to IN (<user or subtree users>))
```

**Query `ToDo`, never `_assign`.** `_assign` is a denormalised cache
(`PHASE_0_FOUNDATION.md` §3) and must not be trusted for access control. The
`status != 'Cancelled'` filter is required — cancelled assignments do not grant access.

---

## 3. `CRM Sales Hierarchy` is a nested-set tree

Upstream uses `lft`/`rgt` columns. Subtree membership is:

```sql
Member.lft >= Mgr.lft AND Member.lft <= Mgr.rgt
```

**Superseded — do not use `django-treebeard`.** This section originally named it; the
implementation is a full rebuild in `crm_app/permissions/tree.py`, and that decision is
now settled rather than provisional. Treebeard owns its own columns and expects node
creation through `add_root`/`add_child`, but rows arrive through the generic
`/api/resource/` endpoint with `reports_to` set, and the schema we must match is Frappe's
`lft`/`rgt`. Adopting it would mean a second tree representation to keep in sync.

Frappe itself does neither: it maintains bounds **incrementally**
(`frappe/utils/nestedset.py:update_add_node` / `update_move_node`) and reserves
`rebuild_tree` for repair. That is a third write path, matching neither treebeard nor
ours. Do not use a self-referential FK alone — it forces recursive CTEs on every list
query. `crm_territory` is also a tree; give it the same treatment.

### The rebuild must be serialised, and a row lock is not enough

`lft`/`rgt` decide **which rows a user can see**, so overlapping bounds are a permission
defect, not a cosmetic one.

The hazard is concurrent **inserts**, not concurrent rebuilds — rebuilding a fixed node
set twice is harmless, since the walk derives bounds from `reports_to` alone. The damage
happens when one transaction walks `n` nodes while another walks `n+1`: each writes only
the rows it read, so the newcomer keeps bounds from one walk and its siblings keep bounds
from the other.

**`select_for_update()` does not fix this.** A row lock only covers rows the query already
matched; the second writer blocks, re-reads *those* rows, and still cannot see the row the
first writer inserted — the classic phantom. It walks `n` nodes regardless, and the bounds
still collide. This was verified by test: the corruption reproduces with `select_for_update`
in place.

The lock has to be taken **before the read**, over the operation rather than a row set —
a transaction-scoped advisory lock (`pg_advisory_xact_lock`). Any test for this must be
checked to fail with the lock removed; a version that spawned concurrent
`rebuild_sales_hierarchy()` calls over a static tree passed either way and proved nothing.

Subtree lookup runs on **every list request** for leads and deals. Cache it per
request at minimum; upstream uses `@request_cache` on the hierarchy checks. Do the
same, and make sure the cache key includes the user.

---

## 4. `has_permission` short-circuits

From source, before any tree evaluation:

- `Administrator` → `True`
- `System Manager` → `True`
- **`ptype == "create"` or the doc has no `name` yet → `True`**

That third one matters: unsaved documents always pass. Skip it and every create fails.

---

## 4a. Two inherited behaviours, confirmed rather than assumed

Both are faithful to upstream and were reviewed deliberately rather than left to default.

### Only three doctypes have row-level rules

Verified in `crm/hooks.py`: `permission_query_conditions` and `has_permission` are
registered for **`CRM Lead`, `CRM Deal`, `CRM Notification`** and nothing else.

Everything else — **organizations, tasks, notes, call logs, contacts, products,
territories, SLAs and all settings** — is readable by **every authenticated user**.
Only role permissions apply. That is a much wider surface than "the CRM has row-level
security" suggests, and it is upstream's design: leads and deals are the confidential
records, the surrounding reference data is shared.

**Decision: keep.** Widening it is a product change, not a port fix, and it would break
the frontend in non-obvious ways — an org or contact linked to a lead you *can* see would
start returning 403 on the detail fetch.

### 403 and 404 are distinguishable

`_get_object` raises `DoesNotExistError` for a missing row and `PermissionError` for a
forbidden one, so a user can tell whether a record they cannot see exists. That is an
existence oracle, and it matches upstream exactly.

**Decision: keep.** Collapsing both to 404 would diverge from upstream and break the
frontend's error handling, which branches on `exc_type`
(`frontend/src/data/document.js:40`). The information leaked is the existence of a record
name the user already had to guess.

## 5. Roles

Four, seeded in phase 0, mapped to Django Groups: `Administrator`, `System Manager`,
`Sales Manager`, `Sales User`.

`Administrator` is a **user**, not only a role, in Frappe — the literal user named
`Administrator` bypasses everything. Implement both the role check and the username
check, exactly as upstream does.

---

## 6. Acceptance criteria

Write a test matrix. Every row is a real access-control decision:

| User | Hierarchy on | In tree | Expected |
|---|---|---|---|
| Administrator | either | either | sees all |
| System Manager | either | either | sees all |
| Sales Manager | off | no | sees all |
| Sales Manager | on | no | sees all |
| Sales Manager | on | yes | own + subtree + subtree-assigned |
| Sales User | off | no | own + directly assigned |
| Sales User | on | yes | own + subtree + subtree-assigned |

- [ ] Full matrix passes for `CRM Lead` and `CRM Deal`
- [ ] `CRM Notification` uses its own doctype-local rule (`crm_notification.py`), not this one
- [ ] Cancelled `ToDo` records grant no access
- [ ] `has_permission` and list filtering agree on every case — no row visible in list but 403 on read, and no row hidden in list but readable directly
- [ ] Create is permitted for unsaved documents
- [ ] Subtree query does not N+1; verify query count on a 100-row list
- [ ] Permission bypass is impossible via `fields`, `order_by`, or `group_by` params

That last one is the real security test: **a filter or field selection must never
expose a row the user cannot see.** Probe it deliberately.
