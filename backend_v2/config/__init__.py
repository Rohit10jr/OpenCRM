"""Load the Celery application when Django imports the project."""

from config.celery import app as celery_app

__all__ = ("celery_app",)
