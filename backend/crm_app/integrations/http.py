"""One outbound HTTP helper, shared by every integration.

`PHASE_7_INTEGRATIONS.md` §3: *"Every outbound call gets a timeout and a retry policy."*
That rule exists because of `UPSTREAM_BUGS` #15 — phase 3 shipped a mail-server validation
with no timeout and it hung the request for up to 130 seconds.

**Upstream's integrations have the same defect.** `crm/integrations/exotel/handler.py:99`
and `:145` call `requests.post` / `requests.get` with no `timeout` at all, and
`twilio_handler.py` inherits whatever the SDK defaults to. A provider that accepts a
connection and never answers would hang a worker thread indefinitely. Recorded as a
divergence rather than reproduced: this is a bug nothing user-visible depends on, and the
failure mode is an outage rather than a wrong answer.

## Retry policy, and what is deliberately *not* retried

Retries cover connection errors, timeouts, and 429/502/503/504 — failures where repeating
the request is meaningful. A 4xx is not retried: it means the request was wrong, and
sending it four more times turns one bad call into five.

**`POST` is retried too, which needs justifying.** `urllib3` excludes POST from its default
`allowed_methods` because a retried POST can double-submit. The calls here are safe to
repeat for a reason specific to this domain: an outbound call request that failed to
*connect* never reached the provider, and one that returned 502/503 was rejected before
dialling. The dangerous case — a request that succeeded but whose response was lost — is
covered by the call-log dedupe, which is keyed on the provider's own call id.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Connect timeout, then read timeout. Short connect (a provider that is down should fail
#: fast), longer read (an accepted request may legitimately take a few seconds).
DEFAULT_TIMEOUT = (5, 20)

#: Total attempts, including the first.
DEFAULT_ATTEMPTS = 3

#: Retried because repeating them is meaningful. 4xx is absent on purpose.
RETRY_STATUSES = (429, 502, 503, 504)


def build_session(attempts: int = DEFAULT_ATTEMPTS):
    """A `requests.Session` with the retry policy attached.

    Imported locally: `requests` is a hard dependency, but keeping the import inside means
    an integration module can be imported for its constants without paying for it.
    """
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry = Retry(
        total=attempts - 1,
        connect=attempts - 1,
        read=attempts - 1,
        status=attempts - 1,
        status_forcelist=RETRY_STATUSES,
        allowed_methods=frozenset({"GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"}),
        backoff_factor=0.5,
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def request(
    method: str,
    url: str,
    *,
    auth=None,
    data=None,
    json=None,
    params=None,
    headers=None,
    timeout=DEFAULT_TIMEOUT,
    attempts: int = DEFAULT_ATTEMPTS,
):
    """One outbound call, with a timeout and a retry policy. Returns the response.

    Raises `requests.RequestException` on a transport failure — callers decide whether that
    is fatal. It is never swallowed here, because "the provider is unreachable" and "the
    provider said no" need different handling and only the caller knows which matters.
    """
    session = build_session(attempts)
    try:
        return session.request(
            method,
            url,
            auth=auth,
            data=data,
            json=json,
            params=params,
            headers=headers,
            timeout=timeout,
        )
    finally:
        session.close()


def redact(url: str) -> str:
    """Strip userinfo from a URL before it reaches a log or an exception message.

    Upstream builds Exotel endpoints as ``https://{api_key}:{api_token}@{subdomain}/...``
    (`handler.py:131-140`), so the credential is *in the URL* — and a URL is the one part of
    a failed request that reliably ends up in a traceback, a log line and an error page.

    This port passes credentials via `auth=` instead, so the situation should not arise;
    this exists so that if a URL from anywhere else is logged, it is logged safely.
    """
    from urllib.parse import urlsplit, urlunsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable url>"
    if not parts.netloc or "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
