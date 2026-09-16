"""Base settings shared by every environment.

Secrets and per-machine values come from the repo-root ``.env`` (gitignored).
"""

from datetime import timedelta
from pathlib import Path

import environ

# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
# -> repo root, where .env lives
ROOT_DIR = BASE_DIR.parent

env = environ.Env()
environ.Env.read_env(str(ROOT_DIR / ".env"))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-fallback-for-tests-only")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    # Phase 6. Both must precede `django.contrib.staticfiles`: daphne replaces
    # `runserver` with the ASGI one, and staticfiles replaces it with its own, so
    # whichever is listed later wins. WSGI cannot carry a WebSocket, so it has to be
    # daphne.
    "daphne",
    "channels",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "rest_framework_simplejwt",
    # Gives ``logout`` something to revoke. Without it ``RefreshToken.blacklist()``
    # raises AttributeError and the endpoint is a no-op, so a stolen refresh token
    # stays usable for its full lifetime.
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "treebeard",
    # local
    "frappe_core",
    "frappe_platform",
    "crm_app",
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
    # Binds the ambient "current user", the equivalent of frappe.session.user.
    # DRF views re-bind it after JWT auth; this covers everything else.
    "frappe_core.session.CurrentUserMiddleware",
    # Binds the client IP so the rate limiter can see it. Endpoints are called with
    # only their own kwargs, so a decorator cannot reach the request any other way.
    "frappe_core.security.ClientIPMiddleware",
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
        "NAME": env("DB_NAME", default="opencrm"),
        "USER": env("DB_USER", default="postgres"),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="5432"),
        # Reuse a connection instead of opening one per query. Django's default is 0 -
        # connect, run, close, every time - and the realtime layer makes that expensive:
        # `consumers._may_read` is `@database_sync_to_async`, which Channels wraps in
        # `close_old_connections()` on entry and exit, so **every `doc_subscribe`
        # permission check opened a fresh Postgres connection**. Opening ten documents
        # cost ten connections; a reconnect replays every subscription, so it fans out
        # into one per document, from every client at once after a restart.
        #
        # The usual objection to persistent connections under ASGI - one connection per
        # concurrent request - does not apply: `database_sync_to_async` is
        # `thread_sensitive` by default, so these calls share one executor thread and this
        # yields **one reused connection**, not many.
        #
        # 60 is not a derived number, and does not need to be. Nearly all the benefit is
        # in the first reuse: 0 -> 60 removes ~99.9% of the churn, and 60 -> 3600 removes
        # the remaining 0.1% during idle periods, when there is no load to slow down. Each
        # held connection is a Postgres backend holding ~5-10 MB, which this machine has
        # twice run out of. `None` is deliberately avoided - unbounded lifetime pins a
        # connection for the process's life and is the version that surprises people
        # during a failover.
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        # Mandatory companion. Without it a connection the server dropped is handed out
        # and the request fails; with it, Django notices and reconnects.
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# PHASE_0_FOUNDATION.md section 7: the user PK is the email address, matching Frappe.
AUTH_USER_MODEL = "frappe_platform.User"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    # The envelope + Frappe-shaped error body are applied by our own handler.
    "EXCEPTION_HANDLER": "frappe_core.exceptions.frappe_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ("frappe_core.renderers.FrappeEnvelopeRenderer",),
    "UNAUTHENTICATED_USER": None,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=5)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7)
    ),
    # Rotate on refresh and blacklist the token just used, so a refresh token captured
    # in transit is single-use: whichever party redeems it first invalidates the other.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    # Our user PK is the email string.
    "USER_ID_FIELD": "name",
    "USER_ID_CLAIM": "user_id",
}

FRONTEND_ORIGIN = env("FRONTEND_ORIGIN", default="http://localhost:8080")
CORS_ALLOWED_ORIGINS = [FRONTEND_ORIGIN]
CORS_ALLOW_CREDENTIALS = True

# The backend's own public URL - the equivalent of ``frappe.utils.get_url()``. Upstream
# serves the Vue app and the API from one origin, so it has only the one value; we are
# split, and links that point at ``/api/method/...`` (the invitation accept link,
# crm_invitation.py:38) have to resolve to the backend, not the frontend.
SITE_URL = env("SITE_URL", default="http://localhost:8000")

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

# Redis, not the per-process default. Rate-limit and lockout counters live here, and a
# LocMemCache would give each worker its own count - a "10 attempts" limit becomes 10 per
# worker, and a restart clears it. DB 3: Celery uses 0 and 1, Channels 2.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        # 127.0.0.1, not localhost: on Windows the name resolves to ::1 first and the
        # IPv6 attempt has to time out before it falls back, costing ~2.6s on the first
        # connection of every process. Measured 2633ms via localhost, 746ms via the
        # literal address. The server here is Memurai, which speaks the Redis protocol.
        "LOCATION": env("CACHE_URL", default="redis://127.0.0.1:6379/3"),
    }
}

