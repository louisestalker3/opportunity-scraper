"""
Celery enrichment tasks.

enrich_app_profile  - fetches/creates AppProfile, runs ReviewSummarizer, queues scoring
score_opportunity   - runs ViabilityScorer and upserts Opportunity record
enrich_pending_apps - beat-scheduled task that finds apps without recent scoring
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, func

from app.workers.celery_app import celery_app
from app.db.database import AsyncSessionLocal
from app.models.app_profile import AppProfile
from app.models.mention import Mention
from app.models.opportunity import Opportunity
from app.nlp.summarizer import ReviewSummarizer
from app.scoring.viability import ViabilityScorer

logger = logging.getLogger(__name__)


async def _run_with_cleanup(coro):
    try:
        return await coro
    finally:
        from app.db.database import engine
        await engine.dispose()


def _run_async(coro):
    return asyncio.run(_run_with_cleanup(coro))


async def _get_or_create_app_profile(app_name: str) -> AppProfile:
    """Fetch an existing AppProfile or create a new minimal one."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AppProfile).where(AppProfile.name == app_name)
        )
        profile = result.scalar_one_or_none()
        if profile:
            return profile

        profile = AppProfile(
            id=uuid.uuid4(),
            name=app_name,
            url="",
            pros=[],
            cons=[],
            pricing_tiers=[],
            competitor_ids=[],
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


async def _enrich_profile(app_profile_id: uuid.UUID) -> None:
    """Run ReviewSummarizer and update pros/cons on an AppProfile."""
    async with AsyncSessionLocal() as session:
        # Load profile
        result = await session.execute(
            select(AppProfile).where(AppProfile.id == app_profile_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            logger.warning("enrich_profile: AppProfile %s not found", app_profile_id)
            return

        # Fetch up to 200 recent mentions for this app
        mention_result = await session.execute(
            select(Mention)
            .where(Mention.app_profile_id == app_profile_id)
            .order_by(Mention.scraped_at.desc())
            .limit(200)
        )
        mentions = mention_result.scalars().all()

        # Also search by app name in app_names_mentioned JSON field
        from sqlalchemy import cast, func
        from sqlalchemy.dialects.postgresql import JSONB
        name_mention_result = await session.execute(
            select(Mention)
            .where(cast(Mention.app_names_mentioned, JSONB).contains(cast([profile.name], JSONB)))
            .order_by(Mention.scraped_at.desc())
            .limit(200)
        )
        name_mentions = name_mention_result.scalars().all()

        all_mentions = list({m.id: m for m in list(mentions) + list(name_mentions)}.values())

        texts = [m.content for m in all_mentions if m.content]

        if not texts:
            logger.info("enrich_profile: No mentions found for %s", profile.name)
            return

        summarizer = ReviewSummarizer()
        summary = await summarizer.summarize(profile.name, texts)

        profile.pros = [p for p in summary["pros"] if p]
        profile.cons = [c for c in summary["cons"] if c]
        profile.last_updated = datetime.now(timezone.utc)
        profile.total_reviews = len(all_mentions)

        # Link mentions that mention this app but don't have app_profile_id set
        for mention in name_mentions:
            if mention.app_profile_id is None:
                mention.app_profile_id = app_profile_id

        await session.commit()
        logger.info(
            "enrich_profile: Updated %s — %d pros, %d cons, %d mentions",
            profile.name, len(profile.pros), len(profile.cons), len(all_mentions)
        )


async def _score_opportunity(app_profile_id: uuid.UUID) -> None:
    """Run ViabilityScorer and upsert an Opportunity record."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AppProfile).where(AppProfile.id == app_profile_id)
        )
        profile = result.scalar_one_or_none()
        if not profile:
            logger.warning("score_opportunity: AppProfile %s not found", app_profile_id)
            return

        # Fetch all mentions for this app profile
        mention_result = await session.execute(
            select(Mention).where(Mention.app_profile_id == app_profile_id)
        )
        mentions = mention_result.scalars().all()
        mention_dicts = [
            {
                "signal_type": m.signal_type,
                "sentiment": m.sentiment,
                "confidence_score": m.confidence_score,
            }
            for m in mentions
        ]

        scorer = ViabilityScorer()
        result_obj = scorer.score(
            mentions=mention_dicts,
            competitor_ids=profile.competitor_ids or [],
            app_cons=profile.cons or [],
            pricing_tiers=profile.pricing_tiers or [],
        )

        # Upsert Opportunity
        opp_result = await session.execute(
            select(Opportunity).where(Opportunity.app_profile_id == app_profile_id)
        )
        opp = opp_result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if opp:
            opp.viability_score = result_obj.viability_score
            opp.market_demand_score = result_obj.market_demand_score
            opp.complaint_severity_score = result_obj.complaint_severity_score
            opp.competition_density_score = result_obj.competition_density_score
            opp.pricing_gap_score = result_obj.pricing_gap_score
            opp.build_complexity_score = result_obj.build_complexity_score
            opp.differentiation_score = result_obj.differentiation_score
            opp.mention_count = result_obj.mention_count
            opp.complaint_count = result_obj.complaint_count
            opp.alternative_seeking_count = result_obj.alternative_seeking_count
            opp.last_scored = now
            opp.updated_at = now
        else:
            opp = Opportunity(
                id=uuid.uuid4(),
                app_profile_id=app_profile_id,
                viability_score=result_obj.viability_score,
                market_demand_score=result_obj.market_demand_score,
                complaint_severity_score=result_obj.complaint_severity_score,
                competition_density_score=result_obj.competition_density_score,
                pricing_gap_score=result_obj.pricing_gap_score,
                build_complexity_score=result_obj.build_complexity_score,
                differentiation_score=result_obj.differentiation_score,
                mention_count=result_obj.mention_count,
                complaint_count=result_obj.complaint_count,
                alternative_seeking_count=result_obj.alternative_seeking_count,
                last_scored=now,
            )
            session.add(opp)

        await session.commit()
        logger.info(
            "score_opportunity: Scored %s — viability=%.1f",
            profile.name, result_obj.viability_score
        )


async def _enrich_app_profile_async(app_name: str) -> str:
    profile = await _get_or_create_app_profile(app_name)
    await _enrich_profile(profile.id)
    return str(profile.id)


@celery_app.task(name="app.workers.enrich_worker.enrich_app_profile", bind=True, max_retries=3)
def enrich_app_profile(self, app_name: str):
    """Fetch/create AppProfile, summarize mentions, then queue scoring."""
    logger.info("enrich_app_profile: Processing %r", app_name)
    try:
        profile_id = _run_async(_enrich_app_profile_async(app_name))
        score_opportunity.delay(profile_id)
    except Exception as exc:
        logger.error("enrich_app_profile failed for %r: %s", app_name, exc)
        raise self.retry(exc=exc, countdown=60 * 2)


@celery_app.task(name="app.workers.enrich_worker.score_opportunity", bind=True, max_retries=3)
def score_opportunity(self, app_profile_id: str):
    """Run ViabilityScorer and upsert Opportunity record."""
    logger.info("score_opportunity: Scoring app_profile_id=%s", app_profile_id)
    try:
        _run_async(_score_opportunity(uuid.UUID(app_profile_id)))
    except Exception as exc:
        logger.error("score_opportunity failed for %s: %s", app_profile_id, exc)
        raise self.retry(exc=exc, countdown=60 * 2)


async def _find_and_enrich_pending() -> None:
    """Find AppProfiles with no Opportunity or stale scores and queue enrichment."""
    stale_threshold = datetime.now(timezone.utc) - timedelta(hours=24)

    async with AsyncSessionLocal() as session:
        # Apps with no opportunity record
        subq = select(Opportunity.app_profile_id)
        result = await session.execute(
            select(AppProfile.name)
            .where(AppProfile.id.notin_(subq))
            .limit(50)
        )
        no_opp_apps = result.scalars().all()

        # Apps with stale opportunities
        stale_result = await session.execute(
            select(AppProfile.name)
            .join(Opportunity, Opportunity.app_profile_id == AppProfile.id)
            .where(Opportunity.last_scored < stale_threshold)
            .limit(50)
        )
        stale_apps = stale_result.scalars().all()

    all_apps = list(set(no_opp_apps) | set(stale_apps))
    logger.info("enrich_pending_apps: Found %d apps to process", len(all_apps))
    for name in all_apps:
        enrich_app_profile.delay(name)


@celery_app.task(name="app.workers.enrich_worker.enrich_pending_apps")
def enrich_pending_apps():
    """Beat-scheduled: find and enrich apps without recent scoring."""
    _run_async(_find_and_enrich_pending())
