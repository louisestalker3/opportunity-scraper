from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "opportunity_scraper",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.scrape_worker",
        "app.workers.enrich_worker",
        "app.workers.heartbeat_worker",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)

celery_app.conf.beat_schedule = {
    # Scrape Reddit every 6 hours
    "scrape-reddit": {
        "task": "app.workers.scrape_worker.scrape_reddit",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    # Scrape Hacker News every 2 hours
    "scrape-hackernews": {
        "task": "app.workers.scrape_worker.scrape_hackernews",
        "schedule": crontab(minute=15, hour="*/2"),
    },
    # Scrape G2 every 24 hours
    "scrape-g2": {
        "task": "app.workers.scrape_worker.scrape_g2",
        "schedule": crontab(minute=30, hour=3),
    },
    # Scrape Capterra every 24 hours
    "scrape-capterra": {
        "task": "app.workers.scrape_worker.scrape_capterra",
        "schedule": crontab(minute=45, hour=3),
    },
    # Scrape Trustpilot every 24 hours
    "scrape-trustpilot": {
        "task": "app.workers.scrape_worker.scrape_trustpilot",
        "schedule": crontab(minute=0, hour=4),
    },
    # Scrape Twitter every 4 hours
    "scrape-twitter": {
        "task": "app.workers.scrape_worker.scrape_twitter",
        "schedule": crontab(minute=30, hour="*/4"),
    },
    # Enrich new apps every hour
    "enrich-new-apps": {
        "task": "app.workers.enrich_worker.enrich_pending_apps",
        "schedule": crontab(minute=0, hour="*"),
    },
    # Heartbeat — lets the UI show the celery worker as alive
    "celery-heartbeat": {
        "task": "app.workers.heartbeat_worker.send_heartbeat",
        "schedule": 10.0,  # every 10 seconds
    },
}
