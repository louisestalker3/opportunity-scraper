"""Celery task that pings the status endpoint so the UI can show a live indicator."""
import logging
import os

import httpx

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_API_BASE = os.environ.get("API_BASE", "http://localhost:9000")


@celery_app.task(name="app.workers.heartbeat_worker.send_heartbeat", ignore_result=True)
def send_heartbeat():
    try:
        httpx.post(f"{_API_BASE}/api/status/heartbeat", json={"runner": "celery"}, timeout=3)
    except Exception as exc:
        logger.debug("Heartbeat failed: %s", exc)
