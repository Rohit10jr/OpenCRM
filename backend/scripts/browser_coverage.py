"""Fill the "API coverage" section of ``docs/BROWSER_TESTING.md`` from the code and the log.

Run from ``backend/``::

    .venv/Scripts/python.exe scripts/browser_coverage.py

Nothing in the section is typed by hand:

* ``frappe_core.whitelist.all_methods()`` - every ``/api/method/`` endpoint, minus the
  integrations (Twilio, Exotel, WhatsApp, ERPNext, lead sync, Frappe Cloud), which are
  listed underneath as excluded;
* each handler's file and line, and the upstream reference its docstring cites
  (``crm/api/doc.py:256-541``, ``frappe/client.py:get_value``), qualified from the
  module docstring when the function cites a bare file name;
* the per-screen tables of the log itself: which rows reach which endpoint (their
  ``Calls`` column) and how those rows went (``Result``, ``Finding``).

The section sits between ``<!-- api-coverage:start -->`` and ``<!-- api-coverage:end -->``;
the Coverage table at the top between ``<!-- coverage:start -->`` and
``<!-- coverage:end -->``. Both are replaced whole on every run.
"""

from __future__ import annotations

import inspect
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
LOG = ROOT / "docs" / "BROWSER_TESTING.md"

sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from frappe_core import whitelist  # noqa: E402

#: Integration endpoints, out of the browser log's scope: by dotted path or by module.
INTEGRATION_PATH_RE = re.compile(
    r"^(crm\.integrations\.|crm\.twilio\.|crm\.exotel\.|crm\.api\.whatsapp|"
    r"crm\.fcrm\.doctype\.(erpnext_crm_settings|crm_lead_sync|facebook)|frappe\.integrations\.)"
)
INTEGRATION_MODULE_RE = re.compile(r"(^|/)integrations/")

#: Under ``crm.integrations`` upstream, but reached by the Call Log screens with no
#: telephony provider configured, so they belong to the log after all.
KEEP = {
    "crm.integrations.api.add_note_to_call_log",
    "crm.integrations.api.add_task_to_call_log",
    "crm.integrations.api.is_call_integration_enabled",
}

#: An upstream reference as the docstrings write it: ``crm/api/doc.py:256-541``,
#: `user.py:967-971`, ``frappe/client.py:get_value``.
UPSTREAM_RE = re.compile(r"`{1,2}((?:[\w.-]+/)*[\w-]+\.py(?::[\w.:-]+)?)`{1,2}")

#: The four endpoints whose docstrings cite no upstream file, because they are the
#: port's JWT sign-in (frontend/JWT_PATCH.md) standing in for Frappe's session login.
UPSTREAM_OVERRIDES = {
    "login": "frappe/auth.py:LoginManager (session login; JWT here, JWT_PATCH.md)",
    "logout": "frappe/auth.py:LoginManager.logout (JWT here)",
    "token/refresh": "none, the JWT deviation (JWT_PATCH.md)",
    "frappe.auth.get_logged_user": "frappe/auth.py:get_logged_user",
}

COVERAGE_START, COVERAGE_END = "<!-- coverage:start -->", "<!-- coverage:end -->"
API_START, API_END = "<!-- api-coverage:start -->", "<!-- api-coverage:end -->"


# ----------------------------------------------------------------------------- the code


def _unwrap(func):
    """The function a decorator stack ultimately calls (same as the inventory script)."""
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


def _upstream(func) -> str:
    """The first upstream reference in the handler's docstring, qualified with the
    directory the module docstring gives the same file, or the module's own citation."""
    own = UPSTREAM_RE.findall(inspect.getdoc(func) or "")
    module = inspect.getmodule(func)
    module_refs = UPSTREAM_RE.findall((module.__doc__ if module else "") or "")
    if own:
        ref = own[0]
        if "/" not in ref:
            base = ref.split(":")[0]
            for candidate in module_refs:
                if candidate.split(":")[0].endswith("/" + base):
                    directory = candidate.split(":")[0].rsplit("/", 1)[0]
                    return f"{directory}/{ref}"
        return ref
    if module_refs:
        return module_refs[0]
    return "-"


