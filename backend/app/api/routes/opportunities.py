import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.app_profile import AppProfile
from app.models.mention import Mention
from app.models.opportunity import Opportunity

router = APIRouter()


# ─── Response schemas ────────────────────────────────────────────────────────

class AppProfileSummary(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    category: str | None
    description: str | None
    avg_review_score: float | None
    total_reviews: int
    pros: list[str]
    cons: list[str]

    class Config:
        from_attributes = True


class OpportunityResponse(BaseModel):
    id: uuid.UUID
    app_profile_id: uuid.UUID
    viability_score: float | None
    market_demand_score: float
    complaint_severity_score: float
    competition_density_score: float
    pricing_gap_score: float
    build_complexity_score: float
    differentiation_score: float
    mention_count: int
    complaint_count: int
    alternative_seeking_count: int
    app_profile: AppProfileSummary | None = None

    class Config:
        from_attributes = True


class MentionResponse(BaseModel):
    id: uuid.UUID
    source: str
    content: str
    url: str
    sentiment: str
    signal_type: str
    confidence_score: float
    scraped_at: Any

    class Config:
        from_attributes = True


class OpportunityDetailResponse(OpportunityResponse):
    recent_mentions: list[MentionResponse] = []


class PaginatedOpportunities(BaseModel):
    items: list[OpportunityResponse]
    total: int
    page: int
    page_size: int


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedOpportunities)
async def list_opportunities(
    category: str | None = Query(None),
    min_score: float = Query(0.0, ge=0, le=100),
    max_competition: float | None = Query(None, ge=0, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all opportunities sorted by viability score descending."""
    query = (
        select(Opportunity)
        .join(AppProfile, Opportunity.app_profile_id == AppProfile.id)
        .options(selectinload(Opportunity.app_profile))
        .where(Opportunity.viability_score >= min_score)
        .order_by(Opportunity.viability_score.desc().nullslast())
    )

    if category:
        query = query.where(AppProfile.category == category)

    if max_competition is not None:
        query = query.where(Opportunity.competition_density_score >= (100 - max_competition))

    # Total count
    count_result = await db.execute(select(Opportunity).where(Opportunity.viability_score >= min_score))
    total = len(count_result.scalars().all())

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return PaginatedOpportunities(
        items=[OpportunityResponse.model_validate(o) for o in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse)
async def get_opportunity(
    opportunity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single opportunity with full app profile and recent mentions."""
    result = await db.execute(
        select(Opportunity)
        .options(selectinload(Opportunity.app_profile))
        .where(Opportunity.id == opportunity_id)
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Fetch recent mentions
    mention_result = await db.execute(
        select(Mention)
        .where(Mention.app_profile_id == opp.app_profile_id)
        .order_by(Mention.scraped_at.desc())
        .limit(30)
    )
    mentions = mention_result.scalars().all()

    detail = OpportunityDetailResponse.model_validate(opp)
    detail.recent_mentions = [MentionResponse.model_validate(m) for m in mentions]
    return detail


@router.post("/{opportunity_id}/trigger-rescore")
async def trigger_rescore(opportunity_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Queue a rescore job for an opportunity."""
    result = await db.execute(
        select(Opportunity).where(Opportunity.id == opportunity_id)
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    from app.workers.enrich_worker import score_opportunity
    score_opportunity.delay(str(opp.app_profile_id))

    return {"status": "queued", "opportunity_id": str(opportunity_id)}
