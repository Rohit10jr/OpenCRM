"""One outbound HTTP helper, shared by every caller that talks to another service.

Ported whole from `backend/crm_app/integrations/http.py` (specs/CONFIGURATION.md 4.3,
decision 5). Every outbound call gets a timeout and a retry policy: a call with no
timeout once held a request for up to 130 seconds (`UPSTREAM_BUGS` #15).

## Retry policy, and what is deliberately *not* retried

Retries cover connection errors, timeouts, and 429/502/503/504 - failures where repeating
the request is meaningful. A 4xx is not retried: it means the request was wrong, and
sending it again turns one bad call into several.

`POST` is in the retried methods, which `urllib3` leaves out by default because a retried
POST can double-submit. A caller that POSTs must be safe to repeat, or pass
`attempts=1`; INTEGRATIONS' spec records why its telephony calls are. The exchange-rate
lookup passes `timeout=5, attempts=1`.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Connect timeout, then read timeout. Short connect (a service that is down should fail
#: fast), longer read (an accepted request may legitimately take a few seconds).
DEFAULT_TIMEOUT = (5, 20)

#: Total attempts, including the first.
DEFAULT_ATTEMPTS = 3

#: Retried because repeating them is meaningful. 4xx is absent on purpose.
RETRY_STATUSES = (429, 502, 503, 504)


def build_session(attempts: int = DEFAULT_ATTEMPTS):
    """A `requests.Session` with the retry policy attached.

    Imported locally, so a module can be imported for its constants without paying for
    `requests`.
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

    Raises `requests.RequestException` on a transport failure; callers decide whether that
    is fatal. It is never swallowed here, because "the service is unreachable" and "the
    service said no" need different handling and only the caller knows which matters.
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

    A URL is the one part of a failed request that reliably ends up in a traceback, a log
    line and an error page, so a credential carried in it (`https://key:token@host/...`)
    is removed before it is logged.
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
