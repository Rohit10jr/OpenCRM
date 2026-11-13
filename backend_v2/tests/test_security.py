import time

import pytest
from django.test import RequestFactory, override_settings
from django.urls import re_path
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from core.exceptions import SecurityException
from core.security import (
    LoginAttemptTracker,
    check_login_allowed,
    rate_limit,
    record_login_failure,
    resolve_ip,
)
from core.views import FrappeAPIView

pytestmark = pytest.mark.django_db
LOGIN = "/api/v1/auth/login/"


class RateLimitedView(FrappeAPIView):
    permission_classes = (AllowAny,)

    @rate_limit(limit=2, seconds=60)
    def get(self, request):
        return Response("ok")


class KeyedRateLimitedView(FrappeAPIView):
    permission_classes = (AllowAny,)

    @rate_limit(
        limit=1,
        seconds=60,
        key="email",
        normalise=lambda value: str(value or "").strip().lower(),
    )
    def post(self, request):
        return Response("ok")


callable_key_inputs = []


def capture_key_inputs(inputs):
    callable_key_inputs.append(inputs)
    return inputs.get("email", "")


class CallableKeyRateLimitedView(FrappeAPIView):
    permission_classes = (AllowAny,)

    @rate_limit(limit=1, seconds=60, key=capture_key_inputs)
    def post(self, request):
        return Response("ok")


urlpatterns = [
    re_path(r"^limited/?$", RateLimitedView.as_view()),
    re_path(r"^keyed-limited/?$", KeyedRateLimitedView.as_view()),
    re_path(r"^callable-key-limited/?$", CallableKeyRateLimitedView.as_view()),
]


def test_a_fresh_key_is_allowed():
    assert LoginAttemptTracker("nobody@example.com").is_user_allowed() is True


def test_lockout_needs_more_than_the_threshold():
    tracker = LoginAttemptTracker("victim@example.com", max_consecutive_login_attempts=3)
    for _ in range(3):
        tracker.add_failure_attempt()
    assert tracker.is_user_allowed() is True
    tracker.add_failure_attempt()
    assert tracker.is_user_allowed() is False


def test_success_clears_the_count():
    tracker = LoginAttemptTracker("victim@example.com", max_consecutive_login_attempts=2)
    for _ in range(3):
        tracker.add_failure_attempt()
    assert tracker.is_user_allowed() is False
    tracker.add_success_attempt()
    assert tracker.is_user_allowed() is True


def test_failures_outside_the_window_do_not_accumulate():
    tracker = LoginAttemptTracker("victim@example.com", max_consecutive_login_attempts=2, lock_interval=1)
    tracker.add_failure_attempt()
    tracker.add_failure_attempt()
    time.sleep(1.1)
    tracker.add_failure_attempt()
    assert tracker.is_user_allowed() is True


def test_check_login_allowed_raises_for_a_locked_key(settings):
    settings.LOGIN_MAX_CONSECUTIVE_ATTEMPTS = 1
    record_login_failure("locked@example.com")
    record_login_failure("locked@example.com")
    with pytest.raises(SecurityException, match="locked"):
        check_login_allowed("locked@example.com")


def test_keys_are_independent():
    record_login_failure("a@example.com")
    assert LoginAttemptTracker("b@example.com").is_user_allowed() is True




@override_settings(ROOT_URLCONF=__name__)
def test_rate_limit_allows_up_to_the_limit(api):
    assert [api.get("/limited/", REMOTE_ADDR="10.0.0.1").status_code for _ in range(2)] == [200, 200]


@override_settings(ROOT_URLCONF=__name__)
def test_rate_limit_raises_past_the_limit(api):
    api.get("/limited/", REMOTE_ADDR="10.0.0.2")
    api.get("/limited/", REMOTE_ADDR="10.0.0.2")
    response = api.get("/limited/", REMOTE_ADDR="10.0.0.2")
    assert response.status_code == 429
    assert response.json()["message"] == "You hit the rate limit because of too many requests. Please try after sometime."


@override_settings(ROOT_URLCONF=__name__)
def test_rate_limit_buckets_are_per_ip(api):
    for address in ("10.0.0.3", "10.0.0.4"):
        assert api.get("/limited/", REMOTE_ADDR=address).status_code == 200


@override_settings(ROOT_URLCONF=__name__)
def test_keyed_rate_limit_uses_normalised_request_inputs(api):
    assert api.post(
        "/keyed-limited/", {"email": "first@example.com"}, format="json", REMOTE_ADDR="10.0.0.5"
    ).status_code == 200
    assert api.post(
        "/keyed-limited/", {"email": "second@example.com"}, format="json", REMOTE_ADDR="10.0.0.5"
    ).status_code == 200
    assert api.post(
        "/keyed-limited/", {"email": " FIRST@EXAMPLE.COM "}, format="json", REMOTE_ADDR="10.0.0.5"
    ).status_code == 429


@override_settings(ROOT_URLCONF=__name__)
def test_rate_limit_callable_key_receives_merged_inputs(api):
    callable_key_inputs.clear()
    response = api.post(
        "/callable-key-limited/?email=query@example.com&source=query&cmd=ignored",
        {"email": "body@example.com"},
        format="json",
        REMOTE_ADDR="10.0.0.6",
    )
    assert response.status_code == 200
    assert callable_key_inputs == [{"email": "body@example.com", "source": "query"}]


def test_rate_limit_is_inert_outside_a_request():
    @rate_limit(limit=1, seconds=60)
    def endpoint():
        return "ok"

    assert [endpoint() for _ in range(5)] == ["ok"] * 5


def test_rate_limit_callable_key_and_normalise_are_resilient(rf):
    calls = []

    @rate_limit(limit=1, seconds=60, key=lambda values: values["account"], normalise=lambda value: value.strip().lower())
    def endpoint(request):
        calls.append(request.query_params["account"])

    endpoint(Request(rf.get("/?account=+Alice@Example.com+", REMOTE_ADDR="10.0.0.9")))
    from core.exceptions import RateLimitExceededError

    with pytest.raises(RateLimitExceededError):
        endpoint(Request(rf.get("/?account=alice@example.com", REMOTE_ADDR="10.0.0.9")))
    assert calls == [" Alice@Example.com "]


def test_a_failing_rate_limit_key_callable_falls_back_to_ip(rf):
    @rate_limit(limit=1, seconds=60, key=lambda values: 1 / 0)
    def endpoint(request):
        return "ok"

    request = Request(rf.get("/", REMOTE_ADDR="10.0.0.10"))
    assert endpoint(request) == "ok"
    from core.exceptions import RateLimitExceededError

    with pytest.raises(RateLimitExceededError):
        endpoint(request)


def test_remote_addr_is_used_by_default():
    request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.7")
    assert resolve_ip(request) == "203.0.113.7"


def test_forwarded_header_is_ignored_when_no_proxy_is_configured(settings):
    settings.TRUSTED_PROXY_COUNT = 0
    request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.7", HTTP_X_FORWARDED_FOR="1.2.3.4")
    assert resolve_ip(request) == "203.0.113.7"


def test_forwarded_header_is_honoured_behind_one_proxy(settings):
    settings.TRUSTED_PROXY_COUNT = 1
    request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.9")
    assert resolve_ip(request) == "203.0.113.9"
