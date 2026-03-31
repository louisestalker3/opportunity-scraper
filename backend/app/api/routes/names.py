import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.name_suggestion import NameSuggestion
from app.models.pipeline_item import PipelineItem
from app.nlp.name_suggester import suggest_names

router = APIRouter()


class NameSuggestionResponse(BaseModel):
    id: str
    name: str
    tagline: str | None
    rationale: str | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class GenerateNamesRequest(BaseModel):
    count: int = 6
    hint: str | None = None  # e.g. "add Guild to the end" or "make it more playful"


class SetManualNameRequest(BaseModel):
    name: str


@router.get("", response_model=list[NameSuggestionResponse])
async def list_names(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(NameSuggestion)
        .where(NameSuggestion.pipeline_item_id == item_id)
        .order_by(NameSuggestion.created_at.desc())
    )
    return [NameSuggestionResponse(
        id=str(s.id), name=s.name, tagline=s.tagline,
        rationale=s.rationale, status=s.status, created_at=s.created_at,
    ) for s in result.scalars().all()]


@router.post("/generate", response_model=list[NameSuggestionResponse])
async def generate_names(
    item_id: uuid.UUID,
    body: GenerateNamesRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate new name suggestions for this pipeline item."""
    item_result = await db.execute(select(PipelineItem).where(PipelineItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    # Get existing suggested names to avoid repeats
    existing_result = await db.execute(
        select(NameSuggestion.name).where(NameSuggestion.pipeline_item_id == item_id)
    )
    existing_names = [r[0] for r in existing_result.all()]

    # Pull context from app_plan
    import json as _json
    plan = {}
    try:
        plan = _json.loads(item.app_plan or "{}")
    except Exception:
        pass

    # Use description/category/features to describe what the app DOES —
    # never the competitor's name, which is a trademark we can't use.
    description = plan.get("description") or plan.get("mvp_summary")
    category = plan.get("category")
    tagline = plan.get("tagline")
    features = [f.get("name", "") for f in (plan.get("features") or []) if f.get("priority") == "mvp"]

    # Pull the original competitor name from the opportunity so we can
    # explicitly tell Claude NOT to use it.
    from app.models.opportunity import Opportunity
    from app.models.app_profile import AppProfile
    competitor_name: str | None = None
    try:
        opp_result = await db.execute(
            select(AppProfile.name)
            .join(Opportunity, Opportunity.app_profile_id == AppProfile.id)
            .where(Opportunity.id == item.opportunity_id)
        )
        competitor_name = opp_result.scalar_one_or_none()
    except Exception:
        pass

    count = max(1, min(body.count, 10))
    suggestions = await suggest_names(
        description=description,
        category=category,
        tagline=tagline,
        features=features,
        count=count,
        existing_names=existing_names,
        forbidden_names=[competitor_name] if competitor_name else [],
        hint=body.hint,
    )

    created = []
    for s in suggestions:
        suggestion = NameSuggestion(
            id=uuid.uuid4(),
            pipeline_item_id=item_id,
            name=s.name,
            tagline=s.tagline,
            rationale=s.rationale,
            status="suggested",
        )
        db.add(suggestion)
        created.append(suggestion)

    await db.commit()
    for s in created:
        await db.refresh(s)

    return [NameSuggestionResponse(
        id=str(s.id), name=s.name, tagline=s.tagline,
        rationale=s.rationale, status=s.status, created_at=s.created_at,
    ) for s in created]


@router.post("/set-manual", response_model=NameSuggestionResponse)
async def set_manual_name(
    item_id: uuid.UUID,
    body: SetManualNameRequest,
    db: AsyncSession = Depends(get_db),
):
    """Directly set a manually entered name, bypassing AI suggestions."""
    item_result = await db.execute(select(PipelineItem).where(PipelineItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")

    # Reject/un-choose all existing suggestions
    all_result = await db.execute(
        select(NameSuggestion).where(
            NameSuggestion.pipeline_item_id == item_id,
            NameSuggestion.status.in_(["suggested", "chosen"]),
        )
    )
    for s in all_result.scalars().all():
        s.status = "rejected"

    suggestion = NameSuggestion(
        id=uuid.uuid4(),
        pipeline_item_id=item_id,
        name=name,
        tagline=None,
        rationale="Manually entered",
        status="chosen",
    )
    db.add(suggestion)
    item.chosen_name = name

    await db.commit()
    await db.refresh(suggestion)

    return NameSuggestionResponse(
        id=str(suggestion.id), name=suggestion.name, tagline=suggestion.tagline,
        rationale=suggestion.rationale, status=suggestion.status, created_at=suggestion.created_at,
    )


@router.post("/{name_id}/select")
async def select_name(
    item_id: uuid.UUID,
    name_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Choose a name — marks it as chosen, rejects others, saves to pipeline item."""
    item_result = await db.execute(select(PipelineItem).where(PipelineItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    name_result = await db.execute(
        select(NameSuggestion)
        .where(NameSuggestion.id == name_id, NameSuggestion.pipeline_item_id == item_id)
    )
    suggestion = name_result.scalar_one_or_none()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Name suggestion not found")

    # Mark chosen
    suggestion.status = "chosen"
    item.chosen_name = suggestion.name

    # Reject others
    all_result = await db.execute(
        select(NameSuggestion).where(
            NameSuggestion.pipeline_item_id == item_id,
            NameSuggestion.id != name_id,
            NameSuggestion.status == "suggested",
        )
    )
    for other in all_result.scalars().all():
        other.status = "rejected"

    await db.commit()
    return {"chosen_name": suggestion.name}


@router.delete("/{name_id}", status_code=204)
async def delete_name(
    item_id: uuid.UUID,
    name_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(NameSuggestion)
        .where(NameSuggestion.id == name_id, NameSuggestion.pipeline_item_id == item_id)
    )
    suggestion = result.scalar_one_or_none()
    if suggestion:
        await db.delete(suggestion)
        await db.commit()
