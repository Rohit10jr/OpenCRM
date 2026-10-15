"""Version-15's Assignment Rule engine.

The ordering and status transitions follow
``frappe/automation/doctype/assignment_rule/assignment_rule.py:69-420``. Conditions are
the deliberate port divergence recorded in FINDINGS.md 80: the CRM editor's JSON is
evaluated as data by :mod:`crm_app.conditions`; saved Python is never executed. Frappe
``msgprint``s ``Auto assignment failed: {0}`` when evaluation fails. This port has no
successful-request message channel, so it logs that text at warning level and lets the
document save continue (the same divergence as ``crm_app.api.bulk_update``).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable

from celery import shared_task
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Count
from django.db.models.signals import post_delete, post_save, pre_save
from django.utils import timezone

from crm_app.api.email_template import render_template
from crm_app.conditions import ConditionError, document_values, evaluate
from frappe_core import children, permissions, registry
from frappe_core.assignment import assign_to_user
from frappe_core.exceptions import DoesNotExistError
from frappe_core.exceptions import PermissionError as FrappePermissionError
from frappe_core.query import parse_json_param
from frappe_core.session import get_current_user, session_user
from frappe_core.whitelist import whitelist
from frappe_platform.models import (
    AssignmentRule,
    AssignmentRuleUser,
    ToDo,
    User,
)

logger = logging.getLogger(__name__)

_RULES_CACHE_PREFIX = "assignment-rules:enabled:"
_DUE_RULES_CACHE_PREFIX = "assignment-rules:due:"
_SKIP_DOCTYPES = {
    "ToDo",
    "Assignment Rule",
    # The only version-15 ``log_types`` currently registered by the port.
    "Version",
}

# The test seam corresponding to ``frappe.flags.assignment_day``. A weekday string
# here wins over the site's local weekday.
assignment_day: str | None = None
_rules_table_ready = False


def _rules_table_exists() -> bool:
    """Stay inert while an initial ``migrate`` has not created Assignment Rule yet."""
    global _rules_table_ready
    if not _rules_table_ready:
        _rules_table_ready = AssignmentRule._meta.db_table in connection.introspection.table_names()
    return _rules_table_ready


def _cache_key(prefix: str, doctype: str) -> str:
    # Memcached rejects spaces and control characters in keys; a digest also prevents
    # two unusual doctype spellings from colliding after sanitisation.
    return f"{prefix}{hashlib.sha256(doctype.encode()).hexdigest()}"


def _rule_names(doctype: str) -> list[str]:
    if not _rules_table_exists():
        return []
    key = _cache_key(_RULES_CACHE_PREFIX, doctype)
    names = cache.get(key)
    if names is None:
        names = list(
            AssignmentRule._default_manager.filter(
                document_type=doctype, disabled=False
            )
            .order_by("-priority")
            .values_list("pk", flat=True)
        )
        cache.set(key, names, None)
    return names


def _due_rule_names(doctype: str) -> list[str]:
    if not _rules_table_exists():
        return []
    key = _cache_key(_DUE_RULES_CACHE_PREFIX, doctype)
    names = cache.get(key)
    if names is None:
        names = list(
            AssignmentRule._default_manager.filter(
                document_type=doctype,
                disabled=False,
            )
            .exclude(due_date_based_on="")
            .values_list("pk", flat=True)
        )
        cache.set(key, names, None)
    return names


def _invalidate_for(doctype: str | None) -> None:
    if not doctype:
        return
    cache.delete_many(
        [
            _cache_key(_RULES_CACHE_PREFIX, doctype),
            _cache_key(_DUE_RULES_CACHE_PREFIX, doctype),
        ]
    )


def _remember_rule_doctype(sender, instance, raw=False, **kwargs) -> None:
    instance._previous_assignment_rule_doctype = None
    if raw or instance._state.adding or not instance.pk:
        return
    instance._previous_assignment_rule_doctype = (
        sender._default_manager.filter(pk=instance.pk)
        .values_list("document_type", flat=True)
        .first()
    )


def _invalidate_rule_cache(sender, instance, **kwargs) -> None:
    _invalidate_for(getattr(instance, "document_type", None))
    _invalidate_for(getattr(instance, "_previous_assignment_rule_doctype", None))


def _children(rule: AssignmentRule, fieldname: str) -> list:
    spec = children.discover_child_tables(AssignmentRule)[fieldname]
    return children.read_children(rule, spec)


def _is_not_applicable_today(rule: AssignmentRule) -> bool:
    days = [row.day for row in _children(rule, "assignment_days")]
    today = assignment_day or timezone.localdate().strftime("%A")
    return bool(days and today not in days)


def _safe_eval(rule: AssignmentRule, fieldname: str, values: dict) -> bool:
    json_field = {
        "assign_condition": "assign_condition_json",
        "unassign_condition": "unassign_condition_json",
        # Brief 02 deliberately refuses a close condition, but keeping the branch makes
        # apply statement-for-statement compatible if imported data reaches it.
        "close_condition": "close_condition",
    }[fieldname]
    condition = getattr(rule, json_field, "")
    if not condition:
        return False
    try:
        return evaluate(condition, values)
    except ConditionError as exc:
        logger.warning("Auto assignment failed: %s", exc)
        return False


def get_assignments(doctype: str, name) -> list[ToDo]:
    return list(
        ToDo._default_manager.filter(
            reference_type=doctype,
            reference_name=str(name),
        )
        .exclude(status="Cancelled")
        .order_by("pk")[:5]
    )


def _set_status(todos: Iterable[ToDo], status: str) -> bool:
    found = False
    for todo in list(todos):
        found = True
        if todo.status == status:
            continue
        todo.status = status
        # save(), not update(): owner sync, notification, and `_assign` rebuilding are
        # existing ToDo effects and must run exactly once.
        todo.save()
    return found


def clear_assignment(doctype: str, name) -> bool:
    return _set_status(
        ToDo._default_manager.filter(
            reference_type=doctype, reference_name=str(name)
        ),
        "Cancelled",
    )


def close_assignments(doctype: str, name) -> bool:
    return _set_status(
        ToDo._default_manager.filter(
            reference_type=doctype, reference_name=str(name)
        ).exclude(status__in=("Cancelled", "Closed")),
        "Closed",
    )


def reopen_closed_assignment(doctype: str, name) -> bool:
    return _set_status(
        ToDo._default_manager.filter(
            reference_type=doctype,
            reference_name=str(name),
            status="Closed",
        ),
        "Open",
    )


def _round_robin_user(rule: AssignmentRule) -> str | None:
    users = [row.user_id for row in _children(rule, "users") if row.user_id]
    if not users:
        return None
    if not rule.last_user_id or rule.last_user_id == users[-1]:
        return users[0]
    try:
        return users[users.index(rule.last_user_id) + 1]
    except (ValueError, IndexError):
        return users[0]


def _load_balancing_user(rule: AssignmentRule) -> str | None:
    users = [row.user_id for row in _children(rule, "users") if row.user_id]
    if not users:
        return None
    counts = dict(
        ToDo._default_manager.filter(
            reference_type=rule.document_type,
            status="Open",
            allocated_to_id__in=users,
        )
        .values("allocated_to_id")
        .annotate(total=Count("pk"))
        .values_list("allocated_to_id", "total")
    )
    # min is stable, so equal counts retain the child table's idx order.
    return min(users, key=lambda user: counts.get(user, 0))


def _based_on_field_user(rule: AssignmentRule, values: dict) -> str | None:
    user = values.get(rule.field)
    if user and User._default_manager.filter(pk=user).exists():
        return str(user)
    return None


def _weighted_user(rule: AssignmentRule) -> str | None:
    with transaction.atomic():
        locked = AssignmentRule._default_manager.select_for_update().get(pk=rule.pk)
        rows = list(
            AssignmentRuleUser._default_manager.filter(
                parenttype="Assignment Rule",
                parent=str(rule.pk),
                parentfield="weighted_users",
            ).order_by("idx")
        )
        users = [(row.user_id, row.weight or 1) for row in rows if row.user_id]
        total_weight = sum(weight for _, weight in users)
        if not users or total_weight <= 0:
            return None
        slot = (locked.current_index or 0) % total_weight
        cumulative = 0
        for user, weight in users:
            cumulative += weight
            if slot < cumulative:
                AssignmentRule._default_manager.filter(pk=locked.pk).update(
                    current_index=(locked.current_index or 0) + 1
                )
                return user
    return None


def get_user(rule: AssignmentRule, values: dict) -> str | None:
    if rule.rule == "Round Robin":
        return _round_robin_user(rule)
    if rule.rule == "Load Balancing":
        return _load_balancing_user(rule)
    if rule.rule == "Based on Field":
        return _based_on_field_user(rule, values)
    if rule.rule == "Weighted Distribution":
        return _weighted_user(rule)
    return None


def do_assignment(rule: AssignmentRule, doc, values: dict) -> bool:
    doctype, name = type(doc).get_doctype(), doc.pk
    clear_assignment(doctype, name)
    user = get_user(rule, values)
    if not user or not User._default_manager.filter(pk=user).exists():
        return False

    due_date = values.get(rule.due_date_based_on) if rule.due_date_based_on else None
    created = assign_to_user(
        doctype,
        name,
        user,
        description=render_template(rule.description, values),
        assignment_rule=str(rule.pk),
        date=due_date,
    )
    if not created:
        return False
    # Frappe's db_set does not run validation or update ``modified``.
    AssignmentRule._default_manager.filter(pk=rule.pk).update(last_user_id=user)
    rule.last_user_id = user
    return True


def apply(doc=None, method=None, doctype: str | None = None, name=None, user=None):
    """Apply enabled rules in version-15's exact unassign/assign/close order."""
    doctype = doctype or (type(doc).get_doctype() if doc is not None else None)
    if not doctype or doctype in _SKIP_DOCTYPES:
        return None

    if doc is None:
        model = registry.get_model(doctype)
        doc = model._default_manager.filter(pk=name).first()
        if doc is None:
            raise DoesNotExistError(f"{doctype} {name} not found")
        caller = user or get_current_user()
        if not permissions.check_object_permission(doc, "read", caller):
            raise FrappePermissionError(
                f"No permission for {doctype} {name}", title="Not Permitted"
            )

    names = _rule_names(doctype)
    if not names:
        return None
    rules_by_name = AssignmentRule._default_manager.in_bulk(names)
    rules = [rules_by_name[rule_name] for rule_name in names if rule_name in rules_by_name]
    if not rules:
        return None

    values = document_values(doc)
    assignments = get_assignments(doctype, doc.pk)
    clear = True
    new_apply = False

    if assignments:
        clear = False
        for rule in rules:
            if _is_not_applicable_today(rule):
                continue
            if (
                rule.unassign_condition
                and rule.pk in [todo.assignment_rule for todo in assignments]
                and _safe_eval(rule, "unassign_condition", values)
            ):
                clear = clear_assignment(doctype, doc.pk)
            else:
                clear = False
            if clear:
                break

    if clear:
        for rule in rules:
            if _is_not_applicable_today(rule):
                continue
            if _safe_eval(rule, "assign_condition", values):
                new_apply = do_assignment(rule, doc, values)
            if new_apply:
                break

    assignments = get_assignments(doctype, doc.pk)
    if assignments:
        for rule in rules:
            if _is_not_applicable_today(rule):
                continue
            if not new_apply:
                to_close = _safe_eval(rule, "close_condition", values)
                if to_close:
                    _set_status(
                        ToDo._default_manager.filter(
                            reference_type=doctype, reference_name=str(doc.pk)
                        ),
                        "Closed",
                    )
                    break
                if reopen_closed_assignment(doctype, doc.pk):
                    break
            if _safe_eval(rule, "close_condition", values):
                close_assignments(doctype, doc.pk)
    return new_apply


