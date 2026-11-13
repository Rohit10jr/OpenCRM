"""Shared client identity, login lockout, and endpoint rate limiting."""

from collections.abc import Callable
from functools import wraps
import time

from django.conf import settings
from django.core.cache import cache

from core.exceptions import RateLimitExceededError, SecurityException
from core.inputs import build_payload


def resolve_ip(request) -> str | None:
    """Resolve the client without trusting forwarded headers beyond known proxies."""
    hops = int(getattr(settings, "TRUSTED_PROXY_COUNT", 0) or 0)
    if hops:
        chain = [
            part.strip()
            for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
            if part.strip()
        ]
        if chain:
            index = max(0, len(chain) - hops)
            return chain[index] if index < len(chain) else chain[0]
    return request.META.get("REMOTE_ADDR")

class LoginAttemptTracker:
    def __init__(
        self,
        key: str,
        max_consecutive_login_attempts: int | None = None,
        lock_interval: int | None = None,
    ):
        self.key = key
        self.max_failed_logins = (
            max_consecutive_login_attempts
            if max_consecutive_login_attempts is not None
            else getattr(settings, "LOGIN_MAX_CONSECUTIVE_ATTEMPTS", 10)
        )
        self.lock_interval = (
            lock_interval
            if lock_interval is not None
            else getattr(settings, "LOGIN_LOCK_INTERVAL_SECONDS", 60)
        )

    @property
    def _cache_key(self) -> str:
        return f"login_attempts:{self.key}"

    def _read(self) -> tuple[int, float | None]:
        state = cache.get(self._cache_key) or {}
        return int(state.get("count", 0)), state.get("first_failure_at")

    def add_failure_attempt(self) -> None:
        count, first_failure_at = self._read()
        now = time.time()
        if first_failure_at and now - first_failure_at < self.lock_interval:
            count += 1
        else:
            first_failure_at, count = now, 1
        cache.set(
            self._cache_key,
            {"count": count, "first_failure_at": first_failure_at},
            timeout=self.lock_interval * 2,
        )

    def add_success_attempt(self) -> None:
        cache.delete(self._cache_key)

    def is_user_allowed(self) -> bool:
        count, first_failure_at = self._read()
        if not first_failure_at:
            return True
        within_window = time.time() - first_failure_at < self.lock_interval
        return not (within_window and count > self.max_failed_logins)


def check_login_allowed(*keys: str) -> None:
    for key in keys:
        if key and not LoginAttemptTracker(key).is_user_allowed():
            raise SecurityException(
                "Your account has been locked and will resume after "
                f"{getattr(settings, 'LOGIN_LOCK_INTERVAL_SECONDS', 60)} seconds"
            )


def record_login_failure(*keys: str) -> None:
    for key in keys:
        if key:
            LoginAttemptTracker(key).add_failure_attempt()


def record_login_success(*keys: str) -> None:
    for key in keys:
        if key:
            LoginAttemptTracker(key).add_success_attempt()


def rate_limit(
    limit: int = 5,
    seconds: int = 86400,
    key: str | Callable[[dict], str] | None = None,
    normalise=None,
):
    """Limit a view method using the request passed explicitly to that method."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            if request is None:
                request = next(
                    (arg for arg in args if hasattr(arg, "META") and hasattr(arg, "method")),
                    None,
                )
            identity = resolve_ip(request) if request is not None else ""
            identity = identity or ""
            if key:
                inputs = build_payload(request) if request is not None else {}
                if callable(key):
                    try:
                        value = key(inputs) or ""
                    except Exception:
                        value = ""
                else:
                    value = inputs.get(key, "")
                if normalise is not None:
                    try:
                        value = normalise(value)
                    except Exception:
                        value = ""
                identity = f"{identity}:{value}"
            if not identity.strip(":"):
                return func(*args, **kwargs)

            cache_key = f"rl:{func.__module__}.{func.__qualname__}:{identity}"
            cache.add(cache_key, 0, timeout=seconds)
            try:
                count = cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, timeout=seconds)
                count = 1
            if count > limit:
                raise RateLimitExceededError(
                    "You hit the rate limit because of too many requests. "
                    "Please try after sometime."
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
