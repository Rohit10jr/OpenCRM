"""Brute-force protection: account lockout and endpoint throttling.

Ports the two mechanisms upstream applies to authentication, which phase 3 left out
because both are framework infrastructure (`docs/internal/PROGRESS_PHASE_3.md`, concern 1):

* :class:`LoginAttemptTracker` - ``frappe/auth.py:519-613``. Counts **consecutive**
  failures and locks for an interval. Reset by any success. Upstream tracks the IP and
  the account separately (``auth.py:260,269``), so switching target does not help an
  attacker.
* :func:`rate_limit` - ``frappe/rate_limiter.py:105-171``. A flat cap on calls to one
  endpoint within a window, keyed on endpoint + IP.

They answer different questions - "is this account under attack?" versus "is this
endpoint being hammered?" - which is why upstream uses both on ``change_password``.

### Two things that decide whether any of this works

**The counters must live somewhere shared.** Django's default cache is per-process, so
with four workers a "10 attempts" limit is really 40, and a restart clears it. The Redis
cache configured in settings is what makes the count real. A limiter on a local-memory
cache is theatre.

**The client IP must be the client's.** Behind a proxy every request appears to come from
the proxy, which would lock out every user at once. ``TRUSTED_PROXY_COUNT`` controls how
many hops of ``X-Forwarded-For`` to trust; the header is only consulted when it is set,
because an attacker who can forge it bypasses the limit entirely.

### Deliberate divergence

Upstream reads its thresholds from the ``System Settings`` doctype
(``allow_consecutive_login_attempts`` = 10, ``allow_login_after_fail`` = 60). That
doctype is not modelled here, so the same numbers are Django settings instead. Behaviour
matches; the place you change it does not.
"""

from __future__ import annotations

from contextvars import ContextVar
from functools import wraps

from django.conf import settings
from django.core.cache import cache

from frappe_core.exceptions import FrappeError

#: Set by :class:`ClientIPMiddleware`. Endpoints are called with only their own kwargs
#: (``method_views._dispatch``), so a decorator cannot reach the request any other way.
_client_ip: ContextVar[str | None] = ContextVar("frappe_client_ip", default=None)


class RateLimitExceededError(FrappeError):
    """Upstream's ``frappe.RateLimitExceededError``. Rendered as HTTP 429."""

    http_status_code = 429


class SecurityException(FrappeError):
    """Upstream's ``frappe.SecurityException`` - raised when an account is locked."""

    http_status_code = 403


def get_client_ip() -> str | None:
    return _client_ip.get()


def _resolve_ip(request) -> str | None:
    """The originating client, honouring ``X-Forwarded-For`` only as far as configured.

    ``TRUSTED_PROXY_COUNT`` is the number of proxies in front of this app. With 0 - the
    default, and correct when nothing fronts it - the header is ignored entirely, because
    a client can send whatever it likes and would otherwise pick its own rate-limit
    bucket.
    """
    hops = int(getattr(settings, "TRUSTED_PROXY_COUNT", 0) or 0)
    if hops:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        chain = [part.strip() for part in forwarded.split(",") if part.strip()]
        if chain:
            # The rightmost entries were added by our own proxies; step back over them.
            index = max(0, len(chain) - hops)
            return chain[index] if index < len(chain) else chain[0]
    return request.META.get("REMOTE_ADDR")


class ClientIPMiddleware:
    """Bind the client IP for the duration of the request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _client_ip.set(_resolve_ip(request))
        try:
            return self.get_response(request)
        finally:
            _client_ip.reset(token)


# --- account lockout ---------------------------------------------------------------


class LoginAttemptTracker:
    """Port of ``frappe/auth.py:519-613``.

    Tracks *consecutive* failures within ``lock_interval``. A success clears the count,
    and a failure arriving after the interval has lapsed starts a fresh window rather
    than adding to a stale one - so an attacker cannot accumulate one attempt per hour
    into a lockout of a legitimate user.

    Upstream stores the count and the first-failure time as two cache hashes; the same
    two values are kept here under one key per identity.
    """

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
        import time

        count, first_failure_at = self._read()
        now = time.time()

        if first_failure_at and (now - first_failure_at) < self.lock_interval:
            count += 1
        else:
            first_failure_at, count = now, 1

        # The entry outlives the window slightly so is_user_allowed can still see it.
        cache.set(
            self._cache_key,
            {"count": count, "first_failure_at": first_failure_at},
            timeout=self.lock_interval * 2,
        )

    def add_success_attempt(self) -> None:
        cache.delete(self._cache_key)

    def is_user_allowed(self) -> bool:
        import time

        count, first_failure_at = self._read()
        if not first_failure_at:
            return True
        within_window = (time.time() - first_failure_at) < self.lock_interval
        # Strictly greater than, as upstream: the Nth failure locks the (N+1)th attempt.
        return not (within_window and count > self.max_failed_logins)


def check_login_allowed(*keys: str) -> None:
    """Raise if any identity is locked out. Upstream checks the IP and the account.

    ``auth.py:260,269`` builds a tracker for each; either being locked stops the login,
    which is what stops an attacker rotating usernames from one address.
    """
    for key in keys:
        if key and not LoginAttemptTracker(key).is_user_allowed():
            raise SecurityException(
                f"Your account has been locked and will resume after "
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


# --- endpoint throttling ------------------------------------------------------------


def rate_limit(limit: int = 5, seconds: int = 86400, key: str | None = None):
    """Port of ``frappe/rate_limiter.py:105-171``. Cap calls to one endpoint per window.

    Applied **below** ``@whitelist`` so the registry stores the wrapped function::

        @whitelist("crm.api.user.change_password")
        @rate_limit(limit=5, seconds=300)
        def change_password(...):

    Deliberately **not** applied to every endpoint, matching upstream, which throttles
    only ``change_password``, password reset and email-link login. A blanket cap would
    trip on a list screen firing a dozen requests at once.

    ``key`` names a parameter to include in the bucket - use it where one IP legitimately
    serves many users and you want per-account limits instead.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            identity = get_client_ip() or ""
            if key:
                identity = f"{identity}:{kwargs.get(key, '')}"
            if not identity.strip(":"):
                # No IP and no key - outside a request, e.g. a direct call in tests.
                return func(*args, **kwargs)

            cache_key = f"rl:{func.__module__}.{func.__qualname__}:{identity}"
            # add() only writes when absent, so the window starts at the first call and
            # is not extended by later ones - upstream's setex-then-incr, atomically.
            if cache.add(cache_key, 0, timeout=seconds):
                pass
            try:
                count = cache.incr(cache_key)
            except ValueError:
                # Expired between add() and incr(); treat as a fresh window.
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
