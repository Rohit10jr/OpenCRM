"""Row-level access for CRM Lead and CRM Deal.

Ported from ``crm/permissions/org_hierarchy.py`` (368 LOC). This is the security-critical
phase: getting it wrong leaks other people's leads.

**The rule order is load-bearing.** It is reproduced below exactly as upstream evaluates
it, with the source line for each step. Reordering steps 3 and 4 in particular would
silently widen access for every Sales Manager.

``has_permission`` re-runs the *same* query conditions against the single row
(``org_hierarchy.py:91-95``), so the two hooks cannot drift apart - there is one
definition of the rules, not two.
"""

from __future__ import annotations

from django.db.models import Q

from frappe_core.assignment import INACTIVE_FOR_PERMISSION
from frappe_core.session import get_request_cache

#: ``org_hierarchy.py:7-10``. The owner column differs per doctype.
_OWNER_FIELD = {
    "CRM Lead": "lead_owner",
    "CRM Deal": "deal_owner",
}

ADMINISTRATOR = "Administrator"
ROLE_SYSTEM_MANAGER = "System Manager"
ROLE_SALES_MANAGER = "Sales Manager"


# ---------------------------------------------------------------------------
# Cached lookups - these run on every list request (PHASE_2_PERMISSIONS.md section 3)
# ---------------------------------------------------------------------------


def _cached(key, producer):
    cache = get_request_cache()
    if key not in cache:
        cache[key] = producer()
    return cache[key]


def hierarchy_enabled() -> bool:
    """``FCRM Settings.enable_sales_hierarchy`` (``org_hierarchy.py:13-14``)."""

    def load():
        from crm_app.models import FCRMSettings

        return bool(
            FCRMSettings._default_manager.values_list(
                "enable_sales_hierarchy", flat=True
            ).first()
        )

    return _cached("hierarchy_enabled", load)


def _get_roles(user: str) -> set[str]:
    def load():
        from frappe_platform.models import User

        obj = User._default_manager.filter(pk=user).first()
        return obj.get_roles() if obj else set()

    return _cached(f"roles:{user}", load)


def _in_hierarchy(user: str) -> bool:
    """``org_hierarchy.py:106-107`` - a CRM Sales Hierarchy row exists for the user."""

    def load():
        from crm_app.models import CRMSalesHierarchy

        return CRMSalesHierarchy._default_manager.filter(user=user).exists()

    return _cached(f"in_hierarchy:{user}", load)


def _team_member_users(user: str):
    """Users in ``user``'s subtree, inclusive of ``user``.

    ``org_hierarchy.py:110-119`` joins the hierarchy to itself on
    ``Member.lft >= Mgr.lft AND Member.lft <= Mgr.rgt``. A range join has no clean
    correlated-subquery form in the ORM, so the manager's own bounds are fetched once
    (cached per request) and used to build a single ``IN (SELECT ...)`` subquery - which
    keeps this to one extra query per request rather than one per row.

    Note the join is inclusive of the manager's own node, because
    ``Mgr.lft >= Mgr.lft`` holds. A manager therefore always sees their own records
    through this clause as well as through the owner check.
    """

    def load():
        from crm_app.models import CRMSalesHierarchy

        bounds = list(
            CRMSalesHierarchy._default_manager.filter(user=user)
            .exclude(lft__isnull=True)
            .exclude(rgt__isnull=True)
            .values_list("lft", "rgt")
        )
        return bounds

    bounds = _cached(f"subtree_bounds:{user}", load)
    if not bounds:
        return None

    from crm_app.models import CRMSalesHierarchy

    range_q = Q()
    for lft, rgt in bounds:
        range_q |= Q(lft__gte=lft, lft__lte=rgt)
    return CRMSalesHierarchy._default_manager.filter(range_q).values_list("user", flat=True)


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------


def _assigned_via_todo(doctype: str, users) -> Q:
    """``name IN (SELECT reference_name FROM ToDo WHERE ... )``.

    ``org_hierarchy.py:42-50``. Three things matter here and each has bitten someone:

    * it queries **ToDo**, never ``_assign`` - that column is a cache and is writable
      through the generic endpoint (PHASE_0_FOUNDATION.md section 3);
    * ``status != 'Cancelled'`` - a cancelled assignment grants no access;
    * ``Closed`` is **not** excluded here, unlike the display list in
      ``crm/api/doc.py:615``. A closed assignment still grants access.
    """
    from frappe_platform.models import ToDo

    todos = ToDo._default_manager.filter(reference_type=doctype).exclude(
        status__in=INACTIVE_FOR_PERMISSION
    )
    if isinstance(users, str):
        todos = todos.filter(allocated_to=users)
    else:
        todos = todos.filter(allocated_to__in=users)
    return Q(name__in=todos.values_list("reference_name", flat=True))


