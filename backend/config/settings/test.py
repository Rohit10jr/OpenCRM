"""Test settings.

Runs against the same Postgres server as development; ``pytest-django`` creates and
drops ``test_opencrm`` on every run, which is what proves migrations apply from empty
(docs/internal/RUNBOOK.md, gate step 2).
"""

from .base import *  # noqa: F403,F401
from .base import INSTALLED_APPS

DEBUG = False

# Throwaway doctypes used to exercise the framework. Test-only: phase 0 is forbidden
# from building CRM models (PHASE_0_FOUNDATION.md section 9), so the generic machinery
# has to be proved against models of its own.
INSTALLED_APPS = [*INSTALLED_APPS, "tests_support"]

# No Celery worker and no SMTP server in the test run (docs/internal/RUNBOOK.md, "Tests that would
# need external services"). Tasks execute inline and mail lands in django.core.mail.outbox.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# And no config account (docs/FINDINGS.md 79) unless a test asks for one with
# `override_settings(EMAIL_HOST=...)`. `base.py` reads the developer's `.env`, which
# `.env.example` tells them to give an EMAIL_HOST; the tests that assert "nothing to send
# through" must not depend on what that file says.
EMAIL_HOST = ""

# No Redis either (docs/internal/RUNBOOK.md, same section). The in-memory layer is process-local, which
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

# Persistent connections are a production optimisation (see `base.py`) and a liability
# here. `transaction=True` tests drop and recreate the test database, and a connection
# still held from the previous test blocks the drop:
#
#     database "test_opencrm" is being accessed by other users
#
# Observed, not anticipated. Tests want a deterministic connection lifecycle far more than
# they want the microseconds; anything measuring connection *reuse* has to do it against
# `local`, as the realtime smoke test did.
DATABASES["default"]["CONN_MAX_AGE"] = 0
DATABASES["default"]["CONN_HEALTH_CHECKS"] = False

# A fixed key, so credential encryption is *on* under test rather than skipped. Running
# the tests with encryption disabled would leave the whole of `frappe_core.secrets`
# unexercised while every test still passed - which is the failure mode the setting's
# "absent means off" default is otherwise designed to allow in production.
FIELD_ENCRYPTION_KEY = "test-only-field-encryption-key-not-for-any-real-deployment"
