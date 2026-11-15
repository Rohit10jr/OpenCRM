"""Lossless parsing primitives for the project's REST Client ``.http`` files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field


VARIABLE_RE = re.compile(r"^@([\w-]+)\s*=\s*(.*)$")
SUBSTITUTION_RE = re.compile(r"\{\{([^{}]+)\}\}")
STATUS_RE = re.compile(r"->\s*(\d{3}(?:\|\d{3})*)")
NAME_RE = re.compile(r"^#\s*@name\s+(\S+)")
EXPECT_RE = re.compile(
    r"^#\s*@expect\s+(\S+)\s+(==|!=|contains|excludes|exists|absent|count)\s*(.*)$"
)
REQUEST_RE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)\s+(\S.*)$", re.IGNORECASE)


class HttpParseError(ValueError):
    """An input file cannot be interpreted without silently changing its meaning."""


@dataclass(frozen=True)
class Expectation:
    path: str
    operator: str
    value: str


@dataclass
class HttpBlock:
    """One separator-led block, or the preamble before the first separator."""

    title: str | None
    lines: list[str] = field(default_factory=list)
    separator: str | None = None
    start_line: int = 1

    @property
    def name(self) -> str | None:
        for line in self.lines:
            if match := NAME_RE.match(line):
                return match.group(1)
        return None

    @property
    def expectations(self) -> list[Expectation]:
        found = []
        for line in self.lines:
            if match := EXPECT_RE.match(line):
                found.append(Expectation(*match.groups()))
        return found

    @property
    def expected_statuses(self) -> set[int]:
        match = STATUS_RE.search(self.title or "")
        return {int(value) for value in match.group(1).split("|")} if match else set()

    @property
    def request_index(self) -> int | None:
        for index, line in enumerate(self.lines):
            if REQUEST_RE.match(line):
                return index
        return None

    @property
    def request(self) -> tuple[str, str] | None:
        index = self.request_index
        if index is None:
            return None
        match = REQUEST_RE.match(self.lines[index])
        assert match is not None
        return match.group(1).upper(), match.group(2)

    def headers_and_body(self) -> tuple[list[str], str]:
        index = self.request_index
        if index is None:
            return [], ""
        index += 1
        headers = []
        while index < len(self.lines) and self.lines[index].strip():
            if self.lines[index].startswith(("#", "//")):
                index += 1
                continue
            if ":" not in self.lines[index]:
                break
            headers.append(self.lines[index])
            index += 1
        if index < len(self.lines) and not self.lines[index].strip():
            index += 1
        body_lines = [
            line for line in self.lines[index:] if not line.startswith(("#", "//"))
        ]
        return headers, "\n".join(body_lines).strip()

    def variables(self) -> list[tuple[str, str]]:
        return [match.groups() for line in self.lines if (match := VARIABLE_RE.match(line))]


@dataclass
class HttpFile:
    blocks: list[HttpBlock]
    trailing_newline: bool = True

    def render(self) -> str:
        lines: list[str] = []
        for block in self.blocks:
            if block.separator is not None:
                lines.append(block.separator)
            lines.extend(block.lines)
        text = "\n".join(lines)
        return text + ("\n" if self.trailing_newline else "")


def parse_http(text: str) -> HttpFile:
    """Split text like the reference runner while retaining separators and comments."""
    blocks = [HttpBlock(title=None, start_line=1)]
    for line_number, line in enumerate(text.splitlines(), 1):
        if line.startswith("###"):
            blocks.append(
                HttpBlock(
                    title=line[3:].strip(),
                    separator=line,
                    start_line=line_number,
                )
            )
        else:
            blocks[-1].lines.append(line)
    return HttpFile(blocks, text.endswith(("\n", "\r")))


def resolve_variables(value: str, variables: dict[str, str]) -> str:
    """Resolve file variables recursively, leaving runtime-only expressions intact."""
    seen: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        expression = match.group(1).strip()
        if expression.startswith("$dotenv") or ".response." in expression:
            return match.group(0)
        if expression not in variables:
            return match.group(0)
        if expression in seen:
            raise HttpParseError(f"cyclic variable {expression!r}")
        seen.add(expression)
        try:
            return SUBSTITUTION_RE.sub(replace, variables[expression])
        finally:
            seen.remove(expression)

    previous = None
    while value != previous:
        previous = value
        value = SUBSTITUTION_RE.sub(replace, value)
    return value


def json_path(value, path: str):
    """Read ``$.a.b[0]`` from a decoded JSON value."""
    if path.startswith("$"):
        path = path[1:]
    for key, index in re.findall(r"\.?([^.\[\]]+)|\[(\d+)\]", path):
        value = value[int(index)] if index else value[key]
    return value


def decode_json_body(block: HttpBlock) -> dict:
    """Return an object body, naming the source line when it is not valid JSON."""
    _, body = block.headers_and_body()
    try:
        value = json.loads(body or "{}")
    except json.JSONDecodeError as exc:
        raise HttpParseError(f"line {block.start_line}: invalid JSON body: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise HttpParseError(f"line {block.start_line}: request body must be a JSON object")
    return value
