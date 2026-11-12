"""Settings for the backend_v2 test suite."""

from .base import *  # noqa: F401,F403

DEBUG = False

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "opencrm-v2-test-cache",
    }
}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
DATABASES["default"]["CONN_MAX_AGE"] = 0
DATABASES["default"]["CONN_HEALTH_CHECKS"] = False
