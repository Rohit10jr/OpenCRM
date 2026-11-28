"""Settings for the backend_v2 test suite."""

from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS

INSTALLED_APPS = [*INSTALLED_APPS, "tests_support"]
ROOT_URLCONF = "config.test_urls"

DEBUG = False
# DEV_DATA_ALLOWED is not set here (default off, temp A-48 group 5 item 7): the tests
# that run seed_dev_data or clear_dev_data turn it on for themselves.
# The old test key (backend/config/settings/test.py:70): Email Account stores its password
# encrypted, and without a key every test that saves one would pass only where a
# developer's environment happens to supply it. Never a real deployment's key.
FIELD_ENCRYPTION_KEY = "test-only-field-encryption-key-not-for-any-real-deployment"

# No Celery worker and no SMTP server under test: tasks run inline and mail lands in
# django.core.mail.outbox. No config account unless a test sets EMAIL_HOST, whatever the
# developer's .env says (backend/config/settings/test.py).
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_HOST = ""
# No test reaches an exchange-rate provider; the tests that need one turn it on and fake it.
ENABLE_EXCHANGE_RATE_API = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "opencrm-v2-test-cache",
    }
}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
DATABASES["default"]["CONN_MAX_AGE"] = 0
DATABASES["default"]["CONN_HEALTH_CHECKS"] = False
