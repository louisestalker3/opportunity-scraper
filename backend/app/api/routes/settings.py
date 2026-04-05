"""
Settings API — persists user config (repos_path, etc.) in the DB.
Also exposes a scan endpoint that imports local git repos not yet tracked.
"""
import re
import socket
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.db.database import get_db
from app.models.app_profile import AppProfile
from app.models.opportunity import Opportunity
from app.models.pipeline_item import PipelineItem
from app.models.project_task import ProjectTask
from app.models.setting import Setting
from app.services.import_port_normalization import (
    build_app_plan_port_fields,
    detect_ports_in_repo,
    write_import_port_artifacts,
)

router = APIRouter()

# ─── Port registry helpers ────────────────────────────────────────────────────

_PORT_REGISTRY_FILE = Path(__file__).resolve().parents[4] / ".port_registry.json"
_PORT_RANGE_START = 9002
_PORT_RANGE_END   = 19999
_APP_RESERVED = {"api": 9000, "frontend": 9001}


def _load_port_registry() -> dict:
    try:
        if _PORT_REGISTRY_FILE.exists():
            import json as _json
            return _json.loads(_PORT_REGISTRY_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_port_registry(registry: dict) -> None:
    import json as _json
    _PORT_REGISTRY_FILE.write_text(_json.dumps(registry, indent=2))


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _allocate_ports_for_slug(slug: str) -> dict:
    """Return {frontend, api, db} port assignments for slug, allocating if needed."""
    registry = _load_port_registry()
    registry.setdefault("__app__", _APP_RESERVED)
    if slug in registry:
        return registry[slug]

    used: set[int] = set()
    for entry in registry.values():
        used.update(entry.values())

    def next_free() -> int:
        for p in range(_PORT_RANGE_START, _PORT_RANGE_END):
            if p not in used and _is_port_free(p):
                used.add(p)
                return p
        raise RuntimeError("No free ports")

    ports = {"frontend": next_free(), "api": next_free(), "db": next_free()}
    registry[slug] = ports
    _save_port_registry(registry)
    return ports


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_setting(db: AsyncSession, key: str, default: str | None = None) -> str | None:
    row = await db.get(Setting, key)
    return row.value if row else default


async def _set_setting(db: AsyncSession, key: str, value: str) -> None:
    row = await db.get(Setting, key)
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Setting(key=key, value=value, updated_at=datetime.now(timezone.utc)))
    await db.commit()


