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


def response(status, body, headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode()
    result.headers["Content-Type"] = "application/json"
    result.headers.update(headers or {})
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


def test_retry_after_difference_is_reported_when_bodies_match():
    difference = response_difference(
        response(429, '{"message":"same"}', {"Retry-After": "10"}),
        response(429, '{"message":"same"}', {"Retry-After": "20"}),
        [],
    )
    assert difference == "$.headers.Retry-After: '10' != '20'"


def test_contract_header_on_one_side_only_is_reported():
    difference = response_difference(
        response(401, '{"message":"same"}', {"WWW-Authenticate": "Bearer"}),
        response(401, '{"message":"same"}'),
        [],
    )
    assert difference == "$.headers.WWW-Authenticate: 'Bearer' != None"


def test_allow_header_method_order_is_ignored():
    assert response_difference(
        response(405, '{"message":"same"}', {"Allow": "GET, POST"}),
        response(405, '{"message":"same"}', {"Allow": "POST, GET"}),
        [],
    ) is None


def test_allow_methods_may_differ_by_design():
    """S7 gives each new route its own methods (A-25): only a 405's Allow is promised."""
    assert response_difference(
        response(200, '{"message":"same"}', {"Allow": "GET, HEAD, OPTIONS, POST, PUT"}),
        response(200, '{"message":"same"}', {"Allow": "OPTIONS, POST"}),
        [],
    ) is None
    assert response_difference(
        response(405, '{"message":"same"}', {"Allow": "GET, POST, PUT"}),
        response(405, '{"message":"same"}', {"Allow": "POST"}),
        [],
    ) is None


def test_a_405_without_allow_is_reported():
    difference = response_difference(
        response(405, '{"message":"same"}', {"Allow": "GET"}),
        response(405, '{"message":"same"}'),
        [],
    )
    assert difference == "$.headers.Allow: present True != False"


def test_a_header_difference_does_not_hide_the_body():
    difference = response_difference(
        response(401, '{"message":"old"}', {"WWW-Authenticate": "Bearer"}),
        response(401, '{"message":"new"}'),
        [],
    )
    assert difference.startswith("$.headers.WWW-Authenticate: 'Bearer' != None; ")
    assert "$.message" in difference


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


LOCKOUT_TEXT = """\
### 1.1 wrong password -> 401
POST {host}/login
### 1.2 wrong password -> 401
POST {host}/login
### 1.3 now locked -> 403
POST {host}/login
"""


@pytest.mark.parametrize(
    "name,expected",
    [
        ("99_lockout.http", ["old", "old", "old", "new", "new", "new"]),
        ("01_auth.http", ["old", "new", "old", "new", "old", "new"]),
    ],
)
def test_the_lockout_file_runs_each_backend_in_turn(temporary_path: Path, name, expected):
    """ACCOUNTS spec section 7 (A-18): interleaving the two servers spreads the failed
    logins past the lockout window, so 99_lockout runs all of one side, then the other."""
    old = temporary_path / "old" / name
    new = temporary_path / "new" / name
    for path, host in ((old, "http://old.test"), (new, "http://new.test")):
        path.parent.mkdir()
        path.write_text(LOCKOUT_TEXT.format(host=host), encoding="utf-8")
    order = []

    def transport(side):
        def request(method, url, **kwargs):
            order.append(side)
            return response(401, '{"message":"no"}')
        return request

    runner = ParityRunner(
        rules=[], old_request=transport("old"), new_request=transport("new"),
        output=lambda line: None,
    )
    assert runner.run_pair(old, new)
    assert order == expected


# --- A-25: the resource envelope and generated names ------------------------------------


def test_a_resource_envelope_block_compares_old_data_with_new_message():
    old = response(201, '{"data": {"name": "x", "title": "A"}}')
    new = response(200, '{"message": {"name": "x", "title": "A"}}')
    assert response_difference(old, new, [], resource_envelope=True) is None
    different = response(200, '{"message": {"name": "x", "title": "B"}}')
    assert "$.message.title" in response_difference(old, different, [], resource_envelope=True)


def test_without_the_marker_the_envelope_still_differs():
    old = response(201, '{"data": {"name": "x"}}')
    new = response(200, '{"message": {"name": "x"}}')
    assert response_difference(old, new, []) == "$.status: 201 != 200"


def test_generated_names_are_normalised_inside_messages():
    old = response(403, '{"message": "No permission for CRM Sales Hierarchy fef8ae3c71"}')
    new = response(403, '{"message": "No permission for CRM Sales Hierarchy bc9dfbeae8"}')
    assert response_difference(old, new, []) is None


def test_other_differences_survive_the_normalisation():
    old = response(403, '{"message": "No permission for CRM Sales Hierarchy fef8ae3c71"}')
    new = response(403, '{"message": "No permission to read CRM Sales Hierarchy bc9dfbeae8"}')
    assert response_difference(old, new, []).startswith("$.message:")


def test_timestamps_are_normalised_but_not_other_values():
    """API_CONTRACT lists timestamps beside generated names (A-25)."""
    old = response(200, '{"message": {"creation": "2026-11-17T23:22:26.313641Z", "role": "Sales User"}}')
    new = response(200, '{"message": {"creation": "2026-11-17T23:22:30.702068Z", "role": "Sales User"}}')
    assert response_difference(old, new, []) is None
    changed = response(200, '{"message": {"creation": "2026-11-17T23:22:30.702068Z", "role": "Sales Manager"}}')
    assert response_difference(old, changed, []).startswith("$.message.role:")


# --- A-26: every path, rows by name, narrower normalisations -----------------------------


def test_every_differing_path_is_reported():
    difference = body_difference(
        {"message": {"a": 1, "b": 2, "c": 3}}, {"message": {"a": 9, "b": 2, "c": 8}}, []
    )
    assert "$.message.a" in difference and "$.message.c" in difference


def test_rows_with_names_are_compared_by_name():
    old = [{"name": "ada", "role": "Sales User"}, {"name": "zed", "role": "x"}]
    new = [{"name": "ada", "role": "Sales Manager"}]
    difference = body_difference(old, new, [])
    assert "length 2 != 1" in difference
    assert "names only in old ['zed']" in difference
    assert "$[name=ada].role" in difference


def test_a_timestamp_format_change_is_reported():
    assert body_difference(
        {"creation": "2026-11-18 10:00:00"}, {"creation": "2026-11-18T10:00:00.123456Z"}, []
    )
    assert body_difference(
        {"creation": "2026-11-18T10:00:00.123456Z"}, {"creation": "2026-11-19T11:01:02.654321Z"}, []
    ) is None


def test_a_timestamp_in_another_key_is_compared_exactly():
    assert body_difference(
        {"due_date": "2026-11-18T10:00:00Z"}, {"due_date": "2026-11-19T10:00:00Z"}, []
    )
    assert body_difference({"note": "2026-11-18T10:00:00Z"}, {"note": "2026-11-19T10:00:00Z"}, [])


def test_two_different_ten_digit_numbers_differ():
    assert body_difference({"phone": "9876543210"}, {"phone": "9876543211"}, [])


def test_a_reused_generated_name_must_be_reused_on_the_other_side():
    same = body_difference(
        {"a": "abc123def0", "b": "abc123def0"}, {"a": "fed321cba9", "b": "fed321cba9"}, []
    )
    assert same is None
    broken = body_difference(
        {"a": "abc123def0", "b": "abc123def0"}, {"a": "fed321cba9", "b": "0123456abc"}, []
    )
    assert broken
    shared = body_difference(
        {"a": "abc123def0", "b": "111111111a"}, {"a": "fed321cba9", "b": "fed321cba9"}, []
    )
    assert shared


def test_rows_named_by_generated_hashes_are_compared_by_position():
    old = [{"name": "aa11bb22cc", "role": "Sales User"}]
    new = [{"name": "dd33ee44ff", "role": "Sales Manager"}]
    difference = body_difference(old, new, [])
    assert difference == '$[0].role: "Sales User" != "Sales Manager"'
    assert body_difference(old, [{"name": "dd33ee44ff", "role": "Sales User"}], []) is None
