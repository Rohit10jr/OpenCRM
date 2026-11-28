from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import requests

from scripts.parity_diff import (
    IgnoreRule,
    ParityRunner,
    body_difference,
    load_ignore_rules,
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
            # each side locks on its third attempt, as block 1.3 expects
            if order.count(side) == 3:
                return response(403, '{"message":"locked"}')
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


def test_a_date_under_another_key_is_compared_exactly():
    """A-56: a timestamp key AND an ISO value on both sides; a date the caller sets, or one
    shifted by a time-zone bug, is a real difference."""
    assert body_difference(
        {"due_date": "2026-11-18T10:00:00Z"}, {"due_date": "2026-11-19T10:00:00Z"}, []
    )
    assert body_difference({"closed_date": "2026-11-18"}, {"closed_date": "2026-11-19"}, [])
    assert body_difference({"based_on": "Lead 1"}, {"based_on": "Lead 2"}, [])


def test_a_timestamp_key_with_iso_values_is_normalised():
    assert body_difference(
        {"modified": "2026-11-18 10:00:00.123456"}, {"modified": "2026-11-19 11:01:02.654321"}, []
    ) is None
    assert body_difference({"sent_on": "2026-11-18"}, {"sent_on": "2026-11-19"}, []) is None
    assert body_difference(
        {"email_sent_at": "2026-11-18T10:00:00+05:30"},
        {"email_sent_at": "2026-11-19T11:01:02+05:30"},
        [],
    ) is None


def test_a_value_that_is_not_iso_is_compared_exactly_even_in_a_timestamp_key():
    assert body_difference({"creation": "yesterday"}, {"creation": "today"}, [])
    assert body_difference({"sent_at": "18/11/2026"}, {"sent_at": "19/11/2026"}, [])
    assert body_difference(
        {"note": "due 2026-11-18"}, {"note": "due 2026-11-19"}, []
    ), "a date inside text is not a whole ISO value"
    assert body_difference({"modified": "2026-11-18"}, {"modified": "not a date"}, [])
    assert body_difference({"creation": "20261118"}, {"creation": "20261119"}, [])


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


# --- A-48 group 5: the lockout's expected status, and scoped ignore rules ---------------


def test_the_lockout_file_holds_each_side_to_the_expected_status(temporary_path: Path):
    """Item 5: in 99_lockout both sides answering 401 where the block expects the lock
    (403) is a difference, though the two answers agree."""
    lines = []
    old = temporary_path / "old" / "99_lockout.http"
    new = temporary_path / "new" / "99_lockout.http"
    for path, host in ((old, "http://old.test"), (new, "http://new.test")):
        path.parent.mkdir()
        path.write_text(LOCKOUT_TEXT.format(host=host), encoding="utf-8")

    def transport(method, url, **kwargs):
        return response(401, '{"message":"no"}')

    runner = ParityRunner(
        rules=[], old_request=transport, new_request=transport, output=lines.append
    )
    assert not runner.run_pair(old, new)
    assert any("1.3" in line and "$.status: old 401 not 403" in line for line in lines)
    assert all("[same]" in line for line in lines if "1.1" in line or "1.2" in line)


def test_another_file_is_not_held_to_the_expected_status(temporary_path: Path):
    old, new = write_pair(temporary_path, LOCKOUT_TEXT.format(host="http://old.test"),
                          LOCKOUT_TEXT.format(host="http://new.test"))

    def transport(method, url, **kwargs):
        return response(401, '{"message":"no"}')

    runner = ParityRunner(rules=[], old_request=transport, new_request=transport,
                          output=lambda line: None)
    assert runner.run_pair(old, new)


REGISTER = """\
### PE-7. Something approved

- **Status:** approved by the owner (20 Nov 2026); built
- **Where:** here

### PE-23. Something proposed

- **Status:** proposed — decided by the supervisor
"""


def write_rules(temporary_path: Path, rules) -> tuple[Path, Path]:
    import json

    rules_path = temporary_path / "ignore.json"
    rules_path.write_text(json.dumps({"rules": rules}), encoding="utf-8")
    register = temporary_path / "PARITY_EXCEPTIONS.md"
    register.write_text(REGISTER, encoding="utf-8")
    return rules_path, register


def test_a_scoped_rule_applies_to_its_file_and_block_only(temporary_path: Path):
    rules_path, register = write_rules(temporary_path, [{
        "path": "$.message.name", "comment": "PE-7", "file": "09_users.http",
        "block": "2.3", "pe": "PE-7",
    }])
    rules = load_ignore_rules(rules_path, register)
    old, new = {"message": {"name": "a"}}, {"message": {"name": "b"}}
    assert body_difference(old, new, rules, where=("09_users.http", "2.3")) is None
    assert body_difference(old, new, rules, where=("09_users.http", "2.4"))
    assert body_difference(old, new, rules, where=("01_auth.http", "2.3"))
    assert body_difference(old, new, rules)


def test_an_unscoped_rule_still_applies_everywhere(temporary_path: Path):
    rules_path, register = write_rules(
        temporary_path, [{"path": "$.message.access", "comment": "issued independently"}]
    )
    rules = load_ignore_rules(rules_path, register)
    old, new = {"message": {"access": "a"}}, {"message": {"access": "b"}}
    assert body_difference(old, new, rules, where=("01_auth.http", "1.1")) is None
    assert body_difference(old, new, rules) is None


@pytest.mark.parametrize("scope", [
    {"file": "09_users.http"},
    {"file": "09_users.http", "block": "2.3"},
    {"pe": "PE-7"},
    {"file": "09_users.http", "block": "", "pe": "PE-7"},
])
def test_a_partial_scope_is_refused(temporary_path: Path, scope):
    rules_path, register = write_rules(
        temporary_path, [{"path": "$.x", "comment": "c", **scope}]
    )
    with pytest.raises(ValueError, match="file, block and pe go together"):
        load_ignore_rules(rules_path, register)


@pytest.mark.parametrize("pe", ["PE-23", "PE-99"])
def test_a_rule_needs_an_approved_exception(temporary_path: Path, pe):
    rules_path, register = write_rules(temporary_path, [{
        "path": "$.x", "comment": "c", "file": "a.http", "block": "1.1", "pe": pe,
    }])
    with pytest.raises(ValueError, match=f"{pe} is not an approved exception"):
        load_ignore_rules(rules_path, register)


def test_the_shipped_rules_load_against_the_real_register():
    from scripts.parity_diff import DEFAULT_IGNORES

    assert load_ignore_rules(DEFAULT_IGNORES)


def test_a_scoped_rule_reaches_the_block_through_the_runner(temporary_path: Path):
    old_text = "### 2.3 read -> 200\nGET http://old.test/u\n"
    new_text = "### 2.3 read -> 200\nGET http://new.test/u\n"
    (temporary_path / "old").mkdir()
    (temporary_path / "new").mkdir()
    old = temporary_path / "old" / "09_users.http"
    new = temporary_path / "new" / "09_users.http"
    old.write_text(old_text, encoding="utf-8")
    new.write_text(new_text, encoding="utf-8")

    def transport(body):
        return lambda method, url, **kwargs: response(200, body)

    rule = IgnoreRule("$.message.name", "PE-7", "09_users.http", "2.3", "PE-7")
    runner = ParityRunner(
        rules=[rule], old_request=transport('{"message":{"name":"a"}}'),
        new_request=transport('{"message":{"name":"b"}}'), output=lambda line: None,
    )
    assert runner.run_pair(old, new)


# --- A-56: a whole answer expected to differ under an approved exception ----------------


def run_one_block(temporary_path: Path, rules, old_answer, new_answer):
    for side in ("old", "new"):
        (temporary_path / side).mkdir()
        (temporary_path / side / "09_users.http").write_text(
            f"### 2.3 read -> 200\nGET http://{side}.test/u\n", encoding="utf-8"
        )
    lines = []

    def transport(answer):
        return lambda method, url, **kwargs: response(*answer)

    runner = ParityRunner(
        rules=rules, old_request=transport(old_answer), new_request=transport(new_answer),
        output=lines.append, dotenv_path=temporary_path / "no.env",
    )
    okay = runner.run_pair(temporary_path / "old" / "09_users.http",
                           temporary_path / "new" / "09_users.http")
    return okay, lines


WHOLE = IgnoreRule("$", "a new rule", "09_users.http", "2.3", "PE-7")


def test_a_whole_answer_rule_reports_its_own_outcome(temporary_path: Path):
    okay, lines = run_one_block(
        temporary_path, [WHOLE], (200, '{"message":"x"}'), (403, '{"message":"no"}')
    )
    assert okay
    assert any(line.startswith("  [expected (PE-7)] 2.3") and "$.status: 200 != 403" in line
               for line in lines)
    assert lines[-1] == "  0 same, 1 expected, 0 differs, 0 skipped"


def test_a_whole_answer_rule_whose_answers_are_equal_is_an_error(temporary_path: Path):
    okay, lines = run_one_block(
        temporary_path, [WHOLE], (200, '{"message":"x"}'), (200, '{"message":"x"}')
    )
    assert not okay
    assert any("[differs] 2.3" in line and "expected to differ under PE-7" in line
               and "remove the rule" in line for line in lines)


def test_a_whole_answer_rule_is_for_its_block_only(temporary_path: Path):
    other = IgnoreRule("$", "c", "09_users.http", "2.4", "PE-7")
    okay, lines = run_one_block(
        temporary_path, [other], (200, '{"message":"x"}'), (403, '{"message":"no"}')
    )
    assert not okay
    assert any("[differs] 2.3" in line for line in lines)


def test_a_whole_answer_rule_does_not_ignore_body_paths():
    old, new = {"message": "a"}, {"message": "b"}
    assert body_difference(old, new, [WHOLE], where=("09_users.http", "2.3"))


def test_a_whole_answer_rule_needs_its_scope(temporary_path: Path):
    rules_path, register = write_rules(temporary_path, [{"path": "$", "comment": "c"}])
    with pytest.raises(ValueError, match="whole answer needs a file, block and pe"):
        load_ignore_rules(rules_path, register)
