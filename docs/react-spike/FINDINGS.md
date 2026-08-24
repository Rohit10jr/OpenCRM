# What the Vue frontend actually is

Measured before planning anything, so the estimates below are arithmetic rather than
instinct. All figures from `frontend/src` on `main` (phases 0–7 merged).

---

## Size

| | Count |
|---|---|
| `.vue` files | **321** — 22 pages, 298 components, 1 root |
| Lines of `.vue` | **~46,800** |
| `.js` files | 47 (~5,500 lines) — stores, composables, auth, socket |
| Files importing `frappe-ui` | **199** |

For scale: the entire backend port — seven phases — is about 25,000 lines. **The frontend
is roughly twice the backend.**

## What `frappe-ui` is actually used for

397 import sites, and they are not evenly spread. Sorted by frequency:

### Data layer — ~90 uses, and not UI at all

| Import | Uses | React equivalent |
|---|---|---|
| `createResource` | 46 | TanStack Query `useQuery` / `useMutation` |
| `call` | 32 | a thin `axios` wrapper |
| `createListResource` | 8 | `useQuery` with pagination |
| `createDocumentResource` | 3 | `useQuery` keyed on the document name |

This is the single most important mapping in the project. Get it right once and ~90 call
sites become mechanical.

### UI components — ~180 uses, every one has a shadcn answer

`Dropdown` (23) · `Tooltip` (20) · `Dialog` (15) · `Button` (15) · `Avatar` (14) ·
`Switch` (11) · `FormControl` (11) · `ErrorMessage` (11) · `Popover` (10) · `Combobox` (9)
· `Badge` (9) · `TextInput` (5) · `FeatherIcon` (3)

No gaps. That is less lucky than it sounds: `frappe-ui` is itself a thin Headless UI +
Tailwind layer, the same lineage shadcn comes from.

### The three that need thought

| Import | Uses | Note |
|---|---|---|
| `toast` | 30 | → `sonner`. Trivial, but 30 call sites |
| `TextEditor` | 10 | A TipTap wrapper. **TipTap has first-class React bindings**, so this survives as a port rather than a rewrite |
| `FileUploader` | 3 | Needs writing. Small |

---

## The finding that shapes the spike

**`components/ViewControls.vue` is 1,365 lines and is not part of any one screen.**

It is the client for the backend's list engine. Line 515:

```js
list.value = createResource({ url: 'crm.api.doc.get_data', ... })
```

It owns filters, sorting, column selection, saved views, quick filters, export, page size
and list/kanban switching — and it is imported by **seven pages**: Deals, Leads, Contacts,
Organizations, Notes, Tasks, CallLogs.

So "convert the Deals screen" is really:

| Piece | Lines | Shared? |
|---|---|---|
| `ViewControls.vue` | 1,365 | **Yes — 7 pages** |
| `pages/Deals.vue` | 562 | No |
| `ListViews/DealsListView.vue` | 312 | No |
| `Kanban/KanbanView.vue` | 277 | Shared with Leads |
| **Total** | **~2,516** | |

**This is good news wearing bad clothes.** The first list screen costs ~2,500 lines
because it drags the engine with it. Screens two through seven cost ~600 each, because the
engine is already there.

An estimate taken from the first screen alone would be wrong by a factor of four. That is
precisely what a spike exists to discover, and it is why the spike must be a *list* screen
rather than an easy one.

---

## The backend is a fixed, documented contract

Unusually favourable ground for a rewrite:

* **`PORT_PLAN.md` §3** documents the wire protocol as a hard external contract.
* **`get_data` returns a known shape** (`frappe_core/api/doc.py:353`): `data`, `columns`,
  `rows`, `fields`, `kanban_columns`, `total_count`, `views`, `form_script`, `view_type`
  and more. A React client consumes exactly what the Vue one does.
* **`test_every_frontend_dotted_path_resolves`** reads the frontend source and fails if it
  calls an API path nothing serves. **It would work against React source too** — pointing
  it at the new tree keeps the contract enforced during the migration.
* Auth is already ours: `auth/tokens.js` (91 lines) and `auth/jwtRequest.js` (61) were
  written for this port, not inherited. They are the JWT deviation, and they port almost
  directly to an axios interceptor.

## What else is in the layer

* **10 Pinia stores** (~790 lines) — `users`, `statuses`, `meta`, `settings`, `views`,
  `session`, `global`, `theme`, `organizations`, `notifications`. Most are a cached
  resource plus getters; in React they are TanStack Query keys, not a state library.
* **`socket.js`** (235 lines) — the phase-6 realtime client, already rewritten once for
  this port and already ours. Framework-agnostic apart from how components subscribe.
* **21 routes** in `router.js` → TanStack Router.
* **9 composables** — mostly hooks already in spirit.

## What this means before any code is written

1. The component mapping is clean. There is no `frappe-ui` piece without a React answer.
2. The data layer is the real work, and it is ~90 sites of one pattern.
3. The list engine is shared infrastructure and must be built before the second screen is
   cheap.
4. The API contract is fixed, documented, and already has a test that enforces it.
