"""Generate the REST API copy of every legacy ``docs/http`` walkthrough file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

try:  # Imported by pytest from backend_v2, or executed directly from scripts/.
    from scripts.http_parser import HttpBlock, HttpParseError, parse_http, resolve_variables
except ModuleNotFoundError:  # pragma: no cover - the direct-script import path
    from http_parser import HttpBlock, HttpParseError, parse_http, resolve_variables


ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT / "docs" / "http"
OUTPUT_DIR = ROOT / "backend_v2" / "http"
ROUTE_MAP = ROOT / "backend_v2" / "docs" / "PORT_MAP.md"
TABLE_SEPARATOR_RE = re.compile(r":?-{3,}:?")
NEW_ROUTE_RE = re.compile(r"\b(GET|POST|PATCH|DELETE)\s+(/api/v1/[^\s`,;]+)")
METHOD_URL_RE = re.compile(r"/api/method/([^?]+)")
RESOURCE_URL_RE = re.compile(r"/api/resource/([^/?]+)(?:/([^?]+))?")
GENERIC_CALLS = {
    "frappe.client.get",
    "frappe.client.get_list",
    "frappe.client.insert",
    "frappe.client.set_value",
    "frappe.client.delete",
    "frappe.client.get_value",
    "frappe.client.get_single_value",
    "frappe.client.get_doc_permissions",
}


class SuiteBuildError(ValueError):
    pass


@dataclass(frozen=True)
class RouteEntry:
    key: str
    unit: str
    status: str
    new_route: str = ""
    access: str = ""

    @property
    def built(self) -> bool:
        return self.status == "built"

    @property
    def routes(self) -> list[tuple[str, str]]:
        return NEW_ROUTE_RE.findall(self.new_route)


@dataclass
class RouteMap:
    methods: dict[str, RouteEntry]
    doctypes: dict[str, RouteEntry]
    negative_methods: dict[str, str]


def _cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _plain(value: str) -> str:
    return value.strip().strip("`").strip()


def parse_route_map(text: str) -> RouteMap:
    """Read method and doctype tables, rejecting malformed rows with line numbers."""
    lines = text.splitlines()
    methods: dict[str, RouteEntry] = {}
    doctypes: dict[str, RouteEntry] = {}
    negative_methods: dict[str, str] = {}
    unit = ""
    index = 0
    while index < len(lines):
        if match := re.match(r"^## ([A-Z][A-Z_]*)\s*$", lines[index]):
            unit = match.group(1)
        header = _cells(lines[index])
        if not header or index + 1 >= len(lines):
            index += 1
            continue
        separator = _cells(lines[index + 1])
        if not separator or not all(TABLE_SEPARATOR_RE.fullmatch(cell) for cell in separator):
            index += 1
            continue
        if len(separator) != len(header):
            raise SuiteBuildError(f"malformed table separator at line {index + 2}")
        relevant = "Status" in header and ("Dotted path" in header or "DocType" in header)
        negative_table = header == ["Route", "New app", "Unit", "Status"]
        index += 2
        while index < len(lines):
            row = _cells(lines[index])
            if row is None:
                if relevant and lines[index].lstrip().startswith("|"):
                    raise SuiteBuildError(f"malformed route-map row at line {index + 1}")
                break
            if len(row) != len(header):
                if relevant:
                    raise SuiteBuildError(f"malformed route-map row at line {index + 1}")
                index += 1
                continue
            if relevant:
                values = dict(zip(header, row))
                key_column = "Dotted path" if "Dotted path" in header else "DocType"
                key = _plain(values[key_column])
                route = values.get("New route", "")
                status = _plain(values["Status"])
                if status == "built" and "/api/v1/" in route and not NEW_ROUTE_RE.search(route):
                    raise SuiteBuildError(
                        f"malformed built New route at line {index + 1}: {route}"
                    )
                entry = RouteEntry(key, unit, status, route, _plain(values.get("Access", "")))
                target = methods if key_column == "Dotted path" else doctypes
                if key in target:
                    raise SuiteBuildError(f"duplicate route-map row {key!r} at line {index + 1}")
                target[key] = entry
            elif negative_table:
                match = re.search(
                    r"`/api/method/([^`]+)`\s*→\s*`(/api/v1/[^`]+)`\s*—\s*negative",
                    row[0],
                )
                if match:
                    negative_methods[match.group(1)] = match.group(2)
            index += 1
    return RouteMap(methods, doctypes, negative_methods)


def _replace_status(title: str, status: int) -> str:
    if re.search(r"->\s*\d{3}(?:\|\d{3})*", title):
        return re.sub(r"->\s*\d{3}(?:\|\d{3})*", f"-> {status}", title, count=1)
    return f"{title} -> {status}".strip()


def _annotate(block: HttpBlock, marker: str) -> None:
    if marker not in block.lines:
        block.lines.insert(0, marker)


def _mark_cleanup_blocks(blocks: list[HttpBlock]) -> None:
    under_cleanup_heading = False
    for block in blocks:
        if any("cleanup first" in line.lower() for line in block.lines):
            under_cleanup_heading = True
        title = block.title or ""
        numbered_cleanup = under_cleanup_heading and bool(re.match(r"0\.\d", title))
        titled_cleanup = bool(re.match(r"(?:\d+(?:\.\d+)*[a-z]?\s+)?clean[ -]?up\b", title, re.I))
        if block.request and (numbered_cleanup or titled_cleanup):
            _annotate(block, "# @cleanup")
        if under_cleanup_heading and title and not re.match(r"0\.\d", title):
            under_cleanup_heading = False


def _replace_request(block: HttpBlock, method: str, url: str, body: dict | None = None) -> None:
    index = block.request_index
    assert index is not None
    block.lines[index] = f"{method} {url}"
    if body is None:
        return
    headers, _ = block.headers_and_body()
    end = index + 1
    while end < len(block.lines) and (block.lines[end].strip() or end == index + 1):
        if end > index + 1 and ":" not in block.lines[end]:
            break
        end += 1
    while end < len(block.lines) and not block.lines[end].strip():
        end += 1
    block.lines = block.lines[: index + 1] + headers + ["", json.dumps(body)] + _tail(block)


def _tail(block: HttpBlock) -> list[str]:
    """The block's trailing blank and comment lines: the blank line before the next `###`
    and often the next section's heading. Every rewrite that cuts a block keeps them."""
    index = block.request_index
    assert index is not None
    start = len(block.lines)
    while start > index + 1 and (
        not block.lines[start - 1].strip()
        or block.lines[start - 1].startswith(("#", "//"))
    ):
        start -= 1
    return block.lines[start:]


