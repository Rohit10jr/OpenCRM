"""Settings ACCOUNTS relies on (specs/ACCOUNTS.md section 7), as backend/ has them."""

import pytest
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


def test_password_validators_refuse_a_weak_password():
    with pytest.raises(ValidationError):
        validate_password("123")


def test_reset_link_expiry_defaults_to_an_hour():
    assert settings.PASSWORD_RESET_LINK_EXPIRY_MINUTES == 60


def test_the_test_run_has_inline_tasks_local_mail_and_no_config_account():
    assert settings.CELERY_TASK_ALWAYS_EAGER is True
    assert settings.EMAIL_BACKEND == "django.core.mail.backends.locmem.EmailBackend"
    assert settings.EMAIL_HOST == ""


def test_tasks_land_on_the_old_default_queue():
    """A worker started as the old one is (`-Q default`) receives backend_v2's tasks."""
    from config.celery import app

    assert settings.CELERY_TASK_DEFAULT_QUEUE == "default"
    assert app.conf.task_default_queue == "default"


def test_the_celery_settings_match_the_old_backend():
    """backend/config/settings/base.py:316-326 (A-26)."""
    from config.celery import app

    assert app.conf.task_acks_late is True
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert list(app.conf.accept_content) == ["json"]
    expires = app.conf.result_expires
    assert getattr(expires, "total_seconds", lambda: expires)() == 60 * 60 * 24
