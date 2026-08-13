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

# Fast hashing - these tests create a lot of users.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