def _remember_due_values(sender, instance, raw=False, **kwargs) -> None:
    instance._assignment_rule_due_values = {}
    if raw:
        return
    doctype = sender.get_doctype()
    names = _due_rule_names(doctype)
    if not names or instance._state.adding or not instance.pk:
        return
    fields = list(
        AssignmentRule._default_manager.filter(pk__in=names)
        .exclude(due_date_based_on="")
        .values_list("due_date_based_on", flat=True)
    )
    concrete = {field.name for field in sender._meta.concrete_fields}
    fields = [field for field in dict.fromkeys(fields) if field in concrete]
    if fields:
        instance._assignment_rule_due_values = (
            sender._default_manager.filter(pk=instance.pk).values(*fields).first() or {}
        )


def update_due_date(doc) -> None:
    doctype = type(doc).get_doctype()
    names = _due_rule_names(doctype)
    if not names:
        return
    previous = getattr(doc, "_assignment_rule_due_values", {})
    for rule in AssignmentRule._default_manager.filter(pk__in=names):
        field = rule.due_date_based_on
        if not field or field not in previous or not hasattr(doc, field):
            continue
        value = getattr(doc, field)
        field_object = doc._meta.get_field(field)
        if field_object.is_relation:
            value = getattr(doc, field_object.attname)
        if previous[field] == value:
            continue
        for todo in ToDo._default_manager.filter(
            assignment_rule=rule.pk,
            reference_type=doctype,
            reference_name=str(doc.pk),
            status="Open",
        ):
            todo.date = value
            todo.save()


