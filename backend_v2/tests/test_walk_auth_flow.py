"""The onboarding walk (scripts/walk_auth_flow.py) under pytest, so CI walks it too.

A transactional test: the invitation email is queued after commit, and only a real
commit fires it, as in production.
"""

import pytest

from scripts.walk_auth_flow import walk


@pytest.mark.django_db(transaction=True)
def test_the_onboarding_flow_walks_end_to_end(administrator):
    steps = walk()

    failed = [(label, detail) for label, ok, detail in steps if not ok]
    assert not failed, failed
    assert len(steps) >= 24
