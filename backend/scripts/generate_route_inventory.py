"""Generate ``docs/ROUTES.md`` - every backend and frontend route, from the code.

Run from ``backend/``::

    .venv/Scripts/python.exe scripts/generate_route_inventory.py

Three sources, none transcribed by hand:

* ``frappe_core.whitelist.all_methods()`` - every ``/api/method/<dotted.path>``
* ``frappe_core.registry`` - every ``/api/resource/<DocType>`` and what protects it
* ``frontend/src/router.js`` - every page the Vue app serves

The frontend-usage columns come from counting literal occurrences in ``frontend/src``,
so they are a guide to what matters, not a call graph.
"""

from __future__ import annotations

import inspect
import os
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
FRONTEND_SRC = ROOT / "frontend" / "src"
OUT = ROOT / "docs" / "ROUTES.md"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from frappe_core import registry, whitelist  # noqa: E402

# ----------------------------------------------------------------------------- helpers


def _md(cell) -> str:
    """Escape a value for a markdown table cell."""
    text = "" if cell is None else str(cell)
    return text.replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list], numbered: bool = True) -> str:
    """Render a markdown table.

    ``numbered`` prepends a ``#`` column counting from 1, restarting per table - each
    table is its own checklist, and "method 37" is easier to refer to than a dotted path.
    """
    if numbered:
        headers = ["#", *headers]
        rows = [[i, *row] for i, row in enumerate(rows, start=1)]
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        out.append("| " + " | ".join(_md(c) for c in row) + " |")
    return "\n".join(out)


def _previous_tested() -> dict[str, str]:
    """The Tested column of the file we are about to overwrite, keyed on identity.

    Every generated table has the row number first and the identity second - the dotted
    path, the doctype, or the page path - and Tested last. Anything written there by hand
    is carried into the regenerated file, so refreshing the inventory does not erase the
    checklist. A row that no longer exists simply drops its note.
    """
    if not OUT.exists():
        return {}
    kept: dict[str, str] = {}
    for line in OUT.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        # Split on unescaped pipes only: `_md` writes a literal pipe inside a cell as
        # `\|`, and the parameter column is full of `str \| list`.
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        if cells[-1]:
            kept[cells[1].strip("`")] = cells[-1]
    return kept


def _carry_tested(rows: list[list], kept: dict[str, str]) -> list[list]:
    for row in rows:
        key = str(row[0]).strip("`")
        if row[-1] == "" and key in kept:
            row[-1] = kept[key]
    return rows