def _permission_query_conditions(user: str | None, doctype: str) -> Q | None:
    """``org_hierarchy.py:17-60``. ``None`` == unrestricted (upstream returns ``""``)."""
    from frappe_core.session import get_current_user

    if not user:
        user = get_current_user()

    # 1. The literal Administrator *user*, not merely the role (line 21-22).
    if user == ADMINISTRATOR:
        return None

    roles = _get_roles(user)

    # 2. System Manager role (line 24-26).
    if ROLE_SYSTEM_MANAGER in roles:
        return None

    # 3. Compute tree membership (line 28).
    in_tree = hierarchy_enabled() and _in_hierarchy(user)

    # 4. A Sales Manager *outside* the tree keeps the legacy see-everything behaviour
    #    (line 30-32). This is deliberate upstream, not a bug. Preserve it.
    if ROLE_SALES_MANAGER in roles and not in_tree:
        return None

    owner_field = _OWNER_FIELD[doctype]

    # 5. In the tree: own or subtree-owned, or assigned to anyone in the subtree
    #    (line 38-51).
    if in_tree:
        members = _team_member_users(user)
        owned = Q(**{owner_field: user})
        if members is not None:
            owned |= Q(**{f"{owner_field}__in": members})
        assigned = _assigned_via_todo(
            doctype, members if members is not None else user
        )
        if members is not None:
            assigned |= _assigned_via_todo(doctype, user)
        return owned | assigned

    # 6. Default (Sales User): own records plus records directly assigned (line 53-60).
    return Q(**{owner_field: user}) | _assigned_via_todo(doctype, user)


def get_lead_permission_query_conditions(doctype: str = "CRM Lead", user: str | None = None):
    return _permission_query_conditions(user, "CRM Lead")


def get_deal_permission_query_conditions(doctype: str = "CRM Deal", user: str | None = None):
    return _permission_query_conditions(user, "CRM Deal")


def _has_permission(doc, ptype: str, user: str | None, doctype: str) -> bool | None:
    """``org_hierarchy.py:73-95``.

    The short-circuit order differs from the query-conditions order: the ``create`` /
    unsaved check sits **third**, before tree membership is computed
    (PHASE_2_PERMISSIONS.md section 4). Skip it and every create fails.
    """
    from frappe_core.session import get_current_user

    if not user:
        user = get_current_user()

    if user == ADMINISTRATOR:
        return True

    roles = _get_roles(user)
    if ROLE_SYSTEM_MANAGER in roles:
        return True

    # Unsaved documents always pass (line 84-85).
    if ptype == "create" or not getattr(doc, "pk", None):
        return True

    in_tree = hierarchy_enabled() and _in_hierarchy(user)
    if ROLE_SALES_MANAGER in roles and not in_tree:
        return True

    # Re-run the *same* conditions against this one row (line 91-95). One source of
    # truth for the rules, so list filtering and object checks cannot disagree.
    conditions = _permission_query_conditions(user, doctype)
    if conditions is None:
        return True
    return type(doc)._default_manager.filter(pk=doc.pk).filter(conditions).exists()


def has_lead_permission(doc, ptype: str = "read", user: str | None = None):
    return _has_permission(doc, ptype, user, "CRM Lead")


def has_deal_permission(doc, ptype: str = "read", user: str | None = None):
    return _has_permission(doc, ptype, user, "CRM Deal")


def _has_permission_batch(doctype: str, instances, ptype: str, user: str | None):
    """:func:`_has_permission` for a whole batch, in one query instead of N (C9).

    The step order is the same as the single-object version and deliberately reads the
    same way — the short-circuits are all row-independent, and the only row-dependent
    step is the final one, which upstream runs as ``filter(pk=doc.pk).filter(conditions)``
    per row. Here it is one ``pk__in`` over the batch.

    It has to stay in step with :func:`_has_permission`; if the two ever disagree the
    single-object answer is the one to trust, because that is the one the whole app uses.
    """
    from frappe_core.session import get_current_user

    instances = list(instances)
    if not instances:
        return []
    if not user:
        user = get_current_user()

    if user == ADMINISTRATOR:
        return instances

    roles = _get_roles(user)
    if ROLE_SYSTEM_MANAGER in roles:
        return instances

    if ptype == "create":
        return instances

    # Unsaved rows always pass (line 84-85) and cannot be queried for.
    unsaved = [doc for doc in instances if not getattr(doc, "pk", None)]
    saved = [doc for doc in instances if getattr(doc, "pk", None)]
    if not saved:
        return unsaved

    in_tree = hierarchy_enabled() and _in_hierarchy(user)
    if ROLE_SALES_MANAGER in roles and not in_tree:
        return instances

    conditions = _permission_query_conditions(user, doctype)
    if conditions is None:
        return instances

    model = type(saved[0])
    permitted = set(
        model._default_manager.filter(pk__in=[doc.pk for doc in saved])
        .filter(conditions)
        .values_list("pk", flat=True)
    )
    # Input order, so a caller can pair the result up with what it passed in.
    return [
        doc
        for doc in instances
        if not getattr(doc, "pk", None) or doc.pk in permitted
    ]


def has_lead_permission_batch(doctype, instances, ptype="read", user=None):
    return _has_permission_batch("CRM Lead", instances, ptype, user)


def has_deal_permission_batch(doctype, instances, ptype="read", user=None):
    return _has_permission_batch("CRM Deal", instances, ptype, user)
