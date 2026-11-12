"""Frappe-compatible request input parsing."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from typing import Any


def parse_json_param(value: Any, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def build_payload(request) -> dict:
    payload = {
        key: parse_json_param(value, value)
        for key, value in request.query_params.items()
    }
    data = getattr(request, "data", None)
    if hasattr(data, "dict"):
        payload.update(data.dict())
    elif isinstance(data, dict):
        payload.update(data)
    payload.pop("cmd", None)
    return payload


def bind_arguments(func: Callable, payload: dict) -> dict:
    signature = inspect.signature(func)
    if any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    ):
        return dict(payload)
    allowed = {
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }
    return {key: value for key, value in payload.items() if key in allowed}
