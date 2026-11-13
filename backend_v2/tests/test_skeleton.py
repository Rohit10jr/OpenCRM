import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import get_resolver

from config import celery as celery_config
from config.settings import base


APP_NAMES = [
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


def test_all_ten_apps_are_installed_in_the_decided_order():
    installed = [name for name in settings.INSTALLED_APPS if name in APP_NAMES]
    assert installed == APP_NAMES


def test_each_app_urlconf_is_explicitly_included_under_api_v1():
    includes = [
        (
            str(pattern.pattern),
            getattr(pattern.urlconf_module, "__name__", pattern.urlconf_module),
        )
        for pattern in get_resolver().url_patterns
        if hasattr(pattern, "urlconf_module")
    ]
    assert [("api/v1/", f"{name}.urls") for name in APP_NAMES] == [
        item for item in includes if item[0] == "api/v1/"
    ]


def test_beat_schedule_refuses_a_duplicate_key():
    with pytest.raises(
        ValueError, match=r"Duplicate Celery beat schedule key\(s\): same-task"
    ):
        celery_config.merge_beat_schedules(
            [{"same-task": {"task": "one"}}, {"same-task": {"task": "two"}}]
        )


def test_settings_read_backend_v2_env_only():
    backend_v2_dir = Path(__file__).resolve().parents[1]
    assert base.ENV_FILE == backend_v2_dir / ".env"
    assert base.ENV_FILE != backend_v2_dir.parent / ".env"


def test_drf_uses_json_renderer_only():
    assert settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == (
        "core.renderers.FrappeEnvelopeRenderer",
    )


def test_test_database_has_its_own_explicit_name():
    assert re.fullmatch(
        r"test_opencrm_v2(?:_gw\d+)?", settings.DATABASES["default"]["TEST"]["NAME"]
    )
