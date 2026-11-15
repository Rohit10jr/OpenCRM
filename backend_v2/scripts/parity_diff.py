"""Compare old walkthrough responses with their generated REST counterparts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    from scripts.http_parser import HttpBlock, parse_http
    from scripts.run_http import DEFAULT_ENV, HttpRunner
except ModuleNotFoundError:  # direct: python scripts/parity_diff.py
    from http_parser import HttpBlock, parse_http
    from run_http import DEFAULT_ENV, HttpRunner


ROOT = Path(__file__).resolve().parents[2]
OLD_HTTP = ROOT / "docs" / "http"
NEW_HTTP = ROOT / "backend_v2" / "http"
DEFAULT_IGNORES = Path(__file__).with_name("parity_ignore.json")
NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)+[a-z]?)\b")


@dataclass(frozen=True)
class IgnoreRule:
    path: str
    comment: str


def load_ignore_rules(path: Path) -> list[IgnoreRule]:
    document = json.loads(path.read_text(encoding="utf-8"))
    rules = document.get("rules")
    if not isinstance(rules, list):
        raise ValueError("parity ignore file must contain a rules list")
    parsed = []
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("path"), str) or not rule.get("comment"):
            raise ValueError("each parity ignore rule needs a path and comment")
        parsed.append(IgnoreRule(rule["path"], rule["comment"]))
    return parsed


def ignored(path: str, rules: list[IgnoreRule]) -> bool:
    for rule in rules:
        if rule.path == path:
            return True
        if rule.path.startswith("$..") and path.rsplit(".", 1)[-1] == rule.path[3:]:
            return True
    return False


def body_difference(left, right, rules: list[IgnoreRule], path: str = "$") -> str | None:
    if type(left) is not type(right):
        return f"{path}: type {type(left).__name__} != {type(right).__name__}"
    if ignored(path, rules):
        return None
    if isinstance(left, dict):
        for key in sorted(left.keys() | right.keys()):
            child = f"{path}.{key}"
            if key not in left:
                return f"{child}: missing from old response"
            if key not in right:
                return f"{child}: missing from new response"
            if difference := body_difference(left[key], right[key], rules, child):
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length {len(left)} != {len(right)}"
        for index, (old_value, new_value) in enumerate(zip(left, right)):
            if difference := body_difference(old_value, new_value, rules, f"{path}[{index}]"):
                return difference
        return None
    if left != right:
        old_value = json.dumps(left, ensure_ascii=False)[:80]
        new_value = json.dumps(right, ensure_ascii=False)[:80]
        return f"{path}: {old_value} != {new_value}"
    return None


def response_difference(old_response, new_response, rules: list[IgnoreRule]) -> str | None:
    if old_response.status_code != new_response.status_code:
        return f"$.status: {old_response.status_code} != {new_response.status_code}"
    try:
        old_body = old_response.json()
        new_body = new_response.json()
    except ValueError:
        if old_response.text != new_response.text:
            return "$: response text differs"
        return None
    return body_difference(old_body, new_body, rules)


def block_key(block: HttpBlock) -> str | None:
    match = NUMBER_RE.match(block.title or "")
    return match.group(1) if match else None


def marked(block: HttpBlock, marker: str) -> bool:
    return any(line.startswith(marker) for line in block.lines)


class ParityRunner:
    def __init__(
        self,
        old_base: str = "http://localhost:8000",
        new_base: str = "http://localhost:8001",
        timeout: float = 30,
        rules: list[IgnoreRule] | None = None,
        old_request=None,
        new_request=None,
        output: Callable[[str], None] = print,
        dotenv_path: Path = DEFAULT_ENV,
    ):
        options = {"timeout": timeout, "dotenv_path": dotenv_path, "output": lambda _line: None}
        if old_request is not None:
            options["request"] = old_request
        self.old = HttpRunner(old_base, **options)
        options = dict(options)
        if new_request is not None:
            options["request"] = new_request
        elif "request" in options:
            del options["request"]
        self.new = HttpRunner(new_base, **options)
        self.rules = rules if rules is not None else load_ignore_rules(DEFAULT_IGNORES)
        self.output = output

    @staticmethod
    def _advance_variables(blocks: list[HttpBlock], cursor: int, target: int, runner: HttpRunner) -> int:
        for block in blocks[cursor:target]:
            for name, value in block.variables():
                runner.variables[name] = value
        return target + 1

    def run_pair(self, old_path: Path, new_path: Path) -> bool:
        self.output(new_path.name)
        old_blocks = parse_http(old_path.read_text(encoding="utf-8")).blocks
        new_blocks = parse_http(new_path.read_text(encoding="utf-8")).blocks
        new_by_key = {block_key(block): index for index, block in enumerate(new_blocks) if block_key(block)}
        old_cursor = new_cursor = 0
        counts = {"same": 0, "differs": 0, "skipped": 0}
        for old_index, old_block in enumerate(old_blocks):
            if old_block.request is None or not (key := block_key(old_block)):
                continue
            new_index = new_by_key.get(key)
            if new_index is None:
                counts["differs"] += 1
                self.output(f"  [differs] {old_block.title} -- REST copy is missing")
                continue
            new_block = new_blocks[new_index]
            old_cursor = self._advance_variables(old_blocks, old_cursor, old_index, self.old)
            new_cursor = self._advance_variables(new_blocks, new_cursor, new_index, self.new)
            reason = None
            if marked(new_block, "# @waiting"):
                reason = "waiting for its unit"
            elif marked(new_block, "# @negative"):
                reason = "negative method case"
            elif marked(new_block, "# @not-served") or new_block.request is None:
                reason = "not served under PE-3"
            if reason:
                counts["skipped"] += 1
                self.output(f"  [skipped] {old_block.title} -- {reason}")
                continue
            old_result = self.old.run_block(old_block, check=False)
            new_result = self.new.run_block(new_block, check=False)
            if old_result and new_result and old_result.outcome == new_result.outcome == "skipped":
                counts["skipped"] += 1
                self.output(f"  [skipped] {old_block.title} -- cleanup reference unavailable")
                continue
            failure = next(
                (result.detail for result in (old_result, new_result) if result and result.outcome == "fail"),
                None,
            )
            if failure:
                counts["differs"] += 1
                self.output(self.old.redact(f"  [differs] {old_block.title} -- {failure}"))
                continue
            if old_result is None or new_result is None or old_result.response is None or new_result.response is None:
                difference = "$: response missing"
            else:
                difference = response_difference(old_result.response, new_result.response, self.rules)
            outcome = "differs" if difference else "same"
            counts[outcome] += 1
            detail = f" -- {difference}" if difference else ""
            self.output(self.old.redact(f"  [{outcome}] {old_block.title}{detail}"))
        self.output(
            f"  {counts['same']} same, {counts['differs']} differs, {counts['skipped']} skipped"
        )
        return counts["differs"] == 0


def selected_files(paths: list[Path], include_lockout: bool) -> list[Path]:
    selected = paths or sorted(NEW_HTTP.glob("*.http"))
    lockout = [path for path in selected if path.name == "99_lockout.http"]
    others = [path for path in selected if path.name != "99_lockout.http"]
    if lockout and others and not include_lockout:
        raise ValueError("99_lockout.http cannot run with other files without --include-lockout")
    return others + lockout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--old", default="http://localhost:8000", help="old server base URL")
    parser.add_argument("--new", default="http://localhost:8001", help="new server base URL")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--ignore", type=Path, default=DEFAULT_IGNORES)
    parser.add_argument("--include-lockout", action="store_true")
    args = parser.parse_args(argv)
    try:
        files = selected_files(args.files, args.include_lockout)
        runner = ParityRunner(args.old, args.new, args.timeout, load_ignore_rules(args.ignore))
        okay = True
        for new_path in files:
            okay = runner.run_pair(OLD_HTTP / new_path.name, new_path) and okay
        return 0 if okay else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"parity diff could not start: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
