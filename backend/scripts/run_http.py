"""Replay a VS Code REST Client ``.http`` file against a running server and check it.

    .venv/Scripts/python.exe scripts/run_http.py ../docs/http/02_resource_grammar.http
    .venv/Scripts/python.exe scripts/run_http.py ../docs/http/*.http --mark

The file stays the single source of truth: what you click by hand is what this sends.
Supported, matching the extension's behaviour for everything the walkthrough files use:

* ``@name = value`` file variables, anywhere, evaluated in order
* ``{{name}}`` substitution, ``{{$dotenv NAME}}`` from the ``.env`` beside the file
* ``# @name label`` on a block, then ``{{label.response.body.$.a.b[0].c}}`` later
* ``### title -> 201`` - the expected status is read from the block's own title; a title
  without one expects any 2xx; ``-> 200|404`` accepts either, for cleanup blocks
* ``# @expect $.data.name == Acme`` - optional body assertions: ``==``, ``!=``,
  ``contains``, ``excludes``, ``exists``, ``absent``, and ``count N`` for the length
  of a list. ``contains``/``excludes`` match a substring of the value's JSON text

Each block prints one PASS/FAIL line. ``--mark`` records the file in the Tested column
of ``docs/ROUTES.md`` for every method path and doctype it touched, with a count of
red lines when there were any (those are the logged findings).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import requests

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "docs" / "ROUTES.md"

VAR_RE = re.compile(r"^@([\w-]+)\s*=\s*(.*)$")
SUBST_RE = re.compile(r"\{\{([^{}]+)\}\}")
#: ``-> 201`` or ``-> 200|404`` (a cleanup block that may find nothing to clean).
STATUS_RE = re.compile(r"->\s*(\d{3}(?:\|\d{3})*)")
NAME_RE = re.compile(r"^#\s*@name\s+(\S+)")
EXPECT_RE = re.compile(r"^#\s*@expect\s+(\S+)\s+(==|!=|contains|excludes|exists|absent|count)\s*(.*)$")


class HttpError(Exception):
    pass


# ----------------------------------------------------------------------------- parsing


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def split_blocks(text: str) -> list[tuple[str, list[str]]]:
    """``[(title, lines), ...]`` - the preamble before the first ### has title ``""``."""
    blocks: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if line.startswith("###"):
            blocks.append((line[3:].strip(), []))
        else:
            blocks[-1][1].append(line)
    return blocks


def json_path(obj, path: str):
    """``$.a.b[0].c`` over parsed JSON. Raises KeyError/IndexError when absent."""
    if path.startswith("$"):
        path = path[1:]
    for part in re.findall(r"\.?([^.\[\]]+)|\[(\d+)\]", path):
        key, index = part
        if index:
            obj = obj[int(index)]
        elif key:
            obj = obj[key]
    return obj


# ----------------------------------------------------------------------------- runner