def run_after_save(instance) -> None:
    """``on_update``: ``apply`` then ``update_due_date`` (version-15 ``hooks.py:172-173``).

    The enabled-rule cache lookup is intentionally the first operation. A warm doctype
    with no rules therefore incurs no database query.
    """
    names = _rule_names(type(instance).get_doctype())
    if names:
        apply(instance)
    update_due_date(instance)


def _on_document_save(sender, instance, raw=False, update_fields=None, **kwargs) -> None:
    # A partial save is upstream's ``db_set`` / ``set_value``, which runs no hook.
    if raw or update_fields:
        return
    # A lead or deal assigns its owner in ``after_insert`` / ``validate`` upstream
    # (``crm_lead.py:94-104``, ``crm_deal.py``), both of which Frappe runs *before*
    # ``on_update`` (``document.py`` ``insert``: ``after_insert`` then
    # ``run_post_save_methods``). Here that owner sync runs after the row is written,
    # which is after ``post_save``; such a model calls :func:`run_after_save` itself once
    # the owner is assigned, so a rule sees the owner's assignment as upstream's does.
    if getattr(sender, "RUNS_ASSIGNMENT_RULES_AFTER_OWNER_SYNC", False):
        return
    run_after_save(instance)


@shared_task(name="crm.assignment_rule.apply")
def apply_task(doctype: str, name, user: str | None = None):
    with session_user(user):
        return apply(doctype=doctype, name=name, user=get_current_user())


