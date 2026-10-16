"""Service Level Agreement selection; deadline application follows in brief 06."""

from __future__ import annotations

import logging

from django.db.models import Q
from django.utils import timezone

from crm_app.conditions import ConditionError, evaluate, is_empty
from crm_app.models.sla import CRMServiceLevelAgreement

logger = logging.getLogger(__name__)


def get_sla(doc) -> CRMServiceLevelAgreement | None:
    """Return the first applicable SLA, with a default policy considered last.

    Unlike upstream's ``safe_eval``, a stored condition that can no longer be evaluated
    is logged at warning level and treated as a non-match. One stale policy therefore
    cannot prevent every lead or deal from being saved.
    """

    now = timezone.now()
    local_date = timezone.localtime(now).date()
    slas = CRMServiceLevelAgreement._default_manager.filter(
        apply_on=doc.get_doctype(),
        enabled=True,
    ).filter(
        Q(start_date__isnull=True) | Q(start_date__lte=local_date),
        Q(end_date__isnull=True) | Q(end_date__gte=local_date),
    )

    priority = getattr(doc, "communication_status_id", None)
    if priority:
        slas = slas.filter(priorities__priority_id=priority)

    # The upstream query declares no ordering. Clear this model's list-screen ordering
    # (``-modified``), which must not silently turn "first" into "most recently edited".
    candidates = list(slas.order_by().distinct())
    candidates.sort(key=lambda sla: bool(sla.default))

    for sla in candidates:
        try:
            if is_empty(sla.condition_json) or evaluate(sla.condition_json, doc):
                return sla
        except ConditionError as exc:
            logger.warning(
                "SLA %s condition could not be evaluated: %s",
                sla.pk,
                exc,
            )
    return None
