"""Test settings.

Runs against the same Postgres server as development; ``pytest-django`` creates and
drops ``test_opencrm`` on every run, which is what proves migrations apply from empty
(RUNBOOK.md, gate step 2).
"""

from .base import *  # noqa: F403,F401
from .base import INSTALLED_APPS

DEBUG = False

# Throwaway doctypes used to exercise the framework. Test-only: phase 0 is forbidden
# from building CRM models (PHASE_0_FOUNDATION.md section 9), so the generic machinery
# has to be proved against models of its own.
INSTALLED_APPS = [*INSTALLED_APPS, "tests_support"]

# No Celery worker and no SMTP server in the test run (RUNBOOK.md, "Tests that would
# need external services"). Tasks execute inline and mail lands in django.core.mail.outbox.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# No Redis either (RUNBOOK.md, same section). The in-memory layer is process-local, which
# is all `WebsocketCommunicator` needs: publisher and consumer are the same process.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Likewise the cache. Production points this at Redis so rate-limit and lockout counters
# are shared across workers (frappe_core/security.py); the test run is single-process, so
# local memory gives identical semantics with no service to depend on.
#
# It must be per-test-isolated, though: a counter surviving between tests would make them
# order-dependent. `conftest.clear_cache` flushes it.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "frappe-test-cache",
    }
}

# Fast hashing - these tests create a lot of users.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
