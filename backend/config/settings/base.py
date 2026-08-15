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
        minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=60)
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

CORS_ALLOWED_ORIGINS = [env("FRONTEND_ORIGIN", default="http://localhost:8080")]
CORS_ALLOW_CREDENTIALS = True

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")

# Integration feature flags (specs/PHASE_7_INTEGRATIONS.md) - all off.
ENABLE_ERPNEXT = env.bool("ENABLE_ERPNEXT", default=False)
ENABLE_TWILIO = env.bool("ENABLE_TWILIO", default=False)
ENABLE_EXOTEL = env.bool("ENABLE_EXOTEL", default=False)
ENABLE_FACEBOOK_LEAD_SYNC = env.bool("ENABLE_FACEBOOK_LEAD_SYNC", default=False)
ENABLE_WHATSAPP = env.bool("ENABLE_WHATSAPP", default=False)
