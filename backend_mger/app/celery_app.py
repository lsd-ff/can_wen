from __future__ import annotations

from celery import Celery

from app.config import get_settings


settings = get_settings()

celery_app = Celery(
    "canw-admin",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.knowledge.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_task_always_eager,
)
