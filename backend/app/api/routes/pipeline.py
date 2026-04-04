import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models.app_profile import AppProfile
from app.models.opportunity import Opportunity
from app.models.pipeline_item import PipelineItem
from app.nlp.app_plan_generator import generate_app_plan
from app.nlp.proposal_generator import generate_proposal

# File shared with build_runner.py — stores active session IDs so the runner
# can poll the right pipeline items. Lives next to build_runner.py in the repo root.
_SESSIONS_FILE = Path(__file__).resolve().parents[4] / ".build_sessions"

router = APIRouter()

VALID_STATUSES = {"watching", "considering", "building", "built", "dropped"}


# ─── Schemas ─────────────────────────────────────────────────────────────────

class PipelineItemResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    user_session_id: str
    notes: str | None
    proposal: str | None
    app_plan: str | None
    status: str
    build_status: str | None
    built_repo_url: str | None
    build_log: str | None
    run_status: str | None
    run_url: str | None
    chosen_name: str | None = None
    chosen_logo_svg: str | None = None
    chosen_logo_colors: dict | None = None
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
        raise HTTPException(status_code=400, detail="X-Session-ID header is required")
    return x_session_id


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[PipelineItemResponse])
async def list_pipeline(
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PipelineItem)
        .where(
            (PipelineItem.user_session_id == session_id)
            | (PipelineItem.user_session_id == "imported")
        )
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
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status: {VALID_STATUSES}")

    opp_result = await db.execute(
        select(Opportunity).where(Opportunity.id == body.opportunity_id)
    )
    opp = opp_result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    existing = await db.execute(
        select(PipelineItem).where(
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
            PipelineItem.opportunity_id == body.opportunity_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Opportunity already in pipeline")

    profile_result = await db.execute(
        select(AppProfile).where(AppProfile.id == opp.app_profile_id)
    )
    profile = profile_result.scalar_one_or_none()

    # Generate proposal and app plan in parallel
    proposal, app_plan = await _generate_proposal_and_plan(opp, profile)

    item = PipelineItem(
        id=uuid.uuid4(),
        opportunity_id=body.opportunity_id,
        user_session_id=session_id,
        notes=body.notes,
        status=body.status,
        proposal=proposal,
        app_plan=app_plan,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return PipelineItemResponse.model_validate(item)


@router.post("/{item_id}/regenerate", response_model=PipelineItemResponse)
async def regenerate_plan_and_proposal(
    item_id: uuid.UUID,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Re-generate the proposal and app plan from scratch, resetting build state."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    opp_result = await db.execute(
        select(Opportunity).where(Opportunity.id == item.opportunity_id)
    )
    opp = opp_result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    profile_result = await db.execute(
        select(AppProfile).where(AppProfile.id == opp.app_profile_id)
    )
    profile = profile_result.scalar_one_or_none()

    proposal, app_plan = await _generate_proposal_and_plan(opp, profile)

    item.proposal = proposal
    item.app_plan = app_plan
    item.build_status = None
    item.built_repo_url = None

    await db.commit()
    await db.refresh(item)
    return PipelineItemResponse.model_validate(item)


@router.post("/{item_id}/build", status_code=202)
async def trigger_build(
    item_id: uuid.UUID,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Mark item as building — the local build_runner.py picks it up and does the work."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")
    if not item.app_plan:
        raise HTTPException(status_code=422, detail="No app plan — save the opportunity first")
    if item.build_status == "building":
        raise HTTPException(status_code=409, detail="Build already in progress")
    if item.build_status == "built":
        raise HTTPException(status_code=409, detail="Already built")

    item.build_status = "building"
    item.status = "building"
    item.build_log = None
    await db.commit()

    # Record session ID so build_runner.py (running on the host) can poll the pipeline
    try:
        _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = set(_SESSIONS_FILE.read_text().splitlines()) if _SESSIONS_FILE.exists() else set()
        existing.add(session_id)
        _SESSIONS_FILE.write_text("\n".join(existing) + "\n")
    except Exception:
        pass

    return {"status": "building", "item_id": str(item_id)}


class BuildLogRequest(BaseModel):
    message: str


@router.post("/{item_id}/build-log", status_code=204)
async def append_build_log(
    item_id: uuid.UUID,
    body: BuildLogRequest,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Append a progress line to the build log. Called by build_runner.py."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    existing = item.build_log or ""
    item.build_log = existing + body.message + "\n"
    await db.commit()


class BuildResultRequest(BaseModel):
    build_status: str  # "built" or "failed"
    built_repo_url: str | None = None


@router.post("/{item_id}/build-result", response_model=PipelineItemResponse)
async def set_build_result(
    item_id: uuid.UUID,
    body: BuildResultRequest,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Called by the host-side build_runner.py to record the build outcome."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    item.build_status = body.build_status
    if body.build_status == "built":
        item.status = "built"
        if body.built_repo_url:
            item.built_repo_url = body.built_repo_url
    elif body.build_status == "failed":
        item.status = "considering"  # move back so it's not stuck in "building"
    await db.commit()
    await db.refresh(item)
    return PipelineItemResponse.model_validate(item)


_PORT_REGISTRY_FILE = Path(__file__).resolve().parents[4] / ".port_registry.json"


def _read_port_registry() -> dict:
    try:
        if _PORT_REGISTRY_FILE.exists():
            return json.loads(_PORT_REGISTRY_FILE.read_text())
    except Exception:
        pass
    return {}


@router.get("/{item_id}/ports")
async def get_project_ports(
    item_id: uuid.UUID,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Return the registry-allocated ports for a project."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    try:
        plan = json.loads(item.app_plan or "{}")
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid app plan")

    slug = re.sub(r"[^a-z0-9\-]", "", plan.get("slug", "")).lower()
    registry = _read_port_registry()
    port_entry = registry.get(slug, {})
    # Format as {service: [{host, container}]} to keep the existing client interface
    ports = {k: [{"host": v, "container": v}] for k, v in port_entry.items()}
    return {"slug": slug, "ports": ports}


@router.get("/{item_id}/services")
async def get_project_services(
    item_id: uuid.UUID,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Return service names and allocated ports for a project from the registry."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    try:
        plan = json.loads(item.app_plan or "{}")
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid app plan")

    slug = re.sub(r"[^a-z0-9\-]", "", plan.get("slug", "")).lower()
    registry = _read_port_registry()
    port_entry = registry.get(slug, {})

    # Detect actual services from project structure rather than blindly returning
    # all three allocated ports (frontend/api/db).
    project_dir = Path(settings.repos_path) / slug
    pids_dir    = project_dir / ".pids"

    # If .pids/ exists, use running pid files as the ground truth
    if pids_dir.exists():
        pid_names = {f.stem for f in pids_dir.glob("*.pid")}  # e.g. {"app", "vite", "api"}
    else:
        pid_names = set()

    # Map pid names → canonical service names → ports
    _pid_to_service = {
        "app":      "frontend",
        "frontend": "frontend",
        "web":      "frontend",
        "api":      "api",
        "backend":  "api",
        "vite":     "frontend",
        "db":       "db",
        "database": "db",
    }

    # Determine which services actually exist by checking:
    # 1. If .pids/ has files, use those
    # 2. Otherwise, infer from directory/file structure
    if pid_names:
        seen = set()
        active_services: list[str] = []
        for pid in pid_names:
            svc = _pid_to_service.get(pid, pid)
            if svc not in seen:
                seen.add(svc)
                active_services.append(svc)
    else:
        # Fall back to inspecting the project directory
        has_frontend_dir = (project_dir / "frontend").is_dir()
        has_backend_dir  = (project_dir / "backend").is_dir()
        has_artisan      = (project_dir / "artisan").exists()
        has_pkg          = (project_dir / "package.json").exists()
        has_composer     = (project_dir / "composer.json").exists()
        has_app_py       = (project_dir / "app.py").exists()
        has_requirements = (project_dir / "requirements.txt").exists() or (project_dir / "backend" / "requirements.txt").exists()

        active_services = []
        if has_frontend_dir or has_pkg or has_artisan or has_composer or has_app_py:
            active_services.append("frontend")
        if has_backend_dir and has_requirements:
            active_services.append("api")
        # Include db for anything with a real backend or a Laravel/PHP app
        if "api" in active_services or has_artisan or has_composer:
            active_services.append("db")

    # Port lookup: frontend port for "frontend", api port for "api", db for "db"
    _svc_port_key = {"frontend": "frontend", "api": "api", "db": "db"}
    services = []
    for svc in active_services:
        port_key = _svc_port_key.get(svc, "frontend")
        port = port_entry.get(port_key)
        if port:
            services.append({"name": svc, "ports": [{"host": port, "container": port}]})

    return {"slug": slug, "services": services}


@router.get("/{item_id}/logs/{service}")
async def get_service_logs(
    item_id: uuid.UUID,
    service: str,
    tail: int = 200,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Return recent log lines from the project's .logs/{service}.log file."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    if not re.match(r'^[a-zA-Z0-9_-]+$', service):
        raise HTTPException(status_code=422, detail="Invalid service name")

    try:
        plan = json.loads(item.app_plan or "{}")
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid app plan")

    slug = re.sub(r"[^a-z0-9\-]", "", plan.get("slug", "")).lower()
    logs_dir = Path(settings.repos_path) / slug / ".logs"

    # Try the exact name first, then common aliases for single-process apps
    _aliases = {
        "frontend": ["frontend", "app", "web"],
        "api":      ["api", "app", "backend", "server"],
        "db":       ["db", "database"],
    }
    candidates = _aliases.get(service, [service]) + ["app"]
    log_file = next(
        (logs_dir / f"{c}.log" for c in candidates if (logs_dir / f"{c}.log").exists()),
        logs_dir / f"{service}.log",  # fallback to original (will show not-found message)
    )

    if not log_file.exists():
        return {"service": service, "lines": [f"[no log file at {log_file}]"]}

    try:
        all_lines = log_file.read_text(errors="replace").splitlines()
        lines = all_lines[-tail:] if len(all_lines) > tail else all_lines
    except Exception as e:
        lines = [f"[error reading log: {e}]"]

    return {"service": service, "lines": lines}


@router.post("/{item_id}/force-stop", status_code=202)
async def force_stop_project(
    item_id: uuid.UUID,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Kill all PIDs in the project's .pids/ directory."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    try:
        plan = json.loads(item.app_plan or "{}")
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid app plan")

    slug = re.sub(r"[^a-z0-9\-]", "", plan.get("slug", "")).lower()
    pids_dir = Path(settings.repos_path) / slug / ".pids"

    if pids_dir.exists():
        import signal as _signal
        for pid_file in pids_dir.glob("*.pid"):
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, _signal.SIGKILL)
            except Exception:
                pass

    item.run_status = "stopped"
    item.run_url = None
    await db.commit()
    return {"status": "stopped", "item_id": str(item_id)}


def _parse_compose_services(compose_text: str) -> list[str]:
    """Legacy helper kept for any existing callers."""
    services = []
    in_services_block = False
    for line in compose_text.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if line.strip() == "services:":
            in_services_block = True
            continue
        if in_services_block:
            if indent == 0 and stripped and not stripped.startswith("#"):
                break  # left services block
            if indent == 2 and stripped and not stripped.startswith("#") and stripped.endswith(":"):
                svc = stripped.rstrip(":")
                if svc not in ("volumes", "networks"):
                    services.append(svc)
    return services


@router.post("/{item_id}/start", status_code=202)
async def start_project(
    item_id: uuid.UUID,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Mark item as starting — build_runner.py runs docker compose up -d."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")
    if item.build_status != "built":
        raise HTTPException(status_code=422, detail="App must be built before it can be started")
    if item.run_status in ("starting", "running"):
        raise HTTPException(status_code=409, detail="Already running or starting")

    item.run_status = "starting"
    item.run_url = None

    # Clear stale log files so the UI shows a fresh slate on next run
    try:
        slug = re.sub(r"[^a-z0-9\-]", "", json.loads(item.app_plan or "{}").get("slug", ""))
        if slug:
            logs_dir = Path(settings.repos_path) / slug / ".logs"
            if logs_dir.exists():
                for f in logs_dir.glob("*.log"):
                    f.unlink(missing_ok=True)
    except Exception:
        pass

    await db.commit()
    return {"status": "starting", "item_id": str(item_id)}


@router.post("/{item_id}/stop", status_code=202)
async def stop_project(
    item_id: uuid.UUID,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Mark item as stopping — build_runner.py runs docker compose down."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")
    if item.run_status not in ("running", "starting"):
        raise HTTPException(status_code=409, detail="Not currently running")

    item.run_status = "stopping"
    await db.commit()
    return {"status": "stopping", "item_id": str(item_id)}


class RunResultRequest(BaseModel):
    run_status: str  # "running" | "stopped" | "failed"
    run_url: str | None = None


@router.post("/{item_id}/run-result", response_model=PipelineItemResponse)
async def set_run_result(
    item_id: uuid.UUID,
    body: RunResultRequest,
    session_id: str = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
):
    """Called by the host-side build_runner.py to record the run outcome."""
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    item.run_status = body.run_status
    if body.run_url:
        item.run_url = body.run_url
    elif body.run_status in ("stopped", "failed"):
        item.run_url = None
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
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status: {VALID_STATUSES}")
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
    result = await db.execute(
        select(PipelineItem).where(
            PipelineItem.id == item_id,
            ((PipelineItem.user_session_id == session_id) | (PipelineItem.user_session_id == "imported")),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Pipeline item not found")

    await db.delete(item)
    await db.commit()


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _generate_proposal_and_plan(opp: Opportunity, profile: AppProfile | None):
    import asyncio
    proposal_coro = generate_proposal(
        app_name=profile.name if profile else "Unknown",
        category=profile.category if profile else None,
        description=profile.description if profile else None,
        pros=profile.pros if profile else [],
        cons=profile.cons if profile else [],
        pricing_tiers=profile.pricing_tiers if profile else [],
        target_audience=profile.target_audience if profile else None,
        viability_score=opp.viability_score,
        complaint_severity=opp.complaint_severity_score,
        mention_count=opp.mention_count,
        alternative_seeking_count=opp.alternative_seeking_count,
    )
    plan_coro = generate_app_plan(
        app_name=profile.name if profile else "Unknown",
        category=profile.category if profile else None,
        description=profile.description if profile else None,
        pros=profile.pros if profile else [],
        cons=profile.cons if profile else [],
        target_audience=profile.target_audience if profile else None,
        viability_score=opp.viability_score,
        mention_count=opp.mention_count,
        alternative_seeking_count=opp.alternative_seeking_count,
    )
    return await asyncio.gather(proposal_coro, plan_coro)
