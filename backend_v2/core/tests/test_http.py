"""`core.http`, the outbound HTTP helper (specs/CONFIGURATION.md 4.3, decision 5).

New: `backend/` tests the helper only through its Exotel callers
(`backend/tests/test_exotel.py:375-392`). These patch the session, so nothing leaves the
machine.
"""

from unittest import mock

import pytest

from core import http


class _Session:
    def __init__(self):
        self.calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return "response"

    def close(self):
        self.closed = True


def test_request_sends_the_timeout_and_closes_the_session():
    session = _Session()
    with mock.patch.object(http, "build_session", return_value=session) as build:
        assert http.request("GET", "https://example.test/x", params={"a": 1}) == "response"
    build.assert_called_once_with(http.DEFAULT_ATTEMPTS)
    method, url, kwargs = session.calls[0]
    assert (method, url) == ("GET", "https://example.test/x")
    assert kwargs["timeout"] == http.DEFAULT_TIMEOUT == (5, 20)
    assert kwargs["params"] == {"a": 1}
    assert session.closed


def test_a_caller_chooses_its_own_timeout_and_attempts():
    session = _Session()
    with mock.patch.object(http, "build_session", return_value=session) as build:
        http.request("GET", "https://example.test/x", timeout=5, attempts=1)
    build.assert_called_once_with(1)
    assert session.calls[0][2]["timeout"] == 5


def test_a_transport_failure_is_raised_and_the_session_still_closes():
    import requests

    session = _Session()
    session.request = mock.Mock(side_effect=requests.ConnectionError("down"))
    with mock.patch.object(http, "build_session", return_value=session):
        with pytest.raises(requests.ConnectionError):
            http.request("GET", "https://example.test/x")
    assert session.closed


def test_the_retry_policy():
    session = http.build_session(3)
    retry = session.get_adapter("https://example.test").max_retries
    assert (retry.total, retry.connect, retry.read, retry.status) == (2, 2, 2, 2)
    assert set(retry.status_forcelist) == {429, 502, 503, 504}
    assert "POST" in retry.allowed_methods
    assert retry.respect_retry_after_header is True
    assert session.get_adapter("http://example.test").max_retries is retry


def test_one_attempt_means_no_retry():
    retry = http.build_session(1).get_adapter("https://example.test").max_retries
    assert retry.total == 0


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://key:token@api.example.test/v1?x=1", "https://api.example.test/v1?x=1"),
        ("https://api.example.test/v1", "https://api.example.test/v1"),
        ("not a url", "not a url"),
    ],
)
def test_redact_strips_userinfo(url, expected):
    assert http.redact(url) == expected