class Runner:
    def __init__(self, path: Path, host: str | None, verbose: bool):
        self.path = path
        self.host = host
        self.verbose = verbose
        self.vars: dict[str, str] = {}
        self.dotenv = load_dotenv(path.parent / ".env")
        self.responses: dict[str, requests.Response] = {}
        self.results: list[tuple[str, bool, str]] = []
        self.touched: set[str] = set()

    # -- substitution ---------------------------------------------------------------

    def resolve(self, text: str) -> str:
        def sub(match: re.Match) -> str:
            expr = match.group(1).strip()
            if expr.startswith("$dotenv"):
                key = expr.split(None, 1)[1].lstrip("%").strip()
                if key not in self.dotenv:
                    raise HttpError(f"{key} is not in {self.path.parent / '.env'}")
                return self.dotenv[key]
            if ".response." in expr:
                name, _, rest = expr.partition(".response.")
                if name not in self.responses:
                    raise HttpError(f"no response named {name!r} yet")
                response = self.responses[name]
                if rest.startswith("body."):
                    try:
                        value = json_path(response.json(), rest[len("body."):])
                    except (ValueError, KeyError, IndexError, TypeError):
                        raise HttpError(f"{expr}: not found in the {name} response") from None
                    return value if isinstance(value, str) else json.dumps(value)
                if rest.startswith("headers."):
                    return response.headers.get(rest[len("headers."):], "")
                raise HttpError(f"unsupported reference {expr}")
            if expr in self.vars:
                return self.resolve(self.vars[expr])
            raise HttpError(f"unknown variable {expr}")

        return SUBST_RE.sub(sub, text)

    # -- one block --------------------------------------------------------------------

    def run_block(self, title: str, lines: list[str]) -> None:
        name = None
        expects: list[tuple[str, str, str]] = []
        request_lines: list[str] = []
        for line in lines:
            if not line.strip() and not request_lines:
                continue  # leading blanks are not the start of a request
            var = VAR_RE.match(line)
            if var and not request_lines:
                self.vars[var.group(1)] = var.group(2)
                continue
            if m := NAME_RE.match(line):
                name = m.group(1)
                continue
            if m := EXPECT_RE.match(line):
                expects.append((m.group(1), m.group(2), m.group(3).strip()))
                continue
            if line.startswith("#") or line.startswith("//"):
                continue
            request_lines.append(line)

        while request_lines and not request_lines[0].strip():
            request_lines.pop(0)
        if not request_lines:
            return  # a variables-only block

        expected = STATUS_RE.search(title)
        allowed = {int(s) for s in expected.group(1).split("|")} if expected else set()

        try:
            method, url = self.resolve(request_lines[0]).split(None, 1)
            headers: dict[str, str] = {}
            i = 1
            while i < len(request_lines) and request_lines[i].strip():
                key, _, value = request_lines[i].partition(":")
                headers[key.strip()] = self.resolve(value.strip())
                i += 1
            body = "\n".join(request_lines[i + 1 :]).strip()
            body = self.resolve(body) if body else ""
        except (ValueError, HttpError) as exc:
            # A cleanup block deleting "whatever the previous list returned" has nothing
            # to reference on a clean database. If the title already accepts 404, an
            # unresolvable reference means the same thing: nothing there to clean.
            if 404 in allowed:
                self.record(title, True, f"skipped: {exc}")
            else:
                self.record(title, False, str(exc))
            return
        if self.host:
            url = re.sub(r"^https?://[^/]+", self.host, url)

        try:
            response = requests.request(
                method.upper(), url, headers=headers, data=body.encode("utf-8") or None, timeout=30
            )
        except requests.RequestException as exc:
            self.record(title, False, f"request failed: {exc}")
            return
        if name:
            self.responses[name] = response
        self.note_touched(url)

        if expected:
            ok = response.status_code in allowed
            detail = "" if ok else f"expected {expected.group(1)}, got {response.status_code}"
        else:
            ok = 200 <= response.status_code < 300
            detail = "" if ok else f"expected 2xx, got {response.status_code}"

        if ok and expects:
            ok, detail = self.check_expects(response, expects)
        if not ok:
            detail += f" :: {response.text[:200]}"
        if self.verbose and ok:
            detail = f"{response.status_code} {response.text[:120]}"
        self.record(title, ok, detail)

    def check_expects(self, response, expects) -> tuple[bool, str]:
        try:
            body = response.json()
        except ValueError:
            return False, "body is not JSON"
        for path, op, raw in expects:
            try:
                raw = self.resolve(raw)  # `{{deal}}` in an expectation means the captured name
            except HttpError as exc:
                return False, f"@expect {path}: {exc}"
            try:
                actual = json_path(body, path)
                present = True
            except (KeyError, IndexError, TypeError):
                actual, present = None, False
            try:
                wanted = json.loads(raw) if raw else None
            except ValueError:
                wanted = raw
            if op == "exists":
                passed = present
            elif op == "absent":
                passed = not present
            elif op == "==":
                passed = present and (actual == wanted or str(actual) == raw)
            elif op == "!=":
                passed = present and not (actual == wanted or str(actual) == raw)
            elif op in ("contains", "excludes"):
                haystack = actual if isinstance(actual, str) else json.dumps(actual)
                passed = present and ((raw in haystack) == (op == "contains"))
            else:  # count
                passed = present and isinstance(actual, (list, dict)) and len(actual) == int(raw)
            if not passed:
                shown = json.dumps(actual)[:80] if present else "<absent>"
                return False, f"@expect {path} {op} {raw} failed, actual {shown}"
        return True, ""

    def note_touched(self, url: str) -> None:
        path = unquote(re.sub(r"^https?://[^/]+", "", url).split("?", 1)[0])
        if m := re.match(r"^/api/method/([\w./-]+)/?$", path):
            self.touched.add(m.group(1))
        elif m := re.match(r"^/api/resource/([^/]+)", path):
            self.touched.add(m.group(1))

    def record(self, title: str, ok: bool, detail: str) -> None:
        self.results.append((title, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {title}" + (f"  -- {detail}" if detail else ""))

    # -- whole file -------------------------------------------------------------------

    def run(self) -> bool:
        print(f"\n{self.path.name}")
        for title, lines in split_blocks(self.path.read_text(encoding="utf-8")):
            self.run_block(title, lines)
        failed = [r for r in self.results if not r[1]]
        print(f"  {len(self.results) - len(failed)} of {len(self.results)} passed")
        return not failed


# ----------------------------------------------------------------------------- marking


def mark_routes(touched: set[str], label: str) -> int:
    """Write ``label`` into the Tested cell of every ROUTES.md row whose key was touched."""
    if not ROUTES.exists():
        return 0
    lines = ROUTES.read_text(encoding="utf-8").splitlines()
    hit = 0
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if len(cells) < 3 or not cells[0].isdigit():
            continue
        key = cells[1].strip("`")
        if key in touched and label not in cells[-1]:
            cells[-1] = f"{cells[-1]}, {label}" if cells[-1] else f"✅ {label}"
            lines[i] = "| " + " | ".join(cells) + " |"
            hit += 1
    ROUTES.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return hit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--host", help="override the scheme://host:port in every request")
    parser.add_argument("--mark", action="store_true", help="record green files in docs/ROUTES.md")
    parser.add_argument("-v", "--verbose", action="store_true", help="show status and body on PASS too")
    args = parser.parse_args()

    all_ok = True
    for path in args.files:
        runner = Runner(path, args.host, args.verbose)
        ok = runner.run()
        all_ok &= ok
        if args.mark:
            failed = sum(1 for r in runner.results if not r[1])
            # A file whose only red lines are logged findings has still tested every row
            # it touched; the mark says so and counts the red lines, so the inventory
            # distinguishes "covered, clean" from "covered, with open findings".
            label = f"{dt.date.today():%d %b} — {path.stem}"
            if failed:
                label += f" ({failed} red, see FINDINGS.md)"
            print(f"  marked {mark_routes(runner.touched, label)} rows in ROUTES.md")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