# Brute-force protection (frappe_core/security.py). Upstream reads these from the
# System Settings doctype, which this port does not model - the values match its
# defaults (allow_consecutive_login_attempts=10, allow_login_after_fail=60).
LOGIN_MAX_CONSECUTIVE_ATTEMPTS = env.int("LOGIN_MAX_CONSECUTIVE_ATTEMPTS", default=10)
LOGIN_LOCK_INTERVAL_SECONDS = env.int("LOGIN_LOCK_INTERVAL_SECONDS", default=60)

# Proxies in front of this app. 0 means X-Forwarded-For is ignored entirely, which is
# correct when nothing fronts it: a client can forge that header and would otherwise
# choose its own rate-limit bucket. Set it to the real hop count behind a load balancer,
# or every user shares one bucket and one attacker locks out the office.
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")

# Seconds to wait for a mail server when validating an Email Account
# (frappe_core/mail.py). Upstream passes no timeout, so an unreachable host blocks the
# save until the OS gives up - 20 to 130 seconds, during which the user sees a spinner
# rather than the error written for them. Raise this if a slow but working relay is
# being reported as broken; do not remove it.
MAIL_CONNECT_TIMEOUT = env.int("MAIL_CONNECT_TIMEOUT", default=10)

# Encrypts credential columns at rest (frappe_core/secrets.py) - currently the Email
# Account password and Frappe Mail api_secret.
#
# Deliberately NOT derived from SECRET_KEY. Rotating SECRET_KEY is a routine Django
# operation that invalidates sessions and signed cookies, both disposable; if credentials
# hung off it, that routine act would silently destroy every stored mail password and
# surface days later as "invitations stopped arriving".
#
# Losing this key means stored credentials must be re-entered. That is what "encrypted at
# rest" means, and is the correct failure. Generate one with:
#     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="crm@example.com")

# Product telemetry (crm_app/api/desk.py:boot_config). Both must be set to switch it on;
# with either blank the frontend is told telemetry is off and skips the persona wizard.
POSTHOG_PROJECT_ID = env("POSTHOG_PROJECT_ID", default="")
POSTHOG_HOST = env("POSTHOG_HOST", default="")

# Celery (phase 5). The queue names mirror upstream's RQ queues: short -> default,
# long -> long (PHASE_5_ASYNC.md intro).
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
# A task that outlives its result is just noise in Redis.
CELERY_RESULT_EXPIRES = 60 * 60 * 24

# Phase 8. How long a password-reset link lives.
#
# **Zero means 60 minutes, not "never expires"** - see frappe_core/password_reset.py.
# Upstream's `reset_password_link_expiry_duration` defaults to 0 and treats that as
# disabling the expiry check, which turns a mail archive into a credential store. That is
# the one part of upstream's reset behaviour this port deliberately refuses.
#
# Separate from the invitation's three days on purpose: three days to accept an invitation,
# one hour to choose a password once you have.
PASSWORD_RESET_LINK_EXPIRY_MINUTES = env.int("PASSWORD_RESET_LINK_EXPIRY_MINUTES", default=60)

# Realtime (phase 6). Off switches the WebSocket route out of the ASGI application and
# makes `realtime.publish` a no-op; nothing else changes, because publishing is never
# load-bearing (PHASE_6_REALTIME.md section 4).
ENABLE_REALTIME = env.bool("ENABLE_REALTIME", default=True)

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        # The same Redis Celery already needs, so realtime adds no infrastructure
        # (PORT_PLAN.md section 10). A Celery worker publishing an event reaches the same
        # layer the web process serves from, which is what makes
        # `run_product_reconciliation` able to notify a browser at all.
        "CONFIG": {"hosts": [env("CHANNEL_LAYER_URL", default=REDIS_URL)]},
    }
}

# Integration feature flags (specs/PHASE_7_INTEGRATIONS.md) - all off.
ENABLE_ERPNEXT = env.bool("ENABLE_ERPNEXT", default=False)
ENABLE_TWILIO = env.bool("ENABLE_TWILIO", default=False)
ENABLE_EXOTEL = env.bool("ENABLE_EXOTEL", default=False)
ENABLE_FACEBOOK_LEAD_SYNC = env.bool("ENABLE_FACEBOOK_LEAD_SYNC", default=False)
ENABLE_WHATSAPP = env.bool("ENABLE_WHATSAPP", default=False)
