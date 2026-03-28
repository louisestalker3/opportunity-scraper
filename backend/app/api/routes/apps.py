import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.app_profile import AppProfile
from app.models.mention import Mention

router = APIRouter()


class AppProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    category: str | None
    description: str | None
    pricing_tiers: list
    target_audience: str | None
    avg_review_score: float | None
    total_reviews: int
    pros: list[str]
    cons: list[str]
    competitor_ids: list
    first_seen: Any
    last_updated: Any

    class Config:
        from_attributes = True


class MentionSummary(BaseModel):
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


class AppProfileDetailResponse(AppProfileResponse):
    recent_mentions: list[MentionSummary] = []
    competitors: list[AppProfileResponse] = []


@router.get("", response_model=list[AppProfileResponse])
async def list_apps(
    category: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all app profiles with optional filtering."""
    query = select(AppProfile).order_by(AppProfile.name)

    if category:
        query = query.where(AppProfile.category == category)

    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                AppProfile.name.ilike(pattern),
                AppProfile.description.ilike(pattern),
                AppProfile.target_audience.ilike(pattern),
            )
        )

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    apps = result.scalars().all()
    return [AppProfileResponse.model_validate(a) for a in apps]


@router.get("/{app_id}", response_model=AppProfileDetailResponse)
async def get_app(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a full app profile with mentions and competitor profiles."""
    result = await db.execute(select(AppProfile).where(AppProfile.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="App profile not found")

    # Recent mentions
    mention_result = await db.execute(
        select(Mention)
        .where(Mention.app_profile_id == app_id)
        .order_by(Mention.scraped_at.desc())
        .limit(50)
    )
    mentions = mention_result.scalars().all()

    # Competitor profiles
    competitors = []
    if app.competitor_ids:
        try:
            competitor_uuids = [uuid.UUID(str(cid)) for cid in app.competitor_ids]
            comp_result = await db.execute(
                select(AppProfile).where(AppProfile.id.in_(competitor_uuids))
            )
            competitors = comp_result.scalars().all()
        except (ValueError, TypeError):
            pass

    detail = AppProfileDetailResponse.model_validate(app)
    detail.recent_mentions = [MentionSummary.model_validate(m) for m in mentions]
    detail.competitors = [AppProfileResponse.model_validate(c) for c in competitors]
    return detail
