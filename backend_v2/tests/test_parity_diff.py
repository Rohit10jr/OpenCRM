from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import requests

from scripts.parity_diff import (
    IgnoreRule,
    ParityRunner,
    body_difference,
    response_difference,
    selected_files,
)


def response(status, body):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode()
    result.headers["Content-Type"] = "application/json"
    return result


@pytest.fixture
def temporary_path():
    with TemporaryDirectory(dir=Path(__file__).parents[1] / "scripts") as directory:
        yield Path(directory)


def write_pair(temporary_path: Path, old_text: str, new_text: str):
    old = temporary_path / "old.http"
    new = temporary_path / "new.http"
    old.write_text(old_text, encoding="utf-8")
    new.write_text(new_text, encoding="utf-8")
    return old, new


def test_captured_variables_are_kept_on_their_own_side(temporary_path: Path):
    old, new = write_pair(temporary_path, """\
### 1.1 login -> 200
# @name login
POST http://old.test/login
###
@token = {{login.response.body.$.message.access}}
### 1.2 me -> 200
GET http://old.test/me
Authorization: Bearer {{token}}
""", """\
### 1.1 login -> 200
# @name login
POST http://new.test/login
###
@token = {{login.response.body.$.message.access}}
### 1.2 me -> 200
GET http://new.test/me
Authorization: Bearer {{token}}
""")
    seen = {"old": [], "new": []}

    def transport(side, token):
        def request(method, url, **kwargs):
            seen[side].append(kwargs.get("headers", {}))
            if url.endswith("/login"):
                return response(200, f'{{"message":{{"access":"{token}"}}}}')
            return response(200, '{"message":"same"}')
        return request

    runner = ParityRunner(
        rules=[IgnoreRule("$.message.access", "issued independently")],
        old_request=transport("old", "old-token"), new_request=transport("new", "new-token"),
        output=lambda line: None,
    )
    assert runner.run_pair(old, new)
    assert seen["old"][1]["Authorization"] == "Bearer old-token"
    assert seen["new"][1]["Authorization"] == "Bearer new-token"


def test_ignored_value_may_differ_but_must_exist_with_the_same_type():
    rules = [IgnoreRule("$.message.access", "issued independently")]
    assert body_difference({"message": {"access": "old"}}, {"message": {"access": "new"}}, rules) is None
    assert "missing from new" in body_difference({"message": {"access": "old"}}, {"message": {}}, rules)
    assert "type str != dict" in body_difference({"message": {"access": "old"}}, {"message": {"access": {}}}, rules)


def test_status_difference_is_reported_before_the_body():
    difference = response_difference(response(200, '{"message":"same"}'), response(201, '{"message":"same"}'), [])
    assert difference == "$.status: 200 != 201"


def test_real_body_difference_reports_short_json_path(temporary_path: Path):
    old, new = write_pair(temporary_path, "### 1.1 request -> 200\nGET http://old.test/value\n", "### 1.1 request -> 200\nGET http://new.test/value\n")
    output = []
    runner = ParityRunner(
        rules=[], old_request=lambda *args, **kwargs: response(200, '{"message":{"state":"old"}}'),
        new_request=lambda *args, **kwargs: response(200, '{"message":{"state":"new"}}'), output=output.append,
    )
    assert not runner.run_pair(old, new)
    assert "$.message.state" in "\n".join(output)


def test_waiting_negative_and_pe3_blocks_are_skipped(temporary_path: Path):
    old, new = write_pair(temporary_path, """\
### 1.1 waiting -> 200
GET http://old.test/one
### 1.2 negative -> 200
GET http://old.test/two
### 1.3 no route -> 200
GET http://old.test/three
""", """\
### 1.1 waiting -> 200
# @waiting SALES
GET http://new.test/one
### 1.2 negative -> 405
# @negative
GET http://new.test/two
### 1.3 no route -> 200
# @not-served PE-3: no REST route
# GET http://old.test/three
""")
    calls = []
    runner = ParityRunner(rules=[], old_request=lambda *args, **kwargs: calls.append(args),
                          new_request=lambda *args, **kwargs: calls.append(args), output=lambda line: None)
    assert runner.run_pair(old, new)
    assert not calls


def test_unreachable_side_is_reported_as_a_difference(temporary_path: Path):
    old, new = write_pair(temporary_path, "### 1.1 request -> 200\nGET http://old.test/value\n", "### 1.1 request -> 200\nGET http://new.test/value\n")
    output = []

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("refused")

    runner = ParityRunner(rules=[], old_request=unavailable,
                          new_request=lambda *args, **kwargs: response(200, "{}"), output=output.append)
    assert not runner.run_pair(old, new)
    assert "not reachable" in "\n".join(output)
    assert "Traceback" not in "\n".join(output)


def test_lockout_must_be_explicit_when_combined_and_is_sorted_last():
    normal, lockout = Path("01_auth.http"), Path("99_lockout.http")
    with pytest.raises(ValueError, match="--include-lockout"):
        selected_files([lockout, normal], include_lockout=False)
    assert selected_files([lockout, normal], include_lockout=True) == [normal, lockout]
