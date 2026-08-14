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

Use **`django-treebeard`** (`MP_Node` or `NS_Node`), not a self-referential FK — a
plain FK forces recursive CTEs for every list query and will not perform. `crm_territory`
is also a tree; check it for `lft`/`rgt` and give it the same treatment.

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