def _payload(block: HttpBlock, url: str) -> dict:
    _, body = block.headers_and_body()
    data: dict = {}
    if body:
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise SuiteBuildError(
                f"line {block.start_line}: invalid JSON body: {exc.msg}"
            ) from exc
        if not isinstance(decoded, dict):
            raise SuiteBuildError(f"line {block.start_line}: request body must be an object")
        data.update(decoded)
    query = urlsplit(url).query
    for item in query.split("&") if query else []:
        key, _, value = item.partition("=")
        data.setdefault(key, value)
    return data


def _doctype_from_generic(path: str, payload: dict) -> str | None:
    if path == "frappe.client.insert":
        doc = payload.get("doc")
        if isinstance(doc, str):
            try:
                doc = json.loads(doc)
            except json.JSONDecodeError:
                return None
        return doc.get("doctype") if isinstance(doc, dict) else None
    value = payload.get("doctype")
    return value if isinstance(value, str) and "{{" not in value else None


def _is_singleton(entry: RouteEntry) -> bool:
    """A settings record served at its resource root (S25 (3)), with no name segment."""
    return "(singleton" in entry.new_route


#: PE-11: a list-shaped read of a settings record is retired, naming the block that
#: covers it (A-30, A-31's follow-up). Absent: no other block covers it.
RETIRED_COVERED_BY = {
    ("12_settings_singletons.http", "1.3"): "1.2",
    ("12_settings_singletons.http", "1.4"): "1.11",
}


def _retire_list_read(block: HttpBlock, filename: str) -> None:
    number = (block.title or "").split(" ", 1)[0]
    covered = RETIRED_COVERED_BY.get((filename, number))
    cover = f"covered by {covered}" if covered else "no other block covers it"
    index = block.request_index
    assert index is not None
    block.lines = (
        block.lines[:index]
        + [f"# @retired PE-11: a settings record has no list route; {cover}"]
        + _tail(block)
    )