def _get_repos_path(override: str | None) -> Path:
    raw = override or app_settings.repos_path
    return Path(raw).expanduser().resolve()


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _git_remote(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(path), capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _git_description(path: Path) -> str | None:
    """Try to read a one-line description from README or package.json."""
    for candidate in ["README.md", "readme.md", "README.txt"]:
        f = path / candidate
        if f.exists():
            try:
                first = next(
                    (l.strip().lstrip("#").strip() for l in f.read_text(errors="replace").splitlines()
                     if l.strip() and not l.strip().startswith("![")),
                    None,
                )
                if first:
                    return first[:256]
            except Exception:
                pass
    pkg = path / "package.json"
    if pkg.exists():
        try:
            import json
            data = json.loads(pkg.read_text())
            return data.get("description") or None
        except Exception:
            pass
    return None


# ─── Schemas ─────────────────────────────────────────────────────────────────

class SettingsResponse(BaseModel):
    repos_path: str


class SettingsPatch(BaseModel):
    repos_path: str


class ScannedRepo(BaseModel):
    slug: str
    path: str
    remote: str | None
    description: str | None
    already_tracked: bool
    pipeline_item_id: str | None


class ScanResult(BaseModel):
    repos_path: str
    found: list[ScannedRepo]
    imported: int


class MigrateResult(BaseModel):
    queued: int
    already_done: int
    total: int


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    repos_path = await _get_setting(db, "repos_path", app_settings.repos_path)
    return SettingsResponse(repos_path=repos_path)


@router.patch("", response_model=SettingsResponse)
async def patch_settings(body: SettingsPatch, db: AsyncSession = Depends(get_db)):
    p = Path(body.repos_path).expanduser()
    if not p.exists():
        raise HTTPException(status_code=422, detail=f"Path does not exist: {p}")
    if not p.is_dir():
        raise HTTPException(status_code=422, detail=f"Not a directory: {p}")
    await _set_setting(db, "repos_path", str(p.resolve()))
    return SettingsResponse(repos_path=str(p.resolve()))


@router.post("/scan-repos", response_model=ScanResult)
async def scan_repos(db: AsyncSession = Depends(get_db)):
    """
    Walk the repos_path directory. For each immediate subdirectory that is a
    git repo, check whether it is already tracked as a PipelineItem. Import
    any that aren't — creating an AppProfile + Opportunity + PipelineItem
    with build_status="built" so they appear in Projects.
    """
    repos_path_str = await _get_setting(db, "repos_path", app_settings.repos_path)
    repos_path = _get_repos_path(repos_path_str)

    if not repos_path.exists():
        raise HTTPException(status_code=422, detail=f"Repos path does not exist: {repos_path}")

    # The opportunity-scraper repo itself lives here — skip it
    own_slug = "opportunity-scraper"

    # All existing pipeline items that have a local slug set in their app_plan
    existing_result = await db.execute(select(PipelineItem))
    existing_items = existing_result.scalars().all()

    # Build set of slugs already tracked
    tracked_slugs: dict[str, str] = {}  # slug → pipeline_item_id
    for item in existing_items:
        if item.app_plan:
            try:
                import json
                plan = json.loads(item.app_plan)
                slug = plan.get("slug", "")
                if slug:
                    tracked_slugs[slug] = str(item.id)
            except Exception:
                pass
        # Also track by chosen_name slug
        if item.chosen_name:
            name_slug = re.sub(r"[^a-z0-9\-]", "-", item.chosen_name.lower()).strip("-")
            tracked_slugs[name_slug] = str(item.id)

    # Also check by AppProfile name matching folder name
    app_result = await db.execute(select(AppProfile))
    existing_apps = {a.name.lower(): a for a in app_result.scalars().all()}

    now = datetime.now(timezone.utc)
    found: list[ScannedRepo] = []
    imported = 0

    # Use a stable session ID for imported items (so they appear to a known session)
    import_session = "imported"

    for entry in sorted(repos_path.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if entry.name == own_slug:
            continue
        if not _is_git_repo(entry):
            continue

        slug = entry.name
        remote = _git_remote(entry)
        description = _git_description(entry)

        # Registry ports for this slug (used for app_plan + file artifacts)
        ports = _allocate_ports_for_slug(slug)

        # Check if tracked by slug or by folder-name-as-app-name
        name_slug = re.sub(r"[^a-z0-9\-]", "-", slug.lower()).strip("-")
        item_id = tracked_slugs.get(slug) or tracked_slugs.get(name_slug)
        already_tracked = item_id is not None

        if not already_tracked:
            # Also check if AppProfile already exists for this name
            display_name = slug.replace("-", " ").replace("_", " ").title()
            if slug.lower() in existing_apps or display_name.lower() in existing_apps:
                already_tracked = True
                existing_app = existing_apps.get(slug.lower()) or existing_apps.get(display_name.lower())
                # Find the pipeline item for this app
                opp_result = await db.execute(
                    select(Opportunity).where(Opportunity.app_profile_id == existing_app.id)
                )
                opp = opp_result.scalar_one_or_none()
                if opp:
                    pi_result = await db.execute(
                        select(PipelineItem).where(PipelineItem.opportunity_id == opp.id)
                    )
                    pi = pi_result.scalars().first()
                    if pi:
                        item_id = str(pi.id)

        if not already_tracked:
            # Import it
            display_name = slug.replace("-", " ").replace("_", " ").title()

            detected = detect_ports_in_repo(entry)
            written: list[str] = []
            try:
                written = write_import_port_artifacts(entry, slug, ports, detected)
            except Exception:
                written = []

            profile = AppProfile(
                id=uuid.uuid4(),
                name=display_name,
                url=remote or "",
                category="Imported",
                description=description,
                source="imported",
                pricing_tiers=[],
                pros=[],
                cons=[],
                competitor_ids=[],
                first_seen=now,
                last_updated=now,
            )
            db.add(profile)
            await db.flush()

            opp = Opportunity(
                id=uuid.uuid4(),
                app_profile_id=profile.id,
                viability_score=None,
                market_demand_score=0.0,
                complaint_severity_score=0.0,
                competition_density_score=0.0,
                pricing_gap_score=0.0,
                build_complexity_score=0.0,
                differentiation_score=0.0,
                mention_count=0,
                complaint_count=0,
                alternative_seeking_count=0,
                last_scored=None,
                created_at=now,
                updated_at=now,
            )
            db.add(opp)
            await db.flush()

            import json
            plan = json.dumps(
                build_app_plan_port_fields(slug, display_name, ports, detected, written)
            )

            pi = PipelineItem(
                id=uuid.uuid4(),
                opportunity_id=opp.id,
                user_session_id=import_session,
                notes=f"Imported from {entry}",
                status="built",
                build_status="built",
                built_repo_url=remote or str(entry),
                app_plan=plan,
                chosen_name=display_name,
                created_at=now,
                updated_at=now,
            )
            db.add(pi)
            await db.flush()

            item_id = str(pi.id)
            imported += 1

        found.append(ScannedRepo(
            slug=slug,
            path=str(entry),
            remote=remote,
            description=description,
            already_tracked=already_tracked,
            pipeline_item_id=item_id,
        ))

    await db.commit()
    return ScanResult(repos_path=str(repos_path), found=found, imported=imported)


@router.post("/migrate-projects", response_model=MigrateResult)
async def migrate_projects(db: AsyncSession = Depends(get_db)):
    """
    For every built project that is missing a start.sh, create a migrate task
    (type="migrate", status="ready") so the build runner picks it up and
    generates native start/stop scripts.
    """
    repos_path_str = await _get_setting(db, "repos_path", app_settings.repos_path)
    repos_path = _get_repos_path(repos_path_str)

    # All built pipeline items
    result = await db.execute(
        select(PipelineItem).where(PipelineItem.build_status == "built")
    )
    items = result.scalars().all()

    queued = 0
    already_done = 0

    for item in items:
        # Resolve project slug from app_plan
        slug = ""
        if item.app_plan:
            try:
                import json
                plan = json.loads(item.app_plan)
                slug = plan.get("slug", "")
            except Exception:
                pass
        if not slug and item.chosen_name:
            import re as _re
            slug = _re.sub(r"[^a-z0-9\-]", "-", item.chosen_name.lower()).strip("-")

        if not slug:
            continue

        target_dir = repos_path / slug
        if not target_dir.exists():
            continue

        # Check if start.sh already exists
        if (target_dir / "start.sh").exists():
            already_done += 1
            continue

        # Check if there's already a pending/in-progress migrate task
        existing_result = await db.execute(
            select(ProjectTask).where(
                ProjectTask.pipeline_item_id == item.id,
                ProjectTask.type == "migrate",
                ProjectTask.status.in_(["ready", "in_progress", "waiting_for_agent", "paused"]),
            )
        )
        if existing_result.scalar_one_or_none():
            already_done += 1
            continue

        task = ProjectTask(
            id=uuid.uuid4(),
            pipeline_item_id=item.id,
            type="migrate",
            title="Migrate to native start.sh",
            description=(
                "Generate start.sh and stop.sh for native (no Docker) process management. "
                "Fix any hardcoded ports or Docker hostnames in config files."
            ),
            priority="high",
            status="ready",
        )
        db.add(task)
        queued += 1

    await db.commit()
    return MigrateResult(queued=queued, already_done=already_done, total=len(items))
