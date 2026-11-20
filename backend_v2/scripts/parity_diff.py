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
CONTRACT_HEADERS = ("Allow", "WWW-Authenticate", "Retry-After")


DEFAULT_REGISTER = Path(__file__).resolve().parents[1] / "docs" / "PARITY_EXCEPTIONS.md"
PE_HEADING_RE = re.compile(r"^### (PE-\d+[a-z]?)\.", re.MULTILINE)


@dataclass(frozen=True)
class IgnoreRule:
    """A path whose value may differ. A rule for an approved parity exception names the
    `.http` file, the block number and the PE, and applies to that block only; a rule
    without them (a value each server issues independently, such as a token) applies
    everywhere."""

    path: str
    comment: str
    file: str | None = None
    block: str | None = None
    pe: str | None = None

    def applies_to(self, where: tuple[str, str | None] | None) -> bool:
        return self.file is None or where == (self.file, self.block)


def approved_exceptions(register: Path) -> set[str]:
    """The PE numbers whose entry's status starts with "approved"."""
    text = register.read_text(encoding="utf-8")
    headings = list(PE_HEADING_RE.finditer(text))
    approved = set()
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        status = re.search(r"^- \*\*Status:\*\*\s*(\S+)", text[heading.end():end], re.MULTILINE)
        if status and status.group(1).startswith("approved"):
            approved.add(heading.group(1))
    return approved


def load_ignore_rules(path: Path, register: Path = DEFAULT_REGISTER) -> list[IgnoreRule]:
    document = json.loads(path.read_text(encoding="utf-8"))
    rules = document.get("rules")
    if not isinstance(rules, list):
        raise ValueError("parity ignore file must contain a rules list")
    parsed = []
    approved = None
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("path"), str) or not rule.get("comment"):
            raise ValueError("each parity ignore rule needs a path and comment")
        scope = [rule.get(key) for key in ("file", "block", "pe")]
        if any(scope) and not all(isinstance(value, str) and value for value in scope):
            raise ValueError(
                f"parity ignore rule {rule['path']}: file, block and pe go together"
            )
        if rule.get("pe"):
            if approved is None:
                approved = approved_exceptions(register)
            if rule["pe"] not in approved:
                raise ValueError(
                    f"parity ignore rule {rule['path']}: {rule['pe']} is not an approved exception"
                )
        parsed.append(IgnoreRule(rule["path"], rule["comment"], *scope))
    return parsed


def ignored(
    path: str, rules: list[IgnoreRule], where: tuple[str, str | None] | None = None
) -> bool:
    for rule in rules:
        if not rule.applies_to(where):
            continue
        if rule.path == path:
            return True
        if rule.path.startswith("$..") and path.rsplit(".", 1)[-1] == rule.path[3:]:
            return True
    return False


#: A `Hash(10)` document name, as both backends generate it: ten lowercase hex characters,
#: at least one of them a letter (so a ten-digit phone number is never one). Generated
#: names legitimately differ between two servers (API_CONTRACT.md), also inside a message.
GENERATED_NAME_RE = re.compile(r"(?<![0-9a-z])(?=[0-9]*[a-f])[0-9a-f]{10}(?![0-9a-z])")
#: A whole value that is an ISO date or datetime. API_CONTRACT.md lists timestamps beside
#: generated names as legitimately differing; only their digits are blanked, so the
#: format (separator, precision, zone) is still compared. Any key qualifies: the shape of
#: the value decides, not its key's name.
ISO_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}(?::?\d{2})?)?)?"
)


def is_iso_timestamp(value: str) -> bool:
    return ISO_TIMESTAMP_RE.fullmatch(value) is not None