def _resource_path(entry: RouteEntry, method: str, has_name: bool) -> str | None:
    if _is_singleton(entry):
        has_name = False
    candidates = entry.routes
    for candidate_method, path in candidates:
        named = "<name>" in path
        if candidate_method == method and named == has_name:
            return path
    bases = re.findall(r"(/api/v1/[^\s`,;]+/)", entry.new_route)
    if bases:
        base = bases[0]
        return f"{base}<name>/" if has_name else base
    return None


def _document_entry(routes: RouteMap, doctype: str | None, fallback: RouteEntry) -> RouteEntry:
    if doctype and doctype in routes.doctypes:
        return routes.doctypes[doctype]
    return fallback


def _rewrite_search_link(
    block: HttpBlock,
    method: str,
    resolved_url: str,
    entry: RouteEntry,
    routes: RouteMap,
) -> None:
    payload = _payload(block, resolved_url)
    doctype = payload.get("doctype")
    if doctype != "DocType":
        resource = routes.doctypes.get(doctype) if isinstance(doctype, str) else None
        searches = [
            (verb, path)
            for verb, path in (resource.routes if resource and resource.built else [])
            if path.rstrip("/").endswith("/search")
        ]
        if not searches:
            _annotate(block, f"# @waiting {(resource or entry).unit}")
            return
        # A built resource that opts in to search answers on its own search/ route.
        entry = RouteEntry(resource.key, resource.unit, resource.status, " ".join(
            f"`{verb} {path}`" for verb, path in searches
        ))
    allowed = {verb for verb, _ in entry.routes}
    route = entry.routes[0][1]
    if method not in allowed:
        _negative(block, method, route)
        return
    route = next(path for verb, path in entry.routes if verb == method)
    body = dict(payload)
    body.pop("doctype", None)
    _replace_request(block, method, "{{host}}" + route, body)


def _rewrite_generic(
    block: HttpBlock, path: str, url: str, entry: RouteEntry, routes: RouteMap
) -> bool:
    payload = _payload(block, url)
    doctype = _doctype_from_generic(path, payload)
    if doctype and doctype not in routes.doctypes:
        slug = re.sub(r"[^a-z0-9]+", "-", doctype.lower()).strip("-")
        name = payload.get("name")
        suffix = f"{name}/" if name else ""
        _replace_request(block, "GET", f"{{{{host}}}}/api/v1/{slug}/{suffix}")
        _annotate(block, "# @negative")
        return True
    resource = _document_entry(routes, doctype, entry)
    if path == "frappe.client.get" and "filters" in payload and "name" not in payload:
        _comment_not_served(block)
        return True
    if not resource.built or not resource.new_route or not doctype:
        _annotate(block, f"# @waiting {resource.unit or entry.unit}")
        return True

    name = payload.get("name")
    method = {
        "frappe.client.get": "GET",
        "frappe.client.get_list": "GET",
        "frappe.client.insert": "POST",
        "frappe.client.set_value": "PATCH",
        "frappe.client.delete": "DELETE",
        "frappe.client.get_value": "GET",
        "frappe.client.get_single_value": "GET",
        "frappe.client.get_doc_permissions": "GET",
    }[path]
    has_name = path in {
        "frappe.client.get",
        "frappe.client.set_value",
        "frappe.client.delete",
        "frappe.client.get_doc_permissions",
    }
    target = _resource_path(resource, method, has_name)
    if target is None:
        raise SuiteBuildError(f"line {block.start_line}: no {method} route for {doctype}")
    if has_name:
        target = target.replace("<name>", str(name))
    if path == "frappe.client.get_doc_permissions":
        target = target.rstrip("/") + "/permissions/"
    elif path == "frappe.client.get_value":
        target = target.rstrip("/") + "/value/"
    elif path == "frappe.client.get_single_value":
        target = target.rstrip("/") + "/value/"

    body = dict(payload)
    body.pop("doctype", None)
    body.pop("name", None)
    if path == "frappe.client.insert":
        doc = body.pop("doc", {})
        if isinstance(doc, str):
            doc = json.loads(doc)
        body = {key: value for key, value in doc.items() if key != "doctype"}
    elif path == "frappe.client.set_value":
        body = {str(body.pop("fieldname")): body.pop("value")}
    if method == "GET":
        # A GET route reads its query, not a body (A-32 finding 1).
        query = _query_string(body)
        _replace_request(block, "GET", "{{host}}" + target + (f"?{query}" if query else ""))
        _drop_body(block)
        return True
    _replace_request(block, method, "{{host}}" + target, body)
    return True


