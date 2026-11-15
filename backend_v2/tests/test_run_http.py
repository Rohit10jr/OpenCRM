from pathlib import Path
from tempfile import TemporaryDirectory

import requests

from scripts.http_parser import parse_http
from scripts.run_http import HttpRunner


def response(status, body):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode()
    result.headers["Content-Type"] = "application/json"
    return result


def test_status_expectations_and_body_expectations_are_checked():
    blocks = parse_http("""\
### accepted -> 200|404
# @expect $.message.items count 2
# @expect $.message.label contains right
GET http://example.test/items
### wrong -> 201
GET http://example.test/wrong
""").blocks
    replies = iter((response(200, '{"message":{"items":[1,2],"label":"all right"}}'), response(200, "{}")))
    runner = HttpRunner(request=lambda *args, **kwargs: next(replies), output=lambda line: None)

    assert runner.run_block(blocks[1]).outcome == "pass"
    failed = runner.run_block(blocks[2])
    assert failed.outcome == "fail"
    assert "expected 201, got 200" in failed.detail


def test_captured_response_resolves_in_later_request():
    blocks = parse_http("""\
### login -> 200
# @name login
POST http://example.test/login
### use token -> 200
GET http://example.test/me
Authorization: Bearer {{login.response.body.$.message.access}}
""").blocks
    seen = []

    def request(method, url, **kwargs):
        seen.append(kwargs.get("headers", {}))
        return response(200, '{"message":{"access":"side-token"}}')

    runner = HttpRunner(request=request, output=lambda line: None)
    assert runner.run_block(blocks[1]).outcome == "pass"
    assert runner.run_block(blocks[2]).outcome == "pass"
    assert seen[1]["Authorization"] == "Bearer side-token"


def test_waiting_is_skipped_but_negative_405_is_run():
    blocks = parse_http("""\
### later -> 200
# @waiting SALES
GET http://example.test/later
### refused -> 405
# @negative
# @expect $.exc_type == MethodNotAllowed
POST http://example.test/read-only
""").blocks
    calls = []

    def request(*args, **kwargs):
        calls.append(args)
        return response(405, '{"exc_type":"MethodNotAllowed"}')

    runner = HttpRunner(request=request, output=lambda line: None)
    assert runner.run_block(blocks[1]).outcome == "skipped"
    assert runner.run_block(blocks[2]).outcome == "pass"
    assert len(calls) == 1


def test_unreachable_server_is_a_failure_without_a_traceback():
    block = parse_http("### request -> 200\nGET http://example.test/path\n").blocks[1]

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    result = HttpRunner(base_url="http://localhost:8001", request=unavailable).run_block(block)
    assert result.outcome == "fail"
    assert "server " in result.detail and " is not reachable" in result.detail
    assert "Traceback" not in result.detail


def test_dotenv_values_are_redacted_from_all_file_output():
    with TemporaryDirectory(dir=Path(__file__).parents[1] / "scripts") as directory:
        temporary = Path(directory)
        secret = "do-not-print-this-password"
        env = temporary / ".env"
        env.write_text(f"ADMIN_PWD={secret}\n", encoding="utf-8")
        http = temporary / "secret.http"
        http.write_text(
            "### login -> 200\nPOST http://example.test/login\n\n"
            '{"pwd":"{{$dotenv ADMIN_PWD}}"}\n', encoding="utf-8",
        )
        lines = []

        def echo(*args, **kwargs):
            return response(500, f'{{"echo":"{secret}"}}')

        okay = HttpRunner(request=echo, dotenv_path=env, output=lines.append).run_file(http)
        assert not okay
        assert secret not in "\n".join(lines)
        assert "<redacted>" in "\n".join(lines)


def test_statusless_block_accepts_any_2xx():
    block = parse_http("### request\nPOST http://example.test/path\n").blocks[1]
    runner = HttpRunner(request=lambda *args, **kwargs: response(204, ""))
    assert runner.run_block(block).outcome == "pass"
