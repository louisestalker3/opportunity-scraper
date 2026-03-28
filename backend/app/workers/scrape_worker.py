"""
Celery scraping tasks.

Each task runs the appropriate scraper, passes results through NLP pipelines,
upserts mentions to the database, and queues app enrichment for newly detected apps.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.workers.celery_app import celery_app
from app.db.database import AsyncSessionLocal
from app.models.mention import Mention
from app.nlp.sentiment import SentimentAnalyser
from app.nlp.entity_extraction import AppNameExtractor

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _process_raw_mentions(
    raw_items: list[dict[str, Any]],
    source: str,
) -> list[str]:
    """
    Run sentiment + entity extraction on raw scraped items,
    upsert Mention records, and return list of new app names discovered.
    """
    if not raw_items:
        return []

    texts = [item["content"] for item in raw_items]

    analyser = SentimentAnalyser()
    extractor = AppNameExtractor()

    # Batch sentiment analysis
    sentiments = await analyser.analyse_many(texts)

    new_app_names: set[str] = set()

    async with AsyncSessionLocal() as session:
        for item, sent in zip(raw_items, sentiments):
            try:
                extraction = await extractor.extract(item["content"])
                app_names = extractor.high_confidence_names(extraction, threshold=0.7)
                new_app_names.update(app_names)

                mention_data = {
                    "source": source,
                    "source_id": item["source_id"],
                    "content": item["content"],
                    "url": item.get("url", ""),
                    "sentiment": sent["sentiment"],
                    "signal_type": sent["signal_type"],
                    "confidence_score": sent["confidence_score"],
                    "app_names_mentioned": app_names,
                    "raw_data": item.get("raw_data", {}),
                    "scraped_at": datetime.now(timezone.utc),
                }

                stmt = (
                    pg_insert(Mention)
                    .values(**mention_data)
                    .on_conflict_do_update(
                        constraint="uq_mention_source_source_id",
                        set_={
                            "sentiment": mention_data["sentiment"],
                            "signal_type": mention_data["signal_type"],
                            "confidence_score": mention_data["confidence_score"],
                            "app_names_mentioned": mention_data["app_names_mentioned"],
                            "scraped_at": mention_data["scraped_at"],
                        },
                    )
                )
                await session.execute(stmt)
            except Exception as exc:
                logger.warning("Failed to upsert mention source_id=%s: %s", item.get("source_id"), exc)

        await session.commit()

    return list(new_app_names)


def _queue_enrichment(app_names: list[str]) -> None:
    """Queue enrich_app_profile task for each newly discovered app."""
    from app.workers.enrich_worker import enrich_app_profile  # avoid circular
    for name in app_names:
        enrich_app_profile.delay(name)


@celery_app.task(name="app.workers.scrape_worker.scrape_reddit", bind=True, max_retries=3)
def scrape_reddit(self):
    logger.info("Starting Reddit scrape task")
    try:
        from app.scrapers.reddit import RedditScraper
        scraper = RedditScraper()
        raw = _run_async(scraper.scrape_with_retry())
        new_apps = _run_async(_process_raw_mentions(raw, "reddit"))
        _queue_enrichment(new_apps)
        logger.info("Reddit scrape done: %d items, %d new apps", len(raw), len(new_apps))
    except Exception as exc:
        logger.error("Reddit scrape task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 5)


@celery_app.task(name="app.workers.scrape_worker.scrape_hackernews", bind=True, max_retries=3)
def scrape_hackernews(self):
    logger.info("Starting Hacker News scrape task")
    try:
        from app.scrapers.hackernews import HNScraper
        scraper = HNScraper()
        raw = _run_async(scraper.scrape_with_retry())
        new_apps = _run_async(_process_raw_mentions(raw, "hackernews"))
        _queue_enrichment(new_apps)
        logger.info("HN scrape done: %d items, %d new apps", len(raw), len(new_apps))
    except Exception as exc:
        logger.error("HN scrape task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 5)


@celery_app.task(name="app.workers.scrape_worker.scrape_g2", bind=True, max_retries=2)
def scrape_g2(self):
    logger.info("Starting G2 scrape task")
    try:
        from app.scrapers.g2 import G2Scraper
        scraper = G2Scraper()
        raw = _run_async(scraper.scrape_with_retry())
        new_apps = _run_async(_process_raw_mentions(raw, "g2"))
        _queue_enrichment(new_apps)
        logger.info("G2 scrape done: %d items, %d new apps", len(raw), len(new_apps))
    except Exception as exc:
        logger.error("G2 scrape task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 10)


@celery_app.task(name="app.workers.scrape_worker.scrape_capterra", bind=True, max_retries=2)
def scrape_capterra(self):
    logger.info("Starting Capterra scrape task")
    try:
        from app.scrapers.capterra import CapterraScraper
        scraper = CapterraScraper()
        raw = _run_async(scraper.scrape_with_retry())
        new_apps = _run_async(_process_raw_mentions(raw, "capterra"))
        _queue_enrichment(new_apps)
        logger.info("Capterra scrape done: %d items, %d new apps", len(raw), len(new_apps))
    except Exception as exc:
        logger.error("Capterra scrape task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 10)


@celery_app.task(name="app.workers.scrape_worker.scrape_trustpilot", bind=True, max_retries=2)
def scrape_trustpilot(self):
    logger.info("Starting Trustpilot scrape task")
    try:
        from app.scrapers.trustpilot import TrustpilotScraper
        scraper = TrustpilotScraper()
        raw = _run_async(scraper.scrape_with_retry())
        new_apps = _run_async(_process_raw_mentions(raw, "trustpilot"))
        _queue_enrichment(new_apps)
        logger.info("Trustpilot scrape done: %d items, %d new apps", len(raw), len(new_apps))
    except Exception as exc:
        logger.error("Trustpilot scrape task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 10)


@celery_app.task(name="app.workers.scrape_worker.scrape_twitter", bind=True, max_retries=3)
def scrape_twitter(self):
    logger.info("Starting Twitter scrape task")
    try:
        from app.scrapers.twitter import TwitterScraper
        scraper = TwitterScraper()
        raw = _run_async(scraper.scrape_with_retry())
        new_apps = _run_async(_process_raw_mentions(raw, "twitter"))
        _queue_enrichment(new_apps)
        logger.info("Twitter scrape done: %d items, %d new apps", len(raw), len(new_apps))
    except Exception as exc:
        logger.error("Twitter scrape task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 5)
