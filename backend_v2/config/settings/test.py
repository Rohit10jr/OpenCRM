"""Settings for the backend_v2 test suite."""

from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS

INSTALLED_APPS = [*INSTALLED_APPS, "tests_support"]
ROOT_URLCONF = "config.test_urls"

DEBUG = False
DEV_DATA_ALLOWED = True

# No Celery worker and no SMTP server under test: tasks run inline and mail lands in
# django.core.mail.outbox. No config account unless a test sets EMAIL_HOST, whatever the
# developer's .env says (backend/config/settings/test.py).
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_HOST = ""

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "opencrm-v2-test-cache",
    }
}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
DATABASES["default"]["CONN_MAX_AGE"] = 0
DATABASES["default"]["CONN_HEALTH_CHECKS"] = False
