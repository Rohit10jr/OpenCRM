"""``crm.api.notifications.*``. Ported from ``crm/api/notifications.py``."""

from __future__ import annotations

from frappe_core.session import get_current_user
from frappe_core.whitelist import whitelist


def get_hash(notification) -> str:
    """``crm/api/notifications.py:57-69``.

    The ``"has been removed by"`` substring test is upstream's, and it is a content
    sniff on user-facing copy - fragile, but reproduced because the frontend routes on
    the result and changing it would change where a notification click lands.
    """
    _hash = ""
    if notification["type"] == "Mention" and notification["notification_type_doc"]:
        _hash = "#" + notification["notification_type_doc"]

    if notification["type"] == "WhatsApp":
        _hash = "#whatsapp"

    if (
        notification["type"] == "Assignment"
        and notification["notification_type_doctype"] == "CRM Task"
    ):
        _hash = "#tasks"
        if "has been removed by" in (notification["message"] or ""):
            _hash = ""
    return _hash


@whitelist("crm.api.notifications.get_notifications")
def get_notifications():
    """``crm/api/notifications.py:6-49``.

    ``reference_doctype`` and ``route_name`` are **rewritten** on the way out - the
    frontend receives ``"deal"``/``"lead"`` and ``"Deal"``/``"Lead"``, not the doctype
    name. Anything that is not a CRM Deal falls to the lead spelling, which is upstream's
    ternary, not a guess.
    """
    from frappe_core.query import base_queryset
    from frappe_platform.models import User

    user = get_current_user()
    # Upstream's query is ``WHERE to_user = session.user`` for everyone (lines 8-13),
    # and the filter has to be stated here too. The permission rule is `to_user = user`
    # only for ordinary users; for Administrator and System Managers it is
    # unrestricted, as upstream's is, so reading through ``base_queryset`` alone put
    # every user's notifications in an administrator's bell (FINDINGS.md 61).
    rows = list(
        base_queryset("CRM Notification", user)
        .filter(to_user=user)
        .order_by("-creation")
        .values(
            "creation",
            "from_user",
            "type",
            "to_user",
            "read",
            "message",
            "notification_text",
            "notification_type_doctype",
            "notification_type_doc",
            "reference_doctype",
            "reference_name",
        )
    )

    senders = {r["from_user"] for r in rows if r["from_user"]}
    full_names = dict(
        User._default_manager.filter(name__in=senders).values_list("name", "full_name")
    )

    notifications = []
    for row in rows:
        is_deal = row["reference_doctype"] == "CRM Deal"
        notifications.append(
            {
                "creation": row["creation"],
                "from_user": {
                    "name": row["from_user"],
                    "full_name": full_names.get(row["from_user"]),
                },
                "type": row["type"],
                "to_user": row["to_user"],
                "read": row["read"],
                "hash": get_hash(row),
                "notification_text": row["notification_text"],
                "notification_type_doctype": row["notification_type_doctype"],
                "notification_type_doc": row["notification_type_doc"],
                "reference_doctype": "deal" if is_deal else "lead",
                "reference_name": row["reference_name"],
                "route_name": "Deal" if is_deal else "Lead",
            }
        )
    return notifications


@whitelist("crm.api.notifications.mark_as_read")
def mark_as_read(doc: str | None = None):
    """``crm/api/notifications.py:52-64``.

    Scoped to the caller's own unread notifications. ``doc`` narrows to the ones raised
    by a particular comment or document, which is how "mark this thread read" works.
    """
    from django.db.models import Q

    from frappe_core.query import base_queryset

    # ``filters = {"to_user": user, "read": False}`` upstream (line 54), for every caller.
    # Stated here rather than left to the permission rule, which is unrestricted for an
    # administrator: without it "Mark all as read" cleared every user's notifications
    # (FINDINGS.md 61).
    user = get_current_user()
    queryset = base_queryset("CRM Notification", user).filter(to_user=user, read=False)
    if doc:
        queryset = queryset.filter(Q(comment=doc) | Q(notification_type_doc=doc))

    # save() per row rather than update(): CRMNotification.on_update is the phase-6
    # realtime publish seam, and a bulk update would skip it.
    for notification in list(queryset):
        notification.read = True
        notification.save()
