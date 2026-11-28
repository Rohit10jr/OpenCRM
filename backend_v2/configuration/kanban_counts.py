"""A kanban card's four badge counts (specs/CONFIGURATION.md 4.8, decision 6; temp A-40).

The old `get_counts` (`backend/frappe_core/api/doc.py:564-598`) counts Communication and
Automated Message together, Comment, CRM Task and FCRM Note rows naming the card. Those
are ACTIVITIES' models, so the counts come from the module `KANBAN_COUNTS_PROVIDER`
names: `counts_for(doctype, names) -> {name: {the four keys}}`, batched so a column
costs one query per kind. Until ACTIVITIES names its module, every count is 0, which
is the true count while those rows cannot exist (the screen hides 0 and a missing key
alike, `Deals.vue:179`). Like the old ones, the counts are of related rows and are not
filtered by the caller's rules; only the cards were filtered first. `configuration`
never imports `activities`.
"""

from __future__ import annotations

from importlib import import_module

from django.conf import settings
from django.core.checks import Error, register

COUNT_KEYS = ("_email_count", "_comment_count", "_task_count", "_note_count")


def zero_counts(doctype: str, names: list) -> dict:
    return {name: dict.fromkeys(COUNT_KEYS, 0) for name in names}


def provider():
    path = getattr(settings, "KANBAN_COUNTS_PROVIDER", "") or ""
    if not path:
        return zero_counts
    return import_module(path).counts_for


def add_counts(doctype: str, cards: list[dict]) -> None:
    """Each card gets the four keys; a card without a name gets none, as the old code."""
    names = [card["name"] for card in cards if card.get("name") is not None]
    if not names:
        return
    counts = provider()(doctype, names)
    for card in cards:
        name = card.get("name")
        if name is not None:
            card.update(counts.get(name) or dict.fromkeys(COUNT_KEYS, 0))


@register()
def check_kanban_counts_provider(app_configs, **kwargs):
    """A named provider must resolve and expose `counts_for`, so a typo never answers
    zeros quietly."""
    path = getattr(settings, "KANBAN_COUNTS_PROVIDER", "") or ""
    if not path:
        return []
    try:
        module = import_module(path)
    except ImportError as exc:
        return [
            Error(
                f"KANBAN_COUNTS_PROVIDER {path!r} does not resolve: {exc}",
                hint="Name the module that provides counts_for(doctype, names).",
                id="configuration.E001",
            )
        ]
    if not callable(getattr(module, "counts_for", None)):
        return [
            Error(
                f"KANBAN_COUNTS_PROVIDER {path!r} lacks counts_for",
                hint="Expose counts_for(doctype, names) -> {name: {the four counts}}.",
                id="configuration.E001",
            )
        ]
    return []