class _Comparison:
    """One response's comparison: every differing path, and the generated-name pairing,
    which must be one-to-one across the whole response (the same old name always pairs
    with the same new name, and two old names never share one)."""

    def __init__(self, rules: list[IgnoreRule], where: tuple[str, str | None] | None = None):
        self.rules = rules
        self.where = where
        self.differences: list[str] = []
        self.old_to_new: dict[str, str] = {}
        self.new_to_old: dict[str, str] = {}

    def add(self, text: str) -> None:
        self.differences.append(text)

    def _pair(self, old_token: str, new_token: str) -> bool:
        if self.old_to_new.setdefault(old_token, new_token) != new_token:
            return False
        return self.new_to_old.setdefault(new_token, old_token) == old_token

    def strings_match(self, left: str, right: str) -> bool:
        if left == right:
            return True
        if is_iso_timestamp(left) and is_iso_timestamp(right):
            return re.sub(r"\d", "0", left) == re.sub(r"\d", "0", right)
        old_tokens = GENERATED_NAME_RE.findall(left)
        new_tokens = GENERATED_NAME_RE.findall(right)
        if not old_tokens or len(old_tokens) != len(new_tokens):
            return False
        if GENERATED_NAME_RE.sub("<generated>", left) != GENERATED_NAME_RE.sub(
            "<generated>", right
        ):
            return False
        return all(self._pair(old, new) for old, new in zip(old_tokens, new_tokens))

    def compare(self, left, right, path: str = "$") -> None:
        if type(left) is not type(right):
            self.add(f"{path}: type {type(left).__name__} != {type(right).__name__}")
            return
        if ignored(path, self.rules, self.where):
            return
        if isinstance(left, dict):
            for child_key in sorted(left.keys() | right.keys()):
                child = f"{path}.{child_key}"
                if child_key not in left:
                    self.add(f"{child}: missing from old response")
                elif child_key not in right:
                    self.add(f"{child}: missing from new response")
                else:
                    self.compare(left[child_key], right[child_key], child)
            return
        if isinstance(left, list):
            self._compare_lists(left, right, path)
            return
        if isinstance(left, str) and self.strings_match(left, right):
            return
        if left != right:
            old_value = json.dumps(left, ensure_ascii=False)[:80]
            new_value = json.dumps(right, ensure_ascii=False)[:80]
            self.add(f"{path}: {old_value} != {new_value}")

    def _compare_lists(self, left: list, right: list, path: str) -> None:
        def names(rows):
            if rows and all(isinstance(row, dict) and "name" in row for row in rows):
                return [str(row["name"]) for row in rows]
            return None

        old_names, new_names = names(left), names(right)
        generated = (
            old_names is not None
            and new_names is not None
            and all(GENERATED_NAME_RE.fullmatch(name) for name in old_names + new_names)
        )
        if generated:
            # Rows named by generated hashes cannot match by name across two servers:
            # pair them by position, and the one-to-one name pairing checks the names.
            old_names = new_names = None
        if old_names is not None and new_names is not None and old_names != new_names:
            # Rows of documents: compare the rows both sides hold, matched by name, and
            # report the names only one side holds.
            if len(left) != len(right):
                self.add(f"{path}: length {len(left)} != {len(right)}")
            old_by_name = dict(zip(old_names, left))
            new_by_name = dict(zip(new_names, right))
            if missing := [name for name in old_names if name not in new_by_name]:
                self.add(f"{path}: names only in old {missing}")
            if extra := [name for name in new_names if name not in old_by_name]:
                self.add(f"{path}: names only in new {extra}")
            common = [name for name in old_names if name in new_by_name]
            if [n for n in new_names if n in old_by_name] != common:
                self.add(f"{path}: order of shared names differs")
            for name in common:
                self.compare(old_by_name[name], new_by_name[name], f"{path}[name={name}]")
            return
        if len(left) != len(right):
            self.add(f"{path}: length {len(left)} != {len(right)}")
        for index, (old_value, new_value) in enumerate(zip(left, right)):
            self.compare(old_value, new_value, f"{path}[{index}]")


def body_differences(
    left, right, rules: list[IgnoreRule], where: tuple[str, str | None] | None = None
) -> list[str]:
    comparison = _Comparison(rules, where)
    comparison.compare(left, right)
    return comparison.differences


def body_difference(
    left,
    right,
    rules: list[IgnoreRule],
    path: str = "$",
    where: tuple[str, str | None] | None = None,
) -> str | None:
    comparison = _Comparison(rules, where)
    comparison.compare(left, right, path)
    return "; ".join(comparison.differences) or None


