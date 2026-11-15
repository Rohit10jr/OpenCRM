"""Keep production API URL patterns and built route-map rows in lockstep."""

import re
from pathlib import Path

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, resolve


PORT_MAP = Path(__file__).resolve().parents[2] / "docs" / "PORT_MAP.md"
METHODS = {"GET", "POST", "PATCH", "DELETE"}
ROUTE = re.compile(r"\b(GET|POST|PATCH|DELETE) (/api/v1/[^\s`,;]+)")
PLACEHOLDER = re.compile(r"<[^>]+>")


def _cells(line):
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _is_separator(cells):
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def parse_built_routes(text):
    """Return concrete built method-path pairs, rejecting malformed route tables."""
    lines = text.splitlines()
    routes = set()
    index = 0
    while index + 1 < len(lines):
        header = _cells(lines[index])
        separator = _cells(lines[index + 1])
        if not header or not separator or not _is_separator(separator):
            index += 1
            continue
        if len(separator) != len(header):
            raise AssertionError(f"Malformed table separator at line {index + 2}")

        index += 2
        route_table = "New route" in header and "Status" in header
        while index < len(lines):
            row = _cells(lines[index])
            if row is None:
                if lines[index].lstrip().startswith("|"):
                    raise AssertionError(f"Malformed table row at line {index + 1}")
                break
            if len(row) != len(header):
                raise AssertionError(f"Malformed table row at line {index + 1}")
            if route_table:
                values = dict(zip(header, row))
                if values["Status"].strip("` ") == "built":
                    matches = ROUTE.findall(values["New route"])
                    if "/api/v1/" in values["New route"] and not matches:
                        raise AssertionError(
                            f"Malformed built New route at line {index + 1}: "
                            f"{values['New route']}"
                        )
                    routes.update(
                        (method, path.rstrip("."))
                        for method, path in matches
                        if "<resource>" not in path and "<settings>" not in path
                    )
            index += 1
    return routes


def _normalise_pattern(pattern):
    value = str(pattern)
    value = value.removeprefix("^").removesuffix("$").removesuffix(r"\Z")
    value = re.sub(r"\(\?P<[^>]+>[^)]+\)", "<name>", value)
    value = value.replace("/?", "/").replace("\\", "")
    return value


def _allowed_methods(callback):
    actions = getattr(callback, "actions", None)
    if actions is not None:
        return {method.upper() for method in actions if method.upper() in METHODS}
    view_class = getattr(callback, "view_class", None)
    if view_class is None:
        return set()
    return {
        method.upper()
        for method in view_class.http_method_names
        if method.upper() in METHODS and hasattr(view_class, method)
    }


def _served_routes():
    found = set()

    def walk(patterns, prefix=""):
        for pattern in patterns:
            route = prefix + _normalise_pattern(pattern.pattern)
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, route)
            elif isinstance(pattern, URLPattern) and route.startswith("api/v1/"):
                path = "/" + route
                for method in _allowed_methods(pattern.callback):
                    found.add((method, path))

    walk(get_resolver("config.urls").url_patterns)
    return found


def test_every_built_concrete_route_resolves_and_accepts_its_method():
    routes = parse_built_routes(PORT_MAP.read_text(encoding="utf-8"))
    for method, template in sorted(routes):
        path = PLACEHOLDER.sub("guard-value", template)
        match = resolve(path, urlconf="config.urls")
        assert method in _allowed_methods(match.func), (
            f"{method} {template} is not served"
        )


def test_every_production_api_pattern_is_recorded_as_built():
    mapped = parse_built_routes(PORT_MAP.read_text(encoding="utf-8"))
    served = _served_routes()
    assert served == mapped, (
        f"Production routes missing from PORT_MAP: {sorted(served - mapped)}; "
        f"built PORT_MAP routes not served: {sorted(mapped - served)}"
    )


def test_malformed_route_table_rows_fail_loudly():
    malformed = """\
| Dotted path | New route | Status |
|---|---|---|
| `example` | `GET /api/v1/example/` |
"""
    with pytest.raises(AssertionError, match="Malformed table row"):
        parse_built_routes(malformed)