def _comment_not_served(block: HttpBlock) -> None:
    index = block.request_index
    assert index is not None
    block.lines = (
        block.lines[:index]
        + ["# @not-served PE-3: frappe.client.get by filters has no REST route"]
        + _tail(block)
    )


def _rewrite_resource(
    block: HttpBlock,
    method: str,
    resolved_url: str,
    routes: RouteMap,
    filename: str = "fixture.http",
) -> str | None:
    match = RESOURCE_URL_RE.search(resolved_url)
    if not match:
        return None
    doctype = unquote(match.group(1))
    name = match.group(2)
    entry = routes.doctypes.get(doctype)
    if entry is None:
        slug = re.sub(r"[^a-z0-9]+", "-", doctype.lower()).strip("-")
        _replace_request(block, method, f"{{{{host}}}}/api/v1/{slug}/")
        _annotate(block, "# @negative")
        return None
    if not entry.built or not entry.new_route:
        _annotate(block, f"# @waiting {entry.unit}")
        return None
    new_method = "PATCH" if method == "PUT" else method
    if _is_singleton(entry):
        if name is None and new_method == "GET":
            _retire_list_read(block, filename)
            return None
        root = min((path for _, path in entry.routes), key=len)
        served = {verb for verb, path in entry.routes if path == root}
        if new_method not in served:
            # A verb the settings record does not serve is a wrong-verb 405 (PE-1).
            _negative(block, new_method, root)
            return None
    target = _resource_path(entry, new_method, name is not None)
    if target is None:
        raise SuiteBuildError(f"line {block.start_line}: no {new_method} route for {doctype}")
    if name is not None:
        target = target.replace("<name>", name)
    # A list's own query (`fields`, `limit_page_length`, …) keeps its meaning on the new route.
    if query := urlsplit(block.request[1]).query:
        target = f"{target}?{query}"
    _, body = block.headers_and_body()
    parsed_body = json.loads(body) if body else None
    _replace_request(block, new_method, "{{host}}" + target, parsed_body)
    for index, line in enumerate(block.lines):
        block.lines[index] = line.replace("$.data", "$.message")
    if block.title and 201 in block.expected_statuses:
        block.title = _replace_status(block.title, 200)
        block.separator = "### " + block.title
    _annotate(block, "# @resource-envelope {\"data\"}/201 -> {\"message\"}/200")
    return block.name


def _query_string(payload: dict) -> str:
    """A body as query parameters; `{{variables}}` stay readable for the runner."""
    parts = []
    for key, value in payload.items():
        if not isinstance(value, str):
            value = json.dumps(value, separators=(",", ":"))
        parts.append(f"{quote(str(key), safe='')}={quote(value, safe='{}')}")
    return "&".join(parts)


def _url_key(entry: RouteEntry) -> str | None:
    """The input a route moves into its `<name>`, as the route map writes it."""
    match = re.search(r"`(\w+)` in the URL", entry.new_route)
    return match.group(1) if match else None


#: Routes answering 404 for a doctype that is not served (configuration/metadata.py).
DOCTYPE_CHECKING_PREFIXES = (
    "/api/v1/meta/",
    "/api/v1/fields-layouts/layout/",
    "/api/v1/fields-layouts/sidepanel-sections/",
    "/api/v1/fields-layouts/save/",
)


def _waits_for_its_doctype(
    block: HttpBlock, url: str, entry: RouteEntry, routes: RouteMap | None
) -> bool:
    """A route that checks the doctype it is asked about (the meta/ and layout calls)
    asked about a doctype whose resource is not built yet waits for that unit: it would
    answer 404 until then. An unknown doctype is left alone, since its 404 is what the
    block expects (CONFIGURATION milestones 5 and 6). user-settings/ takes a doctype too
    but does not check it, so it runs."""
    if routes is None or not any(
        path.startswith(DOCTYPE_CHECKING_PREFIXES) for _, path in entry.routes
    ):
        return False
    doctype = _payload(block, url).get("doctype")
    resource = routes.doctypes.get(unquote(doctype)) if isinstance(doctype, str) else None
    if resource is None or resource.built:
        return False
    _annotate(block, f"# @waiting {resource.unit}")
    return True


