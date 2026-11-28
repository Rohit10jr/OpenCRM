"""CRM View Settings keeps no version history (specs/CONFIGURATION.md 4.7, decision 14).

Ported (REBUILD_PLAN S14) from ``backend/tests/test_version_retention.py:97-107``: the
old backend pins the absence on purpose. Adding ``TRACKED_FIELDS`` to the model fails
this guard and points at specs/VERSION_HISTORY.md, rather than letting saved-view churn
appear in the history unremarked.
"""

from configuration.models import CRMViewSettings


def test_saved_views_are_not_tracked():
    assert not getattr(CRMViewSettings, "TRACKED_FIELDS", ())
