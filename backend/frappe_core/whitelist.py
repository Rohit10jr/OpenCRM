"""``@frappe.whitelist()`` for the port.

The frontend calls methods by their **dotted Python path** - ``crm.api.doc.get_data``,
``frappe.client.get_list`` - and those strings are part of the hard wire contract
(PORT_PLAN.md section 3). Our modules do not live at those paths, so the path is
declared explicitly rather than derived:

    @whitelist("crm.api.doc.get_data")
    def get_data(...): ...

Declaring it beats deriving it: the string in the decorator is the string the frontend
sends, greppable and impossible to break by moving a module.
"""

from __future__ import annotations

import inspect
from typing import Callable

_METHODS: dict[str, Callable] = {}


class MethodNotFound(KeyError):
    pass


def whitelist(
    dotted_path: str,
    *,
    allow_guest: bool = False,
    methods: tuple[str, ...] = ("GET", "POST"),
    wants_request: bool = False,
):
    """Register ``func`` as callable at ``/api/method/<dotted_path>``.

    ``wants_request`` passes the DRF request in as ``_request``. Almost nothing should
    want it — the payload already merges query string and body, which is what an endpoint
    normally needs.

    **Webhook signature verification is the case it exists for.** A provider signs the
    request URL and puts the signature in a *header*; neither is a parameter, so a handler
    that cannot see the request cannot verify anything. Phase 7's Twilio endpoints took the
    URL and signature as ordinary arguments and were therefore verifiable only in tests —
    a real webhook has no such parameters and was rejected every time. Found by the phase-7
    review.
    """

    def decorator(func: Callable) -> Callable:
        func.__frappe_whitelisted__ = True
        func.__frappe_path__ = dotted_path
        func.__frappe_allow_guest__ = allow_guest
        func.__frappe_methods__ = tuple(m.upper() for m in methods)
        func.__frappe_wants_request__ = wants_request
        _METHODS[dotted_path] = func
        return func

    return decorator


def get_method(dotted_path: str) -> Callable:
    try:
        return _METHODS[dotted_path]
    except KeyError:
        raise MethodNotFound(dotted_path) from None


def has_method(dotted_path: str) -> bool:
    return dotted_path in _METHODS


def all_methods() -> list[str]:
    return sorted(_METHODS)


def bind_arguments(func: Callable, payload: dict) -> dict:
    """Keep only the keys ``func`` actually accepts.

    Frappe passes the whole request payload as kwargs and ignores the surplus; matching
    that keeps the frontend's extra params (``cmd``, cache-busters) from causing a 500.
    """
    signature = inspect.signature(func)
    accepts_kwargs = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()
    )
    if accepts_kwargs:
        return dict(payload)
    allowed = {
        name
        for name, p in signature.parameters.items()
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    return {k: v for k, v in payload.items() if k in allowed}


def _reset_for_tests() -> None:
    _METHODS.clear()
