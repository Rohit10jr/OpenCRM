"""Base settings shared by every backend_v2 environment."""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"

env = environ.Env()
environ.Env.read_env(str(ENV_FILE))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-fallback-for-tests-only")
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
# The flag belongs to the database it names (owner, DECISIONS 9): set it in that database's
# .env, never in a settings file. Off unless the environment turns it on.
DEV_DATA_ALLOWED = env.bool("DEV_DATA_ALLOWED", default=False)
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"]
)

INSTALLED_APPS = [
    "daphne",
    "channels",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "core",
    "accounts",
    "configuration",
    "contacts",
    "sla",
    "sales",
    "activities",
    "notifications",
    "dashboard",
    "integrations",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE", default="django.db.backends.postgresql"),
        "NAME": env("DB_NAME", default="opencrm_v2"),
        "USER": env("DB_USER", default="postgres"),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
        "TEST": {"NAME": "test_opencrm_v2"},
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ("core.renderers.EnvelopeRenderer",),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "accounts.authentication.VersionedJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("core.permissions.IsAuthenticated",),
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=5)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "name",
    "USER_ID_CLAIM": "user_id",
}

TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)
LOGIN_MAX_CONSECUTIVE_ATTEMPTS = env.int(
    "LOGIN_MAX_CONSECUTIVE_ATTEMPTS", default=10
)
LOGIN_LOCK_INTERVAL_SECONDS = env.int("LOGIN_LOCK_INTERVAL_SECONDS", default=60)

FRONTEND_ORIGIN = env("FRONTEND_ORIGIN", default="http://localhost:8080")
CORS_ALLOWED_ORIGINS = [FRONTEND_ORIGIN]
CORS_ALLOW_CREDENTIALS = True

# Telemetry: on only when both are set (old backend/config/settings/base.py); the
# frontend reads boot_config's `enabled` to decide whether to show the persona wizard.
POSTHOG_PROJECT_ID = env("POSTHOG_PROJECT_ID", default="")
POSTHOG_HOST = env("POSTHOG_HOST", default="")

# Exchange rates (old backend/config/settings/base.py:288-292): a deal or organization in
# another currency asks the provider chosen on FCRM Settings for its rate. Set false on a
# site with no outbound internet, and every such rate is 1 instead of a refused save.
ENABLE_EXCHANGE_RATE_API = env.bool("ENABLE_EXCHANGE_RATE_API", default=True)

# The formats System Settings starts from (old backend/config/settings/base.py:305-313):
# Frappe's own fallbacks. `currency` empty is a fresh site before its setup wizard picked
# one; the frontend shows USD for it.
FRAPPE_SYSDEFAULTS = {
    "date_format": env("FRAPPE_DATE_FORMAT", default="yyyy-mm-dd"),
    "time_format": env("FRAPPE_TIME_FORMAT", default="HH:mm:ss"),
    "number_format": env("FRAPPE_NUMBER_FORMAT", default="#,###.##"),
    "float_precision": env("FRAPPE_FLOAT_PRECISION", default="3"),
    "currency_precision": env("FRAPPE_CURRENCY_PRECISION", default=""),
    "currency": env("FRAPPE_CURRENCY", default=""),
    "rounding_method": env("FRAPPE_ROUNDING_METHOD", default="Banker's Rounding (legacy)"),
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# One hour to choose a password; an invitation's three days are separate.
PASSWORD_RESET_LINK_EXPIRY_MINUTES = env.int(
    "PASSWORD_RESET_LINK_EXPIRY_MINUTES", default=60
)

# The settings-configured outgoing account, as backend/config/settings/base.py has it:
# Django's own names, so get_connection() reads them; EMAIL_HOST empty means no account.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
# Never alongside SSL: Django's SMTP backend refuses both flags.
EMAIL_USE_TLS = (
    env.bool("EMAIL_USE_TLS", default=bool(EMAIL_HOST_USER)) and not EMAIL_USE_SSL
)
EMAIL_PORT = env.int("EMAIL_PORT", default=0) or (
    465 if EMAIL_USE_SSL else 587 if EMAIL_USE_TLS else 25
)
DEFAULT_FROM_EMAIL = (
    env("DEFAULT_FROM_EMAIL", default="")
    or EMAIL_HOST_USER
    or "notifications@example.com"
)
EMAIL_SENDER_NAME = env("EMAIL_SENDER_NAME", default="Frappe")
EMAIL_ALWAYS_USE_ACCOUNT_EMAIL_ID_AS_SENDER = env.bool(
    "EMAIL_ALWAYS_USE_ACCOUNT_EMAIL_ID_AS_SENDER", default=False
)
MAIL_CONNECT_TIMEOUT = env.int("MAIL_CONNECT_TIMEOUT", default=10)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("CACHE_URL", default="redis://127.0.0.1:6379/4"),
    }
}

CELERY_BROKER_URL = env(
    "CELERY_BROKER_URL", default="redis://127.0.0.1:6379/5"
)
CELERY_RESULT_BACKEND = env(
    "CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/6"
)
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
# As the old backend has them (backend/config/settings/base.py:316-326). The queue its
# tasks and beat entries use, so a worker started the old way receives these too; late
# acknowledgement with a prefetch of one, so a task a dying worker held is redelivered;
# JSON only; results expire after a day.
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_EXPIRES = 60 * 60 * 24

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                env("CHANNEL_LAYER_URL", default="redis://127.0.0.1:6379/7")
            ]
        },
    }
}

# The module that finds saved Email Accounts for core.mail (spec CONFIGURATION 4.4); empty
# means the settings-configured account only.
MAIL_ACCOUNT_PROVIDER = "configuration.mail"
