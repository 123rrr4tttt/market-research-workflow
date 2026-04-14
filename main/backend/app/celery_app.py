from __future__ import annotations

from celery import Celery

from .settings.config import settings


celery_app = Celery(
    "lottery_intel",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.autodiscover_tasks(["app.services.tasks"])


