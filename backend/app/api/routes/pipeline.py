import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.opportunity import Opportunity
from app.models.pipeline_item import PipelineItem

router = APIRouter()

VALID_STATUSES = {"watching", "considering", "building", "dropped"}


# ─── Schemas ─────────────────────────────────────────────────────────────────

class PipelineItemResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    user_session_id: str
    notes: str | None
    status: str
    created_at: Any
    updated_at: Any

    class Config:
        from_attributes = True


class CreatePipelineItemRequest(BaseModel):
    opportunity_id: uuid.UUID
    notes: str | None = None
    status: str = "watching"


class UpdatePipelineItemRequest(BaseModel):
    notes: str | None = None
    status: str | None = None


# ─── Session helper ───────────────────────────────────────────────────────────

def get_session_id(x_session_id: str | None = Header(default=None)) -> str:
    if not x_session_id:
        raise HTTPException(
            status_code=400,
            detail="X-Session-ID header is required",
        )
    return x_session_id


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[PipelineItemResponse])
async def list_pipeline(
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """List all pipeline items for the current session."""
    result = await db.execute(
        select(PipelineItem)
        .where(PipelineItem.user_session_id == session_id)
        .order_by(PipelineItem.created_at.desc())
    )
    items = result.scalars().all()
    return [PipelineItemResponse.model_validate(item) for item in items]


@router.post("", response_model=PipelineItemResponse, status_code=201)
async def add_to_pipeline(
    body: CreatePipelineItemRequest,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Add an opportunity to the pipeline."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")

    # Verify opportunity exists
    opp_result = await db.execute(
        select(Opportunity).where(Opportunity.id == body.opportunity_id)
    )
    opp = opp_result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    # Check for duplicate
    existing = await db.execute(
        select(PipelineItem).where(
            PipelineItem.user_session_id == session_id,
            PipelineItem.opportunity_id == body.opportunity_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Opportunity already in pipeline")

    item = PipelineItem(
        id=uuid.uuid4(),
        opportunity_id=body.opportunity_id,
        user_session_id=session_id,
        notes=body.notes,
        status=body.status,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return PipelineItemResponse.model_validate(item)


@router.patch("/{item_id}", response_model=PipelineItemResponse)
async def update_pipeline_item(
    item_id: uuid.UUID,
    body: UpdatePipelineItemRequest,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Update status or notes for a pipeline item."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            PipelineItem.user_session_id == session_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")
        item.status = body.status

    if body.notes is not None:
        item.notes = body.notes

    await db.commit()
    await db.refresh(item)
    return PipelineItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=204)
async def remove_from_pipeline(
    item_id: uuid.UUID,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Remove an item from the pipeline."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            PipelineItem.user_session_id == session_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    await db.delete(item)
    await db.commit()
