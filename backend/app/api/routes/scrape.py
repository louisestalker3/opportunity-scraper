"""
Scrape trigger and seed endpoints.
"""
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.app_profile import AppProfile
from app.models.mention import Mention
from app.models.opportunity import Opportunity

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/trigger/all")
async def trigger_all_scrapes():
    """Trigger all scrapers at once."""
    from app.workers.celery_app import celery_app
    tasks = [
        "app.workers.scrape_worker.scrape_reddit",
        "app.workers.scrape_worker.scrape_hackernews",
    ]
    for task in tasks:
        celery_app.send_task(task)
    return {"status": "queued", "sources": ["reddit", "hackernews"]}


@router.post("/trigger/{source}")
async def trigger_scrape(source: str):
    """Trigger a scrape task for a given source: reddit, hackernews, g2, capterra, trustpilot."""
    task_map = {
        "reddit": "app.workers.scrape_worker.scrape_reddit",
        "hackernews": "app.workers.scrape_worker.scrape_hackernews",
        "g2": "app.workers.scrape_worker.scrape_g2",
        "capterra": "app.workers.scrape_worker.scrape_capterra",
        "trustpilot": "app.workers.scrape_worker.scrape_trustpilot",
    }
    if source not in task_map:
        return {"error": f"Unknown source. Choose from: {list(task_map.keys())}"}

    from app.workers.celery_app import celery_app
    celery_app.send_task(task_map[source])
    return {"status": "queued", "source": source}