def response_difference(
    old_response,
    new_response,
    rules: list[IgnoreRule],
    resource_envelope: bool = False,
    where: tuple[str, str | None] | None = None,
) -> str | None:
    """With `resource_envelope` (a block marked `# @resource-envelope`), the old
    `/api/resource/` answer — `{"data": ...}` and 201 on create — is compared with the
    REST copy's `{"message": ...}` and 200, the shape the route answers by design."""
    old_status = old_response.status_code
    if resource_envelope and old_status == 201:
        old_status = 200
    if old_status != new_response.status_code:
        return f"$.status: {old_response.status_code} != {new_response.status_code}"
    differences = []
    for header in CONTRACT_HEADERS:
        old_present = header in old_response.headers
        new_present = header in new_response.headers
        if header == "Allow":
            # The method sets differ by design (S7, PE-1); the contract promises only that
            # a 405 carries an Allow header (API_CONTRACT.md), so only that is compared.
            if old_response.status_code == 405 and old_present != new_present:
                differences.append(f"$.headers.Allow: present {old_present} != {new_present}")
            continue
        old_value = old_response.headers.get(header)
        new_value = new_response.headers.get(header)
        if old_present != new_present or old_value != new_value:
            differences.append(f"$.headers.{header}: {old_value!r} != {new_value!r}")
    # A header difference does not hide the body: one block can report both.
    try:
        old_body = old_response.json()
        new_body = new_response.json()
    except ValueError:
        if old_response.text != new_response.text:
            differences.append("$: response text differs")
    else:
        if (
            resource_envelope
            and isinstance(old_body, dict)
            and "data" in old_body
            and "message" not in old_body
        ):
            old_body = {"message": old_body["data"], **{
                key: value for key, value in old_body.items() if key != "data"
            }}
        differences.extend(body_differences(old_body, new_body, rules, where))
    return "; ".join(differences) or None


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
        # 99_lockout runs against each backend in turn (ACCOUNTS spec section 7, A-18):
        # alternating the two servers spreads the failed logins past the lockout window,
        # so neither would lock.
        sequential = new_path.name == "99_lockout.http"
        counts = {"same": 0, "differs": 0, "skipped": 0}
        plan = []
        for old_index, old_block in enumerate(old_blocks):
            if old_block.request is None or not (key := block_key(old_block)):
                continue
            new_index = new_by_key.get(key)
            if new_index is None:
                counts["differs"] += 1
                self.output(f"  [differs] {old_block.title} -- REST copy is missing")
                continue
            new_block = new_blocks[new_index]
            reason = None
            if marked(new_block, "# @waiting"):
                reason = "waiting for its unit"
            elif marked(new_block, "# @negative"):
                reason = "negative method case"
            elif marked(new_block, "# @retired"):
                reason = "retired under PE-11"
            elif marked(new_block, "# @not-served") or new_block.request is None:
                reason = "not served under PE-3"
            if reason:
                counts["skipped"] += 1
                self.output(f"  [skipped] {old_block.title} -- {reason}")
                continue
            plan.append((old_index, old_block, new_index, new_block))

        if sequential:
            old_results = self._run_in_turn(old_blocks, [(i, b) for i, b, _, _ in plan], self.old)
            new_results = self._run_in_turn(new_blocks, [(i, b) for _, _, i, b in plan], self.new)
        else:
            old_results, new_results = [], []
            old_cursor = new_cursor = 0
            for old_index, old_block, new_index, new_block in plan:
                old_cursor = self._advance_variables(old_blocks, old_cursor, old_index, self.old)
                new_cursor = self._advance_variables(new_blocks, new_cursor, new_index, self.new)
                old_results.append(self.old.run_block(old_block, check=False))
                new_results.append(self.new.run_block(new_block, check=False))

        for (_, old_block, _, new_block), old_result, new_result in zip(
            plan, old_results, new_results
        ):
            envelope = marked(new_block, "# @resource-envelope")
            # In 99_lockout both sides could agree and still not lock: each side's status
            # is also held to the block's expected one.
            expected = new_block.expected_statuses if sequential else set()
            self._compare(
                old_block, old_result, new_result, counts, envelope, expected,
                (new_path.name, block_key(new_block)),
            )
        self.output(
            f"  {counts['same']} same, {counts['differs']} differs, {counts['skipped']} skipped"
        )
        return counts["differs"] == 0

    def _run_in_turn(self, blocks: list[HttpBlock], indexed, runner: HttpRunner) -> list:
        cursor = 0
        results = []
        for index, block in indexed:
            cursor = self._advance_variables(blocks, cursor, index, runner)
            results.append(runner.run_block(block, check=False))
        return results

    def _compare(
        self,
        old_block: HttpBlock,
        old_result,
        new_result,
        counts: dict,
        envelope: bool = False,
        expected: set[int] | frozenset[int] = frozenset(),
        where: tuple[str, str | None] | None = None,
    ) -> None:
        if old_result and new_result and old_result.outcome == new_result.outcome == "skipped":
            counts["skipped"] += 1
            self.output(f"  [skipped] {old_block.title} -- cleanup reference unavailable")
            return
        failure = next(
            (result.detail for result in (old_result, new_result) if result and result.outcome == "fail"),
            None,
        )
        if failure:
            counts["differs"] += 1
            self.output(self.old.redact(f"  [differs] {old_block.title} -- {failure}"))
            return
        if old_result is None or new_result is None or old_result.response is None or new_result.response is None:
            difference = "$: response missing"
        else:
            unexpected = [
                f"$.status: {side} {result.response.status_code} not {'|'.join(map(str, sorted(expected)))}"
                for side, result in (("old", old_result), ("new", new_result))
                if expected and result.response.status_code not in expected
            ]
            difference = "; ".join(unexpected) or response_difference(
                old_result.response, new_result.response, self.rules, envelope, where
            )
        outcome = "differs" if difference else "same"
        counts[outcome] += 1
        detail = f" -- {difference}" if difference else ""
        self.output(self.old.redact(f"  [{outcome}] {old_block.title}{detail}"))


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