def _rewrite_method(
    block: HttpBlock, method: str, url: str, entry: RouteEntry, routes: RouteMap | None = None
) -> None:
    """A built method path. Its route map row may reshape two inputs (S8): an old POST
    body moves into the query of a route served by GET alone, and a named input moves
    into the URL's `<name>`."""
    if _waits_for_its_doctype(block, url, entry, routes):
        return
    allowed = {verb for verb, _ in entry.routes}
    new_method = method
    if method not in allowed:
        if method == "POST" and allowed == {"GET"}:
            new_method = "GET"
        else:
            _negative(block, method, entry.routes[0][1])
            return
    route = next(path for verb, path in entry.routes if verb == new_method)
    payload = _payload(block, url)
    if "<name>" in route:
        key = _url_key(entry)
        if key is None or key not in payload:
            raise SuiteBuildError(
                f"line {block.start_line}: no input for <name> in {route}"
            )
        route = route.replace("<name>", str(payload.pop(key)))
    if new_method == "GET":
        query = _query_string(payload)
        _replace_request(block, "GET", "{{host}}" + route + (f"?{query}" if query else ""))
        _drop_body(block)
    elif "<name>" in entry.new_route:
        _replace_request(block, new_method, "{{host}}" + route, payload)
    else:
        _replace_request(block, new_method, "{{host}}" + route)


def _drop_body(block: HttpBlock) -> None:
    index = block.request_index
    assert index is not None
    headers, _ = block.headers_and_body()
    block.lines = (
        block.lines[: index + 1]
        + [line for line in headers if not line.lower().startswith("content-type")]
        + _tail(block)
    )


def _negative(block: HttpBlock, method: str, route: str) -> None:
    block.lines = [line for line in block.lines if not line.startswith("# @expect ")]
    _replace_request(block, method, "{{host}}" + route)
    _annotate(block, "# @expect $.exc_type == MethodNotAllowed")
    _annotate(block, "# @negative")
    block.title = _replace_status(block.title or "", 405)
    block.separator = "### " + block.title


def _route_is_guest(route_map: RouteMap, route: str) -> bool:
    return any(
        entry.access == "guest" and route in {path for _, path in entry.routes}
        for entry in route_map.methods.values()
    )


def _unknown_path(block: HttpBlock, method: str, route: str) -> None:
    """The route map's unknown-path case: no route serves it, so the answer is 404
    DoesNotExistError (PE-1: an unknown URL is 404), not a wrong-verb 405 (A-25)."""
    block.lines = [line for line in block.lines if not line.startswith("# @expect ")]
    _replace_request(block, method, "{{host}}" + route)
    _annotate(block, "# @expect $.exc_type == DoesNotExistError")
    _annotate(block, "# @negative")
    block.title = _replace_status(block.title or "", 404)
    block.separator = "### " + block.title


def _added_negative(
    title: str, method: str, route: str, route_map: RouteMap, token: str = "{{token}}"
) -> HttpBlock:
    """A wrong-verb case the old file lacks. A route that is not guest gets the file's
    bearer token, so the request passes authentication and reaches the method check
    (DRF authenticates first; without a token the answer is 401, A-25)."""
    lines = [
        "# @negative",
        "# @expect $.exc_type == MethodNotAllowed",
        f"{method} {{{{host}}}}{route}",
    ]
    if not _route_is_guest(route_map, route):
        lines.append(f"Authorization: Bearer {token}")
    return HttpBlock(title=title, separator="### " + title, lines=lines)


def _section(block: HttpBlock) -> str | None:
    match = re.match(r"(\d+)\.", block.title or "")
    return match.group(1) if match else None


VARIABLE_USE_RE = re.compile(r"\{\{\s*([A-Za-z_]\w*)")


def _story_variables(block: HttpBlock) -> set[str]:
    """The variables a request reads, less the host and the bearer tokens every block
    shares."""
    request_lines = [line for line in block.lines if not line.startswith(("#", "@"))]
    names = set(VARIABLE_USE_RE.findall("\n".join(request_lines)))
    return {name for name in names if name != "host" and not name.endswith("token")}


