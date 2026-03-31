import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.app_profile import AppProfile
from app.models.opportunity import Opportunity
from app.nlp.claude_cli import ProxyUnavailableError
from app.nlp.idea_generator import generate_ideas

router = APIRouter()


class GenerateIdeasRequest(BaseModel):
    count: int = 5
    category: str | None = None


class GeneratedIdeaResponse(BaseModel):
    opportunity_id: str
    app_profile_id: str
    name: str
    tagline: str
    category: str | None
    description: str
    viability_score: int
    market_demand_score: int
    complaint_severity_score: int
    competition_density_score: int
    pricing_gap_score: int
    build_complexity_score: int
    differentiation_score: int
    ai_rationale: str


@router.post("/generate", response_model=list[GeneratedIdeaResponse])
async def generate_app_ideas(
    body: GenerateIdeasRequest,
    db: AsyncSession = Depends(get_db),
):
    """Use AI to generate original app ideas and save them as opportunities."""
    count = max(1, min(body.count, 10))
    try:
        ideas = await generate_ideas(count=count, category=body.category)
    except ProxyUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Claude CLI unavailable — ensure 'claude' is installed and authenticated. ({exc})",
        )

    results = []
    for idea in ideas:
        # Reuse existing profile if app name already exists
        existing = await db.execute(
            select(AppProfile).where(AppProfile.name == idea.name)
        )
        app = existing.scalar_one_or_none()

        if not app:
            app = AppProfile(
                id=uuid.uuid4(),
                name=idea.name,
                url="",
                category=idea.category,
                description=idea.description,
                target_audience=idea.target_audience,
                pros=idea.pros,
                cons=idea.cons,
                source="ai_generated",
            )
            db.add(app)
            await db.flush()

        # Upsert opportunity
        existing_opp = await db.execute(
            select(Opportunity).where(Opportunity.app_profile_id == app.id)
        )
        opp = existing_opp.scalar_one_or_none()

        if not opp:
            opp = Opportunity(
                id=uuid.uuid4(),
                app_profile_id=app.id,
                viability_score=float(idea.viability_score),
                market_demand_score=float(idea.market_demand_score),
                complaint_severity_score=float(idea.complaint_severity_score),
                competition_density_score=float(idea.competition_density_score),
                pricing_gap_score=float(idea.pricing_gap_score),
                build_complexity_score=float(idea.build_complexity_score),
                differentiation_score=float(idea.differentiation_score),
                mention_count=0,
                complaint_count=0,
                alternative_seeking_count=0,
                ai_rationale=idea.ai_rationale,
                last_scored=datetime.utcnow(),
            )
            db.add(opp)
        else:
            opp.viability_score = float(idea.viability_score)
            opp.market_demand_score = float(idea.market_demand_score)
            opp.complaint_severity_score = float(idea.complaint_severity_score)
            opp.competition_density_score = float(idea.competition_density_score)
            opp.pricing_gap_score = float(idea.pricing_gap_score)
            opp.build_complexity_score = float(idea.build_complexity_score)
            opp.differentiation_score = float(idea.differentiation_score)
            opp.ai_rationale = idea.ai_rationale

        results.append(GeneratedIdeaResponse(
            opportunity_id=str(opp.id),
            app_profile_id=str(app.id),
            name=idea.name,
            tagline=idea.tagline,
            category=idea.category,
            description=idea.description,
            viability_score=idea.viability_score,
            market_demand_score=idea.market_demand_score,
            complaint_severity_score=idea.complaint_severity_score,
            competition_density_score=idea.competition_density_score,
            pricing_gap_score=idea.pricing_gap_score,
            build_complexity_score=idea.build_complexity_score,
            differentiation_score=idea.differentiation_score,
            ai_rationale=idea.ai_rationale,
        ))

    await db.commit()
    return results
