import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.pipeline_item import PipelineItem
from app.models.project_task import ProjectTask

router = APIRouter()          # per-item: mounted at /api/pipeline/{item_id}/tasks
runner_router = APIRouter()  # global:   mounted at /api/tasks


# ─── Schemas ──────────────────────────────────────────────────────────────────

class TaskResponse(BaseModel):
    id: str
    pipeline_item_id: str
    type: str
    title: str
    description: str | None
    status: str
    priority: str
    agent_response: str | None
    retry_after: Any
    created_at: datetime
    updated_at: datetime
    completed_at: Any


class CreateTaskRequest(BaseModel):
    type: str = "feature"   # feature | bug | fix | improvement
    title: str
    description: str | None = None
    priority: str = "medium"
    status: str = "draft"


class UpdateTaskRequest(BaseModel):
    type: str | None = None
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None


class AppendOutputRequest(BaseModel):
    output: str


# Internal endpoint schema (called by build_runner)
class TaskStatusUpdateRequest(BaseModel):
    status: str
    agent_response: str | None = None
    retry_after: str | None = None   # ISO datetime string


def _task_to_response(t: ProjectTask) -> TaskResponse:
    return TaskResponse(
        id=str(t.id),
        pipeline_item_id=str(t.pipeline_item_id),
        type=t.type,
        title=t.title,
        description=t.description,
        status=t.status,
        priority=t.priority,
        agent_response=t.agent_response,
        retry_after=t.retry_after,
        created_at=t.created_at,
        updated_at=t.updated_at,
        completed_at=t.completed_at,
    )


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProjectTask)
        .where(ProjectTask.pipeline_item_id == item_id)
        .order_by(ProjectTask.created_at.asc())
    )
    return [_task_to_response(t) for t in result.scalars().all()]


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    item_id: uuid.UUID,
    body: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
):
    item_result = await db.execute(select(PipelineItem).where(PipelineItem.id == item_id))
    if not item_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    task = ProjectTask(
        id=uuid.uuid4(),
        pipeline_item_id=item_id,
        type=body.type,
        title=body.title,
        description=body.description,
        priority=body.priority,
        status=body.status,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    item_id: uuid.UUID,
    task_id: uuid.UUID,
    body: UpdateTaskRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProjectTask).where(
            ProjectTask.id == task_id,
            ProjectTask.pipeline_item_id == item_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.type is not None:
        task.type = body.type
    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.priority is not None:
        task.priority = body.priority
    if body.status is not None:
        task.status = body.status
        if body.status == "done":
            task.completed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(task)
    return _task_to_response(task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    item_id: uuid.UUID,
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProjectTask).where(
            ProjectTask.id == task_id,
            ProjectTask.pipeline_item_id == item_id,
        )
    )
    task = result.scalar_one_or_none()
    if task:
        await db.delete(task)
        await db.commit()


@router.post("/{task_id}/append-output")
async def append_task_output(
    item_id: uuid.UUID,
    task_id: uuid.UUID,
    body: AppendOutputRequest,
    db: AsyncSession = Depends(get_db),
):
    """Called by the build runner to stream output into a task."""
    result = await db.execute(
        select(ProjectTask).where(
            ProjectTask.id == task_id,
            ProjectTask.pipeline_item_id == item_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.agent_response = (task.agent_response or "") + body.output + "\n"
    await db.commit()
    return {"ok": True}


@router.post("/{task_id}/runner-update")
async def runner_update_task(
    item_id: uuid.UUID,
    task_id: uuid.UUID,
    body: TaskStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Called by the build runner to update status and optionally set retry_after."""
    result = await db.execute(
        select(ProjectTask).where(
            ProjectTask.id == task_id,
            ProjectTask.pipeline_item_id == item_id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = body.status
    if body.agent_response is not None:
        task.agent_response = (task.agent_response or "") + body.agent_response
    if body.retry_after:
        try:
            task.retry_after = datetime.fromisoformat(body.retry_after.replace("Z", "+00:00"))
        except Exception:
            pass
    if body.status == "done":
        task.completed_at = datetime.utcnow()

    await db.commit()
    return {"ok": True}


# ─── Global task-runner polling endpoints (runner_router) ────────────────────

class ReadyTaskInfo(BaseModel):
    task_id: str
    pipeline_item_id: str
    session_id: str
    title: str
    type: str
    description: str | None
    priority: str
    app_plan: str | None
    chosen_name: str | None


def _build_ready_task_info(task: ProjectTask, item: PipelineItem) -> ReadyTaskInfo:
    return ReadyTaskInfo(
        task_id=str(task.id),
        pipeline_item_id=str(task.pipeline_item_id),
        session_id=item.user_session_id,
        title=task.title,
        type=task.type,
        description=task.description,
        priority=task.priority,
        app_plan=item.app_plan,
        chosen_name=item.chosen_name,
    )


@runner_router.get("/runner/ready", response_model=list[ReadyTaskInfo])
async def get_ready_tasks(db: AsyncSession = Depends(get_db)):
    """Returns all tasks in 'ready' status across all pipeline items."""
    result = await db.execute(
        select(ProjectTask, PipelineItem)
        .join(PipelineItem, ProjectTask.pipeline_item_id == PipelineItem.id)
        .where(ProjectTask.status == "ready")
        .order_by(ProjectTask.priority.desc(), ProjectTask.created_at.asc())
    )
    return [_build_ready_task_info(t, i) for t, i in result.all()]


@runner_router.get("/runner/waiting", response_model=list[ReadyTaskInfo])
async def get_waiting_tasks(db: AsyncSession = Depends(get_db)):
    """Returns waiting_for_agent tasks whose retry_after has passed."""
    now = datetime.utcnow()
    result = await db.execute(
        select(ProjectTask, PipelineItem)
        .join(PipelineItem, ProjectTask.pipeline_item_id == PipelineItem.id)
        .where(
            ProjectTask.status == "waiting_for_agent",
            (ProjectTask.retry_after == None) | (ProjectTask.retry_after <= now),
        )
        .order_by(ProjectTask.created_at.asc())
    )
    return [_build_ready_task_info(t, i) for t, i in result.all()]


@runner_router.post("/runner/pause-project/{item_id}")
async def pause_project_tasks(item_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Pause all 'ready' tasks for a project (called when rate limit hit)."""
    result = await db.execute(
        select(ProjectTask).where(
            ProjectTask.pipeline_item_id == item_id, ProjectTask.status == "ready"
        )
    )
    for task in result.scalars().all():
        task.status = "paused"
    await db.commit()
    return {"ok": True}


@runner_router.post("/runner/resume-project/{item_id}")
async def resume_project_tasks(item_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Resume 'paused' tasks back to 'ready' (called when rate limit expires)."""
    result = await db.execute(
        select(ProjectTask).where(
            ProjectTask.pipeline_item_id == item_id, ProjectTask.status == "paused"
        )
    )
    for task in result.scalars().all():
        task.status = "ready"
    await db.commit()
    return {"ok": True}