def _frontend_sources() -> list[str]:
    texts = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix in {".vue", ".js", ".ts"} and path.is_file():
            try:
                texts.append(path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                pass
    return texts


FRONTEND_TEXTS = _frontend_sources()


def _frontend_count(literal: str) -> int:
    """Occurrences of ``literal`` as a quoted string under ``frontend/src``.

    Quoted only: a bare substring count credits ``login`` with every ``isLoggedIn`` and
    ``/login`` in the tree, which is noise rather than a call site. The phase-8 auth pages
    address their endpoints by full URL (``'/api/method/<path>'``), so that form counts
    as well.
    """
    forms = (literal, f"/api/method/{literal}")
    quoted = [q for f in forms for q in (f"'{f}'", f'"{f}"', f"`{f}`")]
    return sum(text.count(q) for text in FRONTEND_TEXTS for q in quoted)


def _unwrap(func):
    """The function a decorator stack ultimately calls.

    ``inspect.getsourcelines`` follows ``__wrapped__`` but ``inspect.getsourcefile`` does
    not, so a ``functools.wraps`` wrapper reports the *decorator's* file with the
    *original's* line number - the four ``rate_limit``-ed endpoints came out as
    ``security.py:311`` and so on. Unwrapping first gives both from the same function.

    The closure fallback covers a decorator that copies the signature by hand and leaves
    no ``__wrapped__``: the original is then the one function object it closes over.
    """
    seen = set()
    while id(func) not in seen:
        seen.add(id(func))
        inner = getattr(func, "__wrapped__", None)
        if inner is None:
            funcs = []
            for cell in getattr(func, "__closure__", None) or ():
                try:
                    value = cell.cell_contents
                except ValueError:
                    continue
                if inspect.isfunction(value):
                    funcs.append(value)
            inner = funcs[0] if len(funcs) == 1 else None
        if inner is None:
            break
        func = inner
    return func


def _rel(path: str | None) -> str:
    if not path:
        return "?"
    try:
        return Path(path).resolve().relative_to(BACKEND).as_posix()
    except ValueError:
        return Path(path).name


# ----------------------------------------------------------------------------- methods


def method_rows() -> list[list]:
    rows = []
    for dotted in whitelist.all_methods():
        func = whitelist.get_method(dotted)
        try:
            sig = inspect.signature(func)
            params = ", ".join(
                str(p) for name, p in sig.parameters.items() if name != "_request"
            )
        except (TypeError, ValueError):
            params = "?"
        target = _unwrap(func)
        try:
            src = _rel(inspect.getsourcefile(target))
            line = inspect.getsourcelines(target)[1]
            where = f"{src}:{line}"
        except (OSError, TypeError):
            where = "?"
        verbs = "/".join(getattr(func, "__frappe_methods__", ("GET", "POST")))
        guest = "guest" if getattr(func, "__frappe_allow_guest__", False) else "auth"
        if getattr(func, "__frappe_wants_request__", False):
            guest += " +request"
        rows.append(
            [
                f"`{dotted}`",
                verbs,
                guest,
                f"`{params}`" if params else "—",
                _frontend_count(dotted),
                f"`{where}`",
                "",
            ]
        )
    return rows


# ----------------------------------------------------------------------------- resources


def _classification() -> tuple[dict, dict]:
    try:
        from tests.test_route_surface import NOT_YET_REVIEWED, REVIEWED_OPEN

        return REVIEWED_OPEN, NOT_YET_REVIEWED
    except Exception:  # pragma: no cover - the doc still generates without it
        return {}, {}


def _naming(model) -> str:
    strategy = None
    getter = getattr(model, "get_name_strategy", None)
    if callable(getter):
        strategy = getter()
    if strategy is not None:
        return f"`{strategy!r}`"
    pk = model._meta.pk
    if pk.get_internal_type() in {"AutoField", "BigAutoField"}:
        return "autoincrement (integer)"
    if hasattr(model, "autoname"):
        return "controller `autoname()`"
    return "default"


def _fields(model, attr: str) -> str:
    value = getattr(model, attr, None)
    if not value:
        return ""
    if isinstance(value, dict):
        value = value.keys()
    return ", ".join(f"`{v}`" for v in value)


def resource_rows() -> tuple[list[list], list[list]]:
    reviewed_open, not_reviewed = _classification()
    routable, others = [], []
    for doctype in registry.all_doctypes():
        entry = registry.get_entry(doctype)
        model = entry.model
        try:
            count = model._default_manager.count()
        except Exception:
            count = "?"
        protections = []
        if entry.permission_query_conditions is not None:
            protections.append("list rule")
        if entry.has_permission is not None:
            protections.append("object rule")
        if entry.reference_fields:
            protections.append("destination re-check")

        if entry.is_child_table:
            route = "child table — inline in parent, no route"
        elif not entry.routable:
            route = "**withheld** (`routable=False`)"
        else:
            route = f"`/api/resource/{doctype}`"

        if entry.is_child_table:
            status = "n/a"
        elif not entry.routable:
            status = "withheld — `specs/UNROUTED_DOCTYPES.md`"
        elif protections:
            status = "ruled: " + ", ".join(protections)
        elif doctype in reviewed_open:
            status = "reviewed-open — " + reviewed_open[doctype]
        elif doctype in not_reviewed:
            status = "awaiting review — " + not_reviewed[doctype]
        else:
            status = "open (no rule)"

        declared = []
        for label, attr in (
            ("S", "SENSITIVE_FIELDS"),
            ("E", "ENCRYPTED_FIELDS"),
            ("R", "RESTRICTED_FIELDS"),
            ("RO", "READONLY_FIELDS"),
        ):
            names = _fields(model, attr)
            if names:
                declared.append(f"{label}: {names}")

        row = [
            doctype,
            f"`{model.__module__.split('.')[0]}.{model.__name__}`",
            route,
            "single" if entry.is_single else "",
            _naming(model),
            status,
            "; ".join(declared),
            _frontend_count(doctype),
            count,
            "",
        ]
        (routable if (entry.routable and not entry.is_child_table) else others).append(row)
    return routable, others


# ----------------------------------------------------------------------------- frontend


def frontend_routes() -> list[list]:
    source = (FRONTEND_SRC / "router.js").read_text(encoding="utf-8")
    start = source.index("const routes = [") + len("const routes = [")
    depth, i = 1, start
    while depth and i < len(source):
        depth += {"[": 1, "]": -1}.get(source[i], 0)
        i += 1
    body = source[start : i - 1]

    objects, depth, buf = [], 0, ""
    for ch in body:
        if ch == "{":
            depth += 1
        if depth:
            buf += ch
        if ch == "}":
            depth -= 1
            if depth == 0:
                objects.append(buf)
                buf = ""

    rows = []
    for obj in objects:
        path = re.search(r"path:\s*'([^']+)'", obj)
        name = re.search(r"name:\s*'([^']+)'", obj)
        alias = re.search(r"alias:\s*'([^']+)'", obj)
        public = "public" if re.search(r"isPublic:\s*true", obj) else "login required"
        comp = re.search(r"@/pages/([^'`]+?)\.vue", obj)
        mobile = re.search(r"handleMobileView\('(\w+)'\)", obj)
        if mobile:
            component = f"{mobile.group(1)}.vue / Mobile{mobile.group(1)}.vue"
        elif comp:
            component = comp.group(1) + ".vue"
        else:
            component = "— (redirects in the guard)"
        rows.append(
            [
                f"`/crm{path.group(1)}`" if path else "?",
                f"`/crm{alias.group(1)}`" if alias else "",
                name.group(1) if name else "?",
                component,
                public,
                "",
            ]
        )
    return rows


# ----------------------------------------------------------------------------- document

HEADER = """# Route inventory — every backend and frontend path

**Generated** by `backend/scripts/generate_route_inventory.py` from the whitelist
registry, the doctype registry and `frontend/src/router.js`. Re-run it after adding an
endpoint, a doctype or a page; do not edit the tables by hand. The blank **Tested**
column is the one thing meant to be filled in — it is the checklist for the API
walkthrough.

## How to read this

| | |
|---|---|
| Backend base URL | `http://localhost:8000` (`runserver 8000`, ASGI via daphne) |
| Frontend base URL | `http://localhost:8080/crm` (`yarn dev`; the router's history base is `/crm`) |
| Auth header | `Authorization: Bearer <access token>` — access tokens live 5 minutes, refresh tokens 7 days |
| `/api/method/*` envelope | `{"message": ...}` |
| `/api/resource/*` envelope | `{"data": ...}` |
| Error body | Frappe-shaped (`exc_type`, `exception`, `_server_messages`) — see `frappe_core/exceptions.py` |
| Unknown or withheld doctype | 404, deliberately indistinguishable |
| Forbidden row | 403, distinguishable from 404 — matches upstream |

The dev server proxies `/api`, `/assets`, `/files` and `/private` to the backend, so the
browser only ever talks to port 8080. Manual testing with curl or a REST client goes
straight to port 8000.

---

## 1. Method endpoints — `/api/method/<dotted.path>`

One generic view (`frappe_core/method_views.py`) dispatches every row below by looking
the dotted path up in the whitelist registry. Parameters merge the query string and the
JSON body; each value is JSON-decoded if it parses, so `filters=[["a","=","b"]]` and a
native array are the same thing. Surplus parameters are dropped.

Columns: **Verbs** the view accepts; **Access** is `guest` for the few endpoints that
work without a token, `auth` otherwise, and `+request` marks the webhook handlers that
receive the raw request for signature checks; **Frontend uses** is how many times the
literal path appears under `frontend/src`.

"""

RESOURCE_HEADER = """
---

## 2. Resource endpoints — `/api/resource/<DocType>[/<name>]`

Two generic views (`frappe_core/views.py`) serve every routable doctype:

| Verb | Route | Does |
|---|---|---|
| GET | `/api/resource/<DocType>` | List. Params: `filters`, `or_filters`, `fields`, `order_by`, `limit_start`, `limit_page_length`, `group_by`, `parent` — all JSON strings |
| POST | `/api/resource/<DocType>` | Create. Body is the document; child tables inline |
| GET | `/api/resource/<DocType>/<name>` | Read one. `<name>` may contain slashes |
| PUT | `/api/resource/<DocType>/<name>` | Update. Child tables are replaced wholesale |
| DELETE | `/api/resource/<DocType>/<name>` | Delete → `{"data": null}` |

There is no PATCH. Doctype names contain spaces — URL-encode them (`CRM%20Lead`) or let
the client do it.

Columns: **Naming** is the primary-key strategy, which tells you what `name` to expect
on create; **Protection** is the route-surface classification from
`tests/test_route_surface.py` — `ruled` means a permission hook is registered, the other
two states are recorded decisions; **Declared fields** are the field-visibility
declarations (`S` sensitive: never on the wire, `E` encrypted at rest, `R` restricted to
managers, `RO` read-only); **Frontend refs** counts `'<DocType>'` literals under
`frontend/src`; **Rows** is the count in the local database when this file was generated.

### 2a. Routable doctypes

"""

UNROUTED_HEADER = """
### 2b. Registered but not routable

Child tables are reached inline through their parent. Withheld doctypes exist, have
rules and internal callers, and simply publish no route — `specs/UNROUTED_DOCTYPES.md`
has the reasoning.

"""

WS_HEADER = """
---

## 3. WebSocket — `ws://localhost:8000/ws/realtime?token=<access token>`

One endpoint, `crm_app/consumers.py:RealtimeConsumer`, routed in `config/routing.py`.
The token rides in the query string because a browser cannot set headers on a handshake.
An invalid or missing token closes the socket with code **4001**. `ENABLE_REALTIME=0`
removes the route entirely.

The vite dev server does **not** proxy `/ws`, so in development the browser needs
`VITE_WS_ORIGIN=ws://localhost:8000` in `frontend/.env.local`, or the client silently
retries with backoff and the app runs without live updates.

| Client → server event | Meaning |
|---|---|
{ws_events}

---

## 4. Other backend routes

| Route | What |
|---|---|
| `/admin/` | Django admin. Present in `config/urls.py`; not part of the Frappe contract |

"""

FRONTEND_HEADER = """
---

## 5. Frontend pages — `http://localhost:8080/crm<path>`

From `frontend/src/router.js`. Every path below is relative to the `/crm` history base.
The navigation guard sends a logged-out visitor to **Login** with `?redirect=<path>`, sends
a logged-in visitor without a CRM role to **Not Permitted**, and resolves **Home** to the
user's default saved view (falling back to **Leads**).

`:viewType` is one of `list`, `kanban`, `group_by`, or a saved-view name; `?view=<name>`
selects a saved view. Lead and Deal pages append `#activity` (or the last-used tab) when
opened without a hash. Mobile variants are chosen at load when the viewport is under
768px.

"""

FOOTER = """
---

## 6. Regenerating

```
cd backend
.venv/Scripts/python.exe scripts/generate_route_inventory.py
```

Whatever is written in a **Tested** cell is carried forward on regeneration, keyed on the
dotted path, doctype or page path in the row. A row that disappears takes its note with it.
"""


def _ws_events() -> str:
    # The three events `RealtimeConsumer.receive` dispatches on. Hardcoded rather than
    # scraped: the consumer's own docstring is the contract, and a regex over the file
    # picks up reply names (`doc_subscribed`) and internals (`doc_groups`) as well.
    consumer = (BACKEND / "crm_app" / "consumers.py").read_text(encoding="utf-8")
    events = [
        (
            "doc_subscribe",
            '`{"event": "doc_subscribe", "args": ["CRM Lead", "<name>"]}` — join the '
            "document's room. Permission-checked with the same list + object rules the "
            "HTTP detail route uses; replies `doc_subscribed`",
        ),
        (
            "doc_unsubscribe",
            "same args — leave the room; replies `doc_unsubscribed`",
        ),
        ("ping", "keepalive; replies `pong`"),
    ]
    missing = [e for e, _ in events if f'"{e}"' not in consumer]
    if missing:
        raise SystemExit(f"consumers.py no longer handles {missing}; update _ws_events")
    return "\n".join(f"| `{e}` | {desc} |" for e, desc in events)


def main() -> None:
    kept = _previous_tested()
    methods = _carry_tested(method_rows(), kept)
    routable, others = resource_rows()
    routable, others = _carry_tested(routable, kept), _carry_tested(others, kept)
    pages = _carry_tested(frontend_routes(), kept)

    parts = [
        HEADER,
        _table(
            ["Dotted path", "Verbs", "Access", "Parameters", "Frontend uses", "Source", "Tested"],
            methods,
        ),
        RESOURCE_HEADER,
        _table(
            [
                "DocType",
                "Model",
                "Route",
                "Single",
                "Naming",
                "Protection",
                "Declared fields",
                "Frontend refs",
                "Rows",
                "Tested",
            ],
            routable,
        ),
        UNROUTED_HEADER,
        _table(
            [
                "DocType",
                "Model",
                "Route",
                "Single",
                "Naming",
                "Protection",
                "Declared fields",
                "Frontend refs",
                "Rows",
                "Tested",
            ],
            others,
        ),
        WS_HEADER.format(ws_events=_ws_events()),
        FRONTEND_HEADER,
        _table(["Path", "Alias", "Route name", "Component", "Access", "Tested"], pages),
        FOOTER,
    ]
    OUT.write_text("\n\n".join(p.strip("\n") for p in parts) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT.relative_to(ROOT).as_posix()}: "
        f"{len(methods)} methods, {len(routable)} routable doctypes, "
        f"{len(others)} unrouted/child, {len(pages)} pages"
    )


if __name__ == "__main__":
    main()
