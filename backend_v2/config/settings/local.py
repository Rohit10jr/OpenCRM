"""Local development settings."""

from .base import *  # noqa: F401,F403

DEBUG = True
DEV_DATA_ALLOWED = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]