def endpoints() -> tuple[list[dict], list[str]]:
    """(in-scope endpoints, excluded integration paths), each endpoint a dict."""
    rows, excluded = [], []
    for dotted in whitelist.all_methods():
        func = _unwrap(whitelist.get_method(dotted))
        try:
            source = _rel(inspect.getsourcefile(func))
            line = inspect.getsourcelines(func)[1]
        except (OSError, TypeError):
            source, line = "?", 0
        integration = INTEGRATION_PATH_RE.match(dotted) or INTEGRATION_MODULE_RE.search(source)
        if integration and dotted not in KEEP:
            excluded.append(dotted)
            continue
        rows.append(
            {
                "method": dotted,
                "django": f"{source}:{line}" if line else source,
                "upstream": UPSTREAM_OVERRIDES.get(dotted) or _upstream(func),
            }
        )
    return rows, excluded


# ----------------------------------------------------------------------------- the log

ROW_RE = re.compile(r"^\|\s*([A-Z]+\d+)\s*\|")
#: A backticked call in a row's Calls column: a dotted path, or the two slash-named
#: JWT endpoints (`token/refresh`).
CALL_RE = re.compile(r"`([\w./]+)`")


def screen_rows(text: str) -> list[dict]:
    """Every action row of every per-screen table: id, calls, result, finding, screen."""
    rows, screen = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            screen = line[3:].split("(")[0].strip()
            continue
        match = ROW_RE.match(line)
        if not match:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        result = cells[4].lower()
        status = next((s for s in ("ok", "failed", "skipped") if result.startswith(s)), "")
        rows.append(
            {
                "id": cells[0],
                "screen": screen,
                "calls": CALL_RE.findall(cells[3]),
                "status": status,
                "finding": cells[5],
            }
        )
    return rows


def resolve(token: str, methods: list[str]) -> str | None:
    """A backticked call to its endpoint: the full path, or a unique last segment."""
    if token in methods:
        return token
    if "." in token:
        return None
    hits = [m for m in methods if m.rsplit(".", 1)[-1] == token]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        print(f"ambiguous call `{token}`: {', '.join(hits)}", file=sys.stderr)
    return None


# ----------------------------------------------------------------------------- render


def _replace(text: str, start: str, end: str, body: str) -> str:
    head, _, rest = text.partition(start)
    _, _, tail = rest.partition(end)
    if not rest:
        raise SystemExit(f"marker {start} not found in {LOG}")
    return f"{head}{start}\n{body}\n{end}{tail}"


def render(text: str) -> str:
    api, excluded = endpoints()
    methods = [e["method"] for e in api]
    rows = screen_rows(text)

    reached: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        for token in row["calls"]:
            method = resolve(token, methods)
            if method:
                reached[method].append(row)

    ticked = 0
    lines = ["| | Method | Django | Upstream | Reached from | Result |", "|---|---|---|---|---|---|"]
    for entry in api:
        hits = reached.get(entry["method"], [])
        ok = [r["id"] for r in hits if r["status"] == "ok"]
        failed = [r for r in hits if r["status"] == "failed"]
        if failed:
            mark = "⚠"
            result = "failed: " + ", ".join(
                f"{r['id']}" + (f" (finding {r['finding']})" if r["finding"] else "") for r in failed
            )
        elif ok:
            mark = "☑"
            ticked += 1
            result = "ok: " + ", ".join(ok)
        else:
            mark = "☐"
            result = ""
        reached_from = ", ".join(r["id"] for r in hits)
        lines.append(
            f"| {mark} | `{entry['method']}` | `{entry['django']}` | `{entry['upstream']}` "
            f"| {reached_from} | {result} |"
        )
    unreached = sum(1 for e in api if not reached.get(e["method"]))
    api_body = "\n".join(lines)
    api_body += (
        f"\n\n{ticked} of {len(api)} endpoints confirmed; {unreached} not yet named by any row.\n\n"
        "**Excluded, integrations** (Twilio, Exotel, WhatsApp, ERPNext, lead sync, Frappe "
        "Cloud), not part of this log:\n\n"
        + "\n".join(f"- `{p}`" for p in excluded)
    )
    text = _replace(text, API_START, API_END, api_body)

    screens = defaultdict(list)
    for row in rows:
        screens[row["screen"]].append(row)
    done = sum(1 for rs in screens.values() if rs and all(r["status"] for r in rs))
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("ok", "failed", "skipped")}
    coverage = (
        "| Screens done | Rows ok | Rows failed | Rows skipped | Endpoints confirmed |\n"
        "|---|---|---|---|---|\n"
        f"| {done} of {len(screens)} with rows | {counts['ok']} | {counts['failed']} "
        f"| {counts['skipped']} | {ticked} of {len(api)} |"
    )
    return _replace(text, COVERAGE_START, COVERAGE_END, coverage)


def main() -> None:
    text = LOG.read_text(encoding="utf-8")
    LOG.write_text(render(text), encoding="utf-8")
    print(f"wrote {LOG.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
