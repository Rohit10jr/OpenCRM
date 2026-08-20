"""Importing the Celery app here is what makes ``@shared_task`` bind to it.

Without this, tasks registered with ``@shared_task`` have no app when Django starts and
``CELERY_TASK_ALWAYS_EAGER`` silently does nothing in tests.
"""

from config.celery import app as celery_app

__all__ = ("celery_app",)