@whitelist("frappe.automation.doctype.assignment_rule.assignment_rule.bulk_apply")
def bulk_apply(doctype: str, docnames):
    names = parse_json_param(docnames, [])
    names = [str(name) for name in names]
    user = get_current_user()
    background = len(names) > 5
    for name in names:
        if background:
            apply_task.delay(doctype, name, user)
        else:
            apply(doctype=doctype, name=name, user=user)
    return None


def connect_signals() -> None:
    pre_save.connect(
        _remember_rule_doctype,
        sender=AssignmentRule,
        dispatch_uid="crm.assignment_rules.rule.pre",
    )
    post_save.connect(
        _invalidate_rule_cache,
        sender=AssignmentRule,
        dispatch_uid="crm.assignment_rules.rule.save",
    )
    post_delete.connect(
        _invalidate_rule_cache,
        sender=AssignmentRule,
        dispatch_uid="crm.assignment_rules.rule.delete",
    )

    for doctype in registry.all_doctypes():
        entry = registry.get_entry(doctype)
        if entry.is_child_table or doctype in _SKIP_DOCTYPES:
            continue
        pre_save.connect(
            _remember_due_values,
            sender=entry.model,
            dispatch_uid=f"crm.assignment_rules.due.pre.{doctype}",
        )
        post_save.connect(
            _on_document_save,
            sender=entry.model,
            dispatch_uid=f"crm.assignment_rules.apply.{doctype}",
        )
