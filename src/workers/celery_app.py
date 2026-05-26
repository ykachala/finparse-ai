from celery import Celery


def create_celery(redis_url: str) -> Celery:
    celery: Celery = Celery("finparse", broker=redis_url, backend=redis_url)
    celery.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )
    celery.autodiscover_tasks(["src.workers"])
    return celery


from src.config import get_settings  # noqa: E402

celery_app = create_celery(get_settings().redis_url)
