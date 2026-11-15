"""Replay generated REST Client files and check their recorded expectations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

try:
    from scripts.http_parser import HttpBlock, json_path, parse_http
except ModuleNotFoundError:  # direct: python scripts/run_http.py
    from http_parser import HttpBlock, json_path, parse_http


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".env"
Request = Callable[..., requests.Response]
SUBSTITUTION_RE = re.compile(r"\{\{([^{}]+)\}\}")


class ReplayError(ValueError):
    """A request block cannot be resolved safely."""


@dataclass
class BlockResult:
    title: str
    outcome: str
    detail: str = ""
    response: requests.Response | None = None


def load_dotenv(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


class HttpRunner:
    """Stateful replay context; captured responses belong to this runner only."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30,
        request: Request = requests.request,
        dotenv_path: Path = DEFAULT_ENV,
        output: Callable[[str], None] = print,
    ):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout
        self.request = request
        self.output = output
        self.variables: dict[str, str] = {}
        self.responses: dict[str, requests.Response] = {}
        self.dotenv_path = dotenv_path
        self.secrets = load_dotenv(dotenv_path)

    def redact(self, value: object) -> str:
        text = str(value)
        for secret in sorted((v for v in self.secrets.values() if v), key=len, reverse=True):
            text = text.replace(secret, "<redacted>")
        return text

    def resolve(self, text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            expression = match.group(1).strip()
            if expression.startswith("$dotenv"):
                parts = expression.split(None, 1)
                key = parts[1].lstrip("%").strip() if len(parts) == 2 else ""
                if key not in self.secrets:
                    raise ReplayError(f"{key or 'dotenv key'} is not in {self.dotenv_path}")
                return self.secrets[key]
            if ".response." in expression:
                label, _, reference = expression.partition(".response.")
                if label not in self.responses:
                    raise ReplayError(f"no response named {label!r} yet")
                response = self.responses[label]
                if reference.startswith("body."):
                    try:
                        value = json_path(response.json(), reference[5:])
                    except (ValueError, KeyError, IndexError, TypeError):
                        raise ReplayError(f"{expression}: response value not found") from None
                    return value if isinstance(value, str) else json.dumps(value)
                if reference.startswith("headers."):
                    return response.headers.get(reference[8:], "")
                raise ReplayError(f"unsupported response reference {expression}")
            if expression in self.variables:
                return self.resolve(self.variables[expression])
            raise ReplayError(f"unknown variable {expression}")

        return SUBSTITUTION_RE.sub(replace, text)

    def prepare(self, block: HttpBlock) -> tuple[str, str, dict[str, str], str] | None:
        for name, value in block.variables():
            self.variables[name] = value
        if block.request is None:
            return None
        method, raw_url = block.request
        url = self.resolve(raw_url)
        if self.base_url:
            url = re.sub(r"^https?://[^/]+", self.base_url, url)
        raw_headers, raw_body = block.headers_and_body()
        headers = {}
        for header in raw_headers:
            key, separator, value = header.partition(":")
            if not separator:
                raise ReplayError(f"invalid header {header!r}")
            headers[key.strip()] = self.resolve(value.strip())
        return method, url, headers, self.resolve(raw_body) if raw_body else ""

    def check_expectations(self, block: HttpBlock, response: requests.Response) -> str:
        if not block.expectations:
            return ""
        try:
            body = response.json()
        except ValueError:
            return "body is not JSON"
        for expectation in block.expectations:
            raw = self.resolve(expectation.value)
            try:
                actual, present = json_path(body, expectation.path), True
            except (KeyError, IndexError, TypeError):
                actual, present = None, False
            try:
                wanted = json.loads(raw) if raw else None
            except ValueError:
                wanted = raw
            operator = expectation.operator
            if operator == "exists":
                passed = present
            elif operator == "absent":
                passed = not present
            elif operator == "==":
                passed = present and (actual == wanted or str(actual) == raw)
            elif operator == "!=":
                passed = present and not (actual == wanted or str(actual) == raw)
            elif operator in {"contains", "excludes"}:
                haystack = actual if isinstance(actual, str) else json.dumps(actual)
                passed = present and ((raw in haystack) == (operator == "contains"))
            else:
                try:
                    passed = present and isinstance(actual, (list, dict)) and len(actual) == int(raw)
                except ValueError:
                    passed = False
            if not passed:
                shown = json.dumps(actual)[:80] if present else "<absent>"
                return f"@expect {expectation.path} {operator} {raw} failed, actual {shown}"
        return ""

    def run_block(self, block: HttpBlock, check: bool = True) -> BlockResult | None:
        title = block.title or "(untitled)"
        if "# @waiting" in "\n".join(block.lines):
            return BlockResult(title, "skipped", "waiting for its unit")
        try:
            prepared = self.prepare(block)
        except ReplayError as exc:
            if 404 in block.expected_statuses:
                return BlockResult(title, "skipped", f"cleanup reference unavailable: {exc}")
            return BlockResult(title, "fail", self.redact(exc))
        if prepared is None:
            return None
        method, url, headers, body = prepared
        try:
            response = self.request(
                method, url, headers=headers, data=body.encode("utf-8") or None, timeout=self.timeout
            )
        except requests.RequestException as exc:
            host = self.base_url or re.match(r"^https?://[^/]+", url).group(0)
            return BlockResult(title, "fail", self.redact(f"server {host} is not reachable: {exc}"))
        if block.name:
            self.responses[block.name] = response
        if not check:
            return BlockResult(title, "pass", response=response)
        allowed = block.expected_statuses
        good_status = response.status_code in allowed if allowed else 200 <= response.status_code < 300
        if not good_status:
            expected = "|".join(map(str, sorted(allowed))) if allowed else "2xx"
            detail = f"expected {expected}, got {response.status_code} :: {response.text[:200]}"
            return BlockResult(title, "fail", self.redact(detail), response)
        try:
            detail = self.check_expectations(block, response)
        except ReplayError as exc:
            detail = str(exc)
        return BlockResult(title, "fail" if detail else "pass", self.redact(detail), response)

    def run_file(self, path: Path) -> bool:
        self.output(path.name)
        results = []
        for block in parse_http(path.read_text(encoding="utf-8")).blocks:
            result = self.run_block(block)
            if result is None:
                continue
            results.append(result)
            marker = {"pass": "PASS", "fail": "FAIL", "skipped": "SKIP"}[result.outcome]
            detail = f" -- {result.detail}" if result.detail else ""
            self.output(self.redact(f"  [{marker}] {result.title}{detail}"))
        counts = {kind: sum(result.outcome == kind for result in results) for kind in ("pass", "fail", "skipped")}
        self.output(f"  {counts['pass']} passed, {counts['fail']} failed, {counts['skipped']} skipped")
        return counts["fail"] == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--new", default="http://localhost:8001", help="new server base URL")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    okay = True
    for path in args.files:
        okay = HttpRunner(args.new, args.timeout).run_file(path) and okay
    return 0 if okay else 1


if __name__ == "__main__":
    sys.exit(main())
