import base64
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.logo_suggestion import LogoSuggestion
from app.models.pipeline_item import PipelineItem
from app.nlp.logo_generator import generate_logos

router = APIRouter()


class LogoSuggestionResponse(BaseModel):
    id: str
    concept_name: str
    description: str | None
    svg_content: str
    color_palette: dict
    style: str
    status: str
    created_at: datetime


class GenerateLogosRequest(BaseModel):
    count: int = 3


@router.get("", response_model=list[LogoSuggestionResponse])
async def list_logos(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LogoSuggestion)
        .where(LogoSuggestion.pipeline_item_id == item_id)
        .order_by(LogoSuggestion.created_at.desc())
    )
    return [
        LogoSuggestionResponse(
            id=str(s.id), concept_name=s.concept_name, description=s.description,
            svg_content=s.svg_content, color_palette=s.color_palette,
            style=s.style, status=s.status, created_at=s.created_at,
        )
        for s in result.scalars().all()
    ]


@router.post("/generate", response_model=list[LogoSuggestionResponse])
async def generate_logo_suggestions(
    item_id: uuid.UUID,
    body: GenerateLogosRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate SVG logo concepts for this pipeline item."""
    item_result = await db.execute(select(PipelineItem).where(PipelineItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    import json as _json
    plan = {}
    try:
        plan = _json.loads(item.app_plan or "{}")
    except Exception:
        pass

    app_name = item.chosen_name or plan.get("app_name", "New App")
    tagline = plan.get("tagline")
    category = plan.get("category")
    count = max(1, min(body.count, 5))

    logos = await generate_logos(app_name, tagline, category, count)

    created = []
    for logo in logos:
        suggestion = LogoSuggestion(
            id=uuid.uuid4(),
            pipeline_item_id=item_id,
            concept_name=logo.concept_name,
            description=logo.description,
            svg_content=logo.svg_content,
            color_palette=logo.color_palette,
            style=logo.style,
            status="suggested",
        )
        db.add(suggestion)
        created.append(suggestion)

    await db.commit()
    for s in created:
        await db.refresh(s)

    return [
        LogoSuggestionResponse(
            id=str(s.id), concept_name=s.concept_name, description=s.description,
            svg_content=s.svg_content, color_palette=s.color_palette,
            style=s.style, status=s.status, created_at=s.created_at,
        )
        for s in created
    ]


_ALLOWED_EXTENSIONS = {".svg", ".png", ".jpg", ".jpeg", ".webp"}
_MAX_SIZE = 5 * 1024 * 1024  # 5 MB


@router.post("/upload", response_model=LogoSuggestionResponse)
async def upload_logo(
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a custom logo image (SVG, PNG, JPEG, or WebP)."""
    item_result = await db.execute(select(PipelineItem).where(PipelineItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"Unsupported file type. Allowed: SVG, PNG, JPEG, WebP")

    content = await file.read()
    if len(content) > _MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")

    is_svg = ext == ".svg"
    if is_svg:
        try:
            svg_content = content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=422, detail="Invalid SVG file")
    else:
        content_type = file.content_type or ""
        if not content_type or content_type == "application/octet-stream":
            content_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(ext, "image/png")
        b64 = base64.b64encode(content).decode()
        svg_content = f'<img src="data:{content_type};base64,{b64}" style="max-height:60px;max-width:200px;object-fit:contain;" />'

    # Un-choose any existing chosen logos
    chosen_result = await db.execute(
        select(LogoSuggestion).where(
            LogoSuggestion.pipeline_item_id == item_id,
            LogoSuggestion.status == "chosen",
        )
    )
    for other in chosen_result.scalars().all():
        other.status = "suggested"

    concept_name = filename.rsplit(".", 1)[0] if "." in filename else filename or "Uploaded Logo"
    palette = {"primary": "#000000", "secondary": "#ffffff", "accent": "#666666"}

    suggestion = LogoSuggestion(
        id=uuid.uuid4(),
        pipeline_item_id=item_id,
        concept_name=concept_name,
        description="Manually uploaded logo",
        svg_content=svg_content,
        color_palette=palette,
        style="custom",
        status="chosen",
    )
    db.add(suggestion)
    item.chosen_logo_svg = svg_content
    item.chosen_logo_colors = palette

    await db.commit()
    await db.refresh(suggestion)

    return LogoSuggestionResponse(
        id=str(suggestion.id), concept_name=suggestion.concept_name,
        description=suggestion.description, svg_content=suggestion.svg_content,
        color_palette=suggestion.color_palette, style=suggestion.style,
        status=suggestion.status, created_at=suggestion.created_at,
    )


@router.post("/{logo_id}/select")
async def select_logo(
    item_id: uuid.UUID,
    logo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Choose a logo and save it to the pipeline item."""
    item_result = await db.execute(select(PipelineItem).where(PipelineItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    logo_result = await db.execute(
        select(LogoSuggestion)
        .where(LogoSuggestion.id == logo_id, LogoSuggestion.pipeline_item_id == item_id)
    )
    logo = logo_result.scalar_one_or_none()
    if not logo:
        raise HTTPException(status_code=404, detail="Logo suggestion not found")

    logo.status = "chosen"
    item.chosen_logo_svg = logo.svg_content
    item.chosen_logo_colors = logo.color_palette

    # Deselect others
    all_result = await db.execute(
        select(LogoSuggestion).where(
            LogoSuggestion.pipeline_item_id == item_id,
            LogoSuggestion.id != logo_id,
            LogoSuggestion.status == "chosen",
        )
    )
    for other in all_result.scalars().all():
        other.status = "suggested"

    await db.commit()
    return {"chosen_logo": logo.concept_name, "color_palette": logo.color_palette}


@router.delete("/{logo_id}", status_code=204)
async def delete_logo(
    item_id: uuid.UUID,
    logo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LogoSuggestion)
        .where(LogoSuggestion.id == logo_id, LogoSuggestion.pipeline_item_id == item_id)
    )
    logo = result.scalar_one_or_none()
    if logo:
        await db.delete(logo)
        await db.commit()