@router.post("/seed")
async def seed_demo_data(db: AsyncSession = Depends(get_db)):
    """Seed the database with demo app profiles and opportunities for UI testing."""
    now = datetime.now(timezone.utc)

    demo_apps = [
        {
            "name": "Notion",
            "url": "https://notion.so",
            "category": "Productivity / Notes",
            "description": "All-in-one workspace for notes, docs, and project management.",
            "pricing_tiers": [{"name": "Free"}, {"name": "Plus", "price": 10}, {"name": "Business", "price": 18}],
            "target_audience": "Teams and individuals managing knowledge and projects",
            "avg_review_score": 4.1,
            "total_reviews": 312,
            "pros": [
                "Extremely flexible and customisable",
                "Great for team wikis and knowledge bases",
                "Beautiful, clean interface",
                "Powerful database views (table, board, calendar)",
                "Good free tier",
            ],
            "cons": [
                "Slow on mobile, especially large pages",
                "Offline mode is unreliable",
                "Steep learning curve for new users",
                "No native time-tracking features",
                "Search is frustratingly slow",
            ],
            "viability_score": 78.0,
            "mention_count": 312,
            "complaint_count": 189,
            "alternative_seeking_count": 54,
        },
        {
            "name": "Jira",
            "url": "https://atlassian.com/jira",
            "category": "Project Management",
            "description": "Issue and project tracking for software teams.",
            "pricing_tiers": [{"name": "Free"}, {"name": "Standard", "price": 8.15}, {"name": "Premium", "price": 16}],
            "target_audience": "Software development teams",
            "avg_review_score": 3.7,
            "total_reviews": 487,
            "pros": [
                "Highly customisable workflows",
                "Excellent integrations (GitHub, Confluence, etc.)",
                "Robust reporting and dashboards",
                "Scales well to large teams",
                "Strong Agile/Scrum support",
            ],
            "cons": [
                "Extremely complex to configure and administer",
                "UI feels outdated and cluttered",
                "Too heavyweight for small teams",
                "Pricing jumps significantly at scale",
                "Slow page load times",
            ],
            "viability_score": 85.0,
            "mention_count": 487,
            "complaint_count": 301,
            "alternative_seeking_count": 112,
        },
        {
            "name": "Mailchimp",
            "url": "https://mailchimp.com",
            "category": "Email Marketing",
            "description": "Email marketing platform for small businesses.",
            "pricing_tiers": [{"name": "Free"}, {"name": "Essentials", "price": 13}, {"name": "Standard", "price": 20}],
            "target_audience": "Small businesses and marketers",
            "avg_review_score": 3.8,
            "total_reviews": 256,
            "pros": [
                "Easy drag-and-drop email builder",
                "Great template library",
                "Solid automation for basic workflows",
                "Good analytics and open rate tracking",
                "Generous free tier for small lists",
            ],
            "cons": [
                "Pricing becomes very expensive at scale",
                "Removed free automations in 2019 — still resented",
                "Deliverability issues reported frequently",
                "Customer support is slow and unhelpful",
                "Limited segmentation on lower tiers",
            ],
            "viability_score": 72.0,
            "mention_count": 256,
            "complaint_count": 162,
            "alternative_seeking_count": 67,
        },
        {
            "name": "Zapier",
            "url": "https://zapier.com",
            "category": "Workflow Automation",
            "description": "No-code automation platform connecting web apps.",
            "pricing_tiers": [{"name": "Free"}, {"name": "Starter", "price": 29.99}, {"name": "Professional", "price": 73.50}],
            "target_audience": "Non-technical users automating business workflows",
            "avg_review_score": 4.0,
            "total_reviews": 198,
            "pros": [
                "Massive library of 6000+ app integrations",
                "No coding required",
                "Very reliable task execution",
                "Great documentation and community",
                "Instant Zaps for real-time triggers",
            ],
            "cons": [
                "Extremely expensive at scale",
                "Task limits feel arbitrary and punishing",
                "Debugging failed Zaps is painful",
                "No branching logic on lower tiers",
                "Competitors like Make offer far more for less",
            ],
            "viability_score": 81.0,
            "mention_count": 198,
            "complaint_count": 134,
            "alternative_seeking_count": 78,
        },
        {
            "name": "Intercom",
            "url": "https://intercom.com",
            "category": "Customer Support / Messaging",
            "description": "Customer messaging platform for support, marketing, and sales.",
            "pricing_tiers": [{"name": "Starter", "price": 74}, {"name": "Pro", "price": "custom"}, {"name": "Premium", "price": "custom"}],
            "target_audience": "SaaS companies doing customer support",
            "avg_review_score": 3.9,
            "total_reviews": 174,
            "pros": [
                "Excellent live chat and inbox experience",
                "Powerful customer segmentation",
                "Great product tours and in-app messaging",
                "Strong integration ecosystem",
                "AI-powered ticket summaries",
            ],
            "cons": [
                "Shockingly expensive — pricing is opaque and high",
                "Seat-based pricing punishes growing teams",
                "Messenger widget slows down page load",
                "Email sending reliability has declined",
                "Support for Intercom itself is ironically poor",
            ],
            "viability_score": 88.0,
            "mention_count": 174,
            "complaint_count": 128,
            "alternative_seeking_count": 91,
        },
    ]

    created = 0
    from sqlalchemy import select

    for app_data in demo_apps:
        # Check if already exists
        result = await db.execute(select(AppProfile).where(AppProfile.name == app_data["name"]))
        if result.scalar_one_or_none():
            continue

        profile_id = uuid.uuid4()
        viability = app_data.pop("viability_score")
        mention_count = app_data.pop("mention_count")
        complaint_count = app_data.pop("complaint_count")
        alternative_seeking_count = app_data.pop("alternative_seeking_count")

        profile = AppProfile(
            id=profile_id,
            competitor_ids=[],
            first_seen=now,
            last_updated=now,
            **app_data,
        )
        db.add(profile)
        await db.flush()

        # Seed a handful of mentions
        signal_types = (
            ["complaint"] * 3 + ["alternative_seeking"] * 2 + ["praise"] * 1
        )
        for i, signal in enumerate(signal_types):
            db.add(Mention(
                id=uuid.uuid4(),
                app_profile_id=profile_id,
                source="reddit",
                source_id=f"seed_{profile_id}_{i}",
                content=f"Demo mention {i+1} for {app_data['name']}: {app_data['cons'][i % len(app_data['cons'])]}",
                url=f"https://reddit.com/r/SaaS/demo_{i}",
                sentiment="negative" if signal in ("complaint", "alternative_seeking") else "positive",
                signal_type=signal,
                confidence_score=0.85,
                app_names_mentioned=[app_data["name"]],
                raw_data={},
                scraped_at=now,
            ))

        opp = Opportunity(
            id=uuid.uuid4(),
            app_profile_id=profile_id,
            viability_score=viability,
            market_demand_score=round(viability * 0.9, 1),
            complaint_severity_score=round(complaint_count / mention_count * 100, 1),
            competition_density_score=round(viability * 0.7, 1),
            pricing_gap_score=round(viability * 0.8, 1),
            build_complexity_score=50.0,
            differentiation_score=round(viability * 0.85, 1),
            mention_count=mention_count,
            complaint_count=complaint_count,
            alternative_seeking_count=alternative_seeking_count,
            last_scored=now,
        )
        db.add(opp)
        created += 1

    await db.commit()
    return {"status": "ok", "apps_seeded": created}