def _wait_after_waiting(blocks: list[HttpBlock]) -> None:
    """A block that reads the state an earlier waiting block of its numbered section was
    to set up waits too, on the same unit: 01_auth 4.8 logs in with the password 4.7 was
    to change (A-23). "Reads the same state" is approximated by sharing a variable other
    than the host or a token, so an unrelated check in the same section (13 5.8) still
    runs. Negative and cleanup blocks always run."""
    waiting: dict[str, list[tuple[str, set[str]]]] = {}
    for block in blocks:
        section = _section(block)
        if section is None or block.request is None:
            continue
        variables = _story_variables(block)
        marker = next((line for line in block.lines if line.startswith("# @waiting ")), None)
        if marker is None and not {"# @negative", "# @cleanup"} & set(block.lines):
            marker = next(
                (earlier for earlier, used in waiting.get(section, []) if used & variables),
                None,
            )
            if marker:
                _annotate(block, marker)
        if marker:
            waiting.setdefault(section, []).append((marker, variables))


def rewrite_http(text: str, route_map: RouteMap, filename: str = "fixture.http") -> str:
    document = parse_http(text)
    _mark_cleanup_blocks(document.blocks)
    variables: dict[str, str] = {}
    resource_names: set[str] = set()
    for block in document.blocks:
        for name, value in block.variables():
            variables[name] = value
        request = block.request
        if request is None:
            continue
        method, raw_url = request
        resolved_url = resolve_variables(raw_url, variables)
        if match := METHOD_URL_RE.search(resolved_url):
            path = unquote(match.group(1))
            entry = route_map.methods.get(path)
            if entry is None:
                if path in route_map.negative_methods:
                    _unknown_path(block, method, route_map.negative_methods[path])
                    continue
                raise SuiteBuildError(
                    f"{filename}:{block.start_line}: method path {path!r} is not in PORT_MAP.md"
                )
            if path == "frappe.desk.search.search_link":
                _rewrite_search_link(block, method, resolved_url, entry, route_map)
            elif path in GENERIC_CALLS:
                if (
                    filename == "13_bulk_and_misc.http"
                    and block.title
                    and re.match(r"2\.[567]\b", block.title)
                ):
                    _comment_not_served(block)
                else:
                    _rewrite_generic(block, path, resolved_url, entry, route_map)
            elif entry.built and entry.routes:
                _rewrite_method(block, method, resolved_url, entry, route_map)
            else:
                _annotate(block, f"# @waiting {entry.unit}")
        elif "/api/resource/" in resolved_url:
            if name := _rewrite_resource(block, method, resolved_url, route_map, filename):
                resource_names.add(name)

    _wait_after_waiting(document.blocks)

    for block in document.blocks:
        block.lines = [
            re.sub(r"^@host\s*=.*$", "@host = http://localhost:8001", line)
            for line in block.lines
        ]
        if resource_names:
            block.lines = [
                re.sub(
                    rf"\{{\{{({'|'.join(map(re.escape, resource_names))})\.response\.body\.\$\.data",
                    r"{{\1.response.body.$.message",
                    line,
                )
                for line in block.lines
            ]

    if filename == "01_auth.http":
        insertion = next(
            index
            for index, block in enumerate(document.blocks)
            if block.title and block.title.startswith("1.13 ")
        )
        document.blocks.insert(
            insertion,
            _added_negative(
                "1.12a POST is refused on who-am-I -> 405",
                "POST",
                "/api/v1/auth/me/",
                route_map,
            ),
        )
        insertion = next(
            index
            for index, block in enumerate(document.blocks)
            if block.title and block.title.startswith("2.12 ")
        )
        document.blocks.insert(
            insertion,
            _added_negative(
                "2.11a GET is refused on token refresh -> 405",
                "GET",
                "/api/v1/auth/token/refresh/",
                route_map,
            ),
        )
    return document.render()


def build_suite(source_dir: Path, output_dir: Path, route_map_path: Path) -> list[Path]:
    routes = parse_route_map(route_map_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for source in sorted(source_dir.glob("*.http")):
        result = rewrite_http(source.read_text(encoding="utf-8"), routes, source.name)
        target = output_dir / source.name
        target.write_text(result, encoding="utf-8", newline="\n")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--route-map", type=Path, default=ROUTE_MAP)
    args = parser.parse_args(argv)
    try:
        written = build_suite(args.source, args.output, args.route_map)
    except (OSError, SuiteBuildError, HttpParseError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(f"wrote {len(written)} files to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
