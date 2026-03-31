"""
Builds a real working application from an app plan JSON.
- Creates a directory under repos_path
- Uses Claude in two passes (backend, then frontend) to generate working code
- Runs git init + gh repo create (private) + push
- Updates pipeline_item build_status in DB
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import uuid
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.models.pipeline_item import PipelineItem

logger = logging.getLogger(__name__)

# ─── Prompts ─────────────────────────────────────────────────────────────────

BACKEND_SYSTEM = """You are a senior Python backend developer. Generate a complete, working FastAPI backend.

Return ONLY valid JSON — no markdown fences, no prose. Schema:
{"files": [{"path": "relative/path", "content": "full file content"}]}

Required files:
- backend/Dockerfile
- backend/requirements.txt  (fastapi, uvicorn[standard], sqlalchemy[asyncio], alembic, asyncpg, psycopg2-binary, python-dotenv, pydantic-settings, passlib[bcrypt], python-jose[cryptography])
- backend/alembic.ini
- backend/app/__init__.py
- backend/app/config.py  (pydantic-settings: DATABASE_URL, SECRET_KEY, ENVIRONMENT)
- backend/app/main.py  (FastAPI with CORS, /health endpoint, all routers included)
- backend/app/database.py  (async SQLAlchemy engine, Base, get_db)
- backend/app/models/__init__.py  (imports all models)
- backend/app/models/user.py  (if auth is needed — email, hashed_password, created_at)
- One model per core MVP feature (e.g. models/item.py)
- backend/app/schemas/__init__.py
- backend/app/schemas/  (Pydantic schemas for each model — Create, Update, Response)
- backend/app/routes/__init__.py
- backend/app/routes/  (one router file per feature with full CRUD endpoints)
- backend/app/migrations/env.py  (Alembic async env)
- backend/app/migrations/versions/.gitkeep

Rules:
- ALL code must be complete and runnable — no "# TODO", no "pass" bodies, no stub functions
- Use async/await throughout
- Each router must have working GET (list + detail), POST, PATCH, DELETE
- Use proper HTTP status codes and error handling
- Escape all double-quotes inside JSON string values with backslash"""

FRONTEND_SYSTEM = """You are a senior React/TypeScript developer. Generate a complete, working React frontend.

Return ONLY valid JSON — no markdown fences, no prose. Schema:
{"files": [{"path": "relative/path", "content": "full file content"}]}

Required files:
- frontend/Dockerfile
- frontend/package.json  (react, react-dom, react-router-dom, @tanstack/react-query, axios, lucide-react, tailwindcss, vite, typescript — exact versions)
- frontend/vite.config.ts
- frontend/tsconfig.json
- frontend/tsconfig.node.json
- frontend/index.html
- frontend/tailwind.config.js
- frontend/postcss.config.js
- frontend/src/main.tsx
- frontend/src/App.tsx  (React Router setup with all routes)
- frontend/src/index.css  (@tailwind directives)
- frontend/src/api/client.ts  (axios instance + all API functions matching the backend routes)
- frontend/src/hooks/  (TanStack Query hooks for each resource)
- frontend/src/pages/  (one page component per route — full working UI with forms, lists, detail views)
- frontend/src/components/  (shared components: Layout, Navbar, LoadingSpinner, ErrorBoundary)

Rules:
- ALL code must be complete and working — real UI, not placeholder divs
- Every page must connect to the API via the hooks
- Forms must have validation and error display
- Use Tailwind for all styling — clean, professional look
- Escape all double-quotes inside JSON string values with backslash"""

INFRA_SYSTEM = """You are a DevOps engineer. Generate project infrastructure files.

Return ONLY valid JSON — no markdown fences, no prose. Schema:
{"files": [{"path": "relative/path", "content": "full file content"}]}

Required files:
- docker-compose.yml  (api, frontend, db:postgres:15-alpine, redis if needed — with healthchecks)
- .env.example  (all required env vars with sensible defaults or blank values)
- .gitignore  (Python, Node, Docker, .env, __pycache__, node_modules, dist, .DS_Store)
- README.md  (project description, features, tech stack, local setup, API overview)

Rules:
- docker-compose.yml must be fully working — correct port mappings, volumes, depends_on, env vars
- README setup instructions must work: clone → cp .env.example .env → docker compose up --build → app is running
- Escape all double-quotes inside JSON string values with backslash"""


# ─── Main build task ─────────────────────────────────────────────────────────

async def build_app(pipeline_item_id: str) -> None:
    """Background task — builds the app and updates the DB."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(PipelineItem).where(PipelineItem.id == uuid.UUID(pipeline_item_id))
            )
            item = result.scalar_one_or_none()
            if not item or not item.app_plan:
                logger.error("Build: pipeline item %s not found or has no plan", pipeline_item_id)
                return

            plan = json.loads(item.app_plan)
            slug = re.sub(r"[^a-z0-9\-]", "", plan.get("slug", "new-app").lower())[:64] or "new-app"
            target_dir = Path(settings.repos_path) / slug

            # Generate all files (3 Claude passes in parallel)
            all_files = await _generate_all_files(plan)
            if not all_files:
                item.build_status = "failed"
                await db.commit()
                return

            # Write to disk
            target_dir.mkdir(parents=True, exist_ok=True)
            for file_obj in all_files:
                file_path = target_dir / file_obj["path"]
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(file_obj["content"], encoding="utf-8")

            logger.info("Wrote %d files to %s", len(all_files), target_dir)

            # Git + GitHub (private)
            repo_url = await _git_push(target_dir, slug, plan.get("app_name", slug))

            item.build_status = "built"
            item.built_repo_url = repo_url
            await db.commit()
            logger.info("Build complete for %s → %s", slug, repo_url)

        except Exception as exc:
            logger.error("Build failed for %s: %s", pipeline_item_id, exc, exc_info=True)
            try:
                result = await db.execute(
                    select(PipelineItem).where(PipelineItem.id == uuid.UUID(pipeline_item_id))
                )
                item = result.scalar_one_or_none()
                if item:
                    item.build_status = "failed"
                    await db.commit()
            except Exception:
                pass


# ─── File generation ─────────────────────────────────────────────────────────

async def _generate_all_files(plan: dict) -> list[dict]:
    if not settings.anthropic_api_key:
        logger.warning("No ANTHROPIC_API_KEY — using minimal scaffold")
        return _minimal_scaffold(plan)

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    plan_json = json.dumps(plan, indent=2)

    # Run all three passes concurrently
    backend_task = _claude_pass(client, BACKEND_SYSTEM, f"Build the backend for this app:\n\n{plan_json}")
    frontend_task = _claude_pass(client, FRONTEND_SYSTEM, f"Build the frontend for this app:\n\n{plan_json}")
    infra_task = _claude_pass(client, INFRA_SYSTEM, f"Build the infrastructure files for this app:\n\n{plan_json}")

    results = await asyncio.gather(backend_task, frontend_task, infra_task, return_exceptions=True)

    all_files: list[dict] = []
    pass_names = ["backend", "frontend", "infra"]
    for name, result in zip(pass_names, results):
        if isinstance(result, Exception):
            logger.error("Claude %s pass failed: %s", name, result)
        elif result:
            logger.info("Claude %s pass: %d files", name, len(result))
            all_files.extend(result)

    if not all_files:
        return _minimal_scaffold(plan)

    return all_files


async def _claude_pass(client, system: str, prompt: str) -> list[dict]:
    """Single Claude generation pass. Returns list of file dicts."""
    message = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    return data.get("files", [])


def _minimal_scaffold(plan: dict) -> list[dict]:
    """Fallback when no API key — creates enough to push."""
    app_name = plan.get("app_name", "New App")
    tagline = plan.get("tagline", "")
    features = plan.get("features", [])
    stack = plan.get("tech_stack", {})

    features_md = "\n".join(f"- **{f['name']}** — {f['description']}" for f in features)
    stack_md = "\n".join(f"- **{k.title()}:** {v}" for k, v in stack.items())

    return [
        {"path": "README.md", "content": f"# {app_name}\n\n> {tagline}\n\n{plan.get('description','')}\n\n## Features\n\n{features_md}\n\n## Tech Stack\n\n{stack_md}\n\n## Setup\n\n```bash\ncp .env.example .env\ndocker compose up --build\n```\n"},
        {"path": ".gitignore", "content": "*.env\n.env\n__pycache__/\nnode_modules/\ndist/\n.DS_Store\n*.pyc\n"},
        {"path": ".env.example", "content": "DATABASE_URL=postgresql://postgres:postgres@db:5432/app\nSECRET_KEY=change-me\nENVIRONMENT=development\n"},
        {"path": "APP_PLAN.json", "content": json.dumps(plan, indent=2)},
    ]


# ─── Git helpers ─────────────────────────────────────────────────────────────

def _get_gh_user(token: str) -> str:
    try:
        out = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "GH_TOKEN": token} if token else os.environ,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "louisestalker3"


async def _git_push(target_dir: Path, slug: str, app_name: str) -> str:
    def run(cmd: list[str]) -> str:
        result = subprocess.run(
            cmd, cwd=str(target_dir), capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{cmd[0]} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    loop = asyncio.get_event_loop()

    def _sync_git():
        gh_token = os.environ.get("GH_TOKEN", "")
        gh_user = _get_gh_user(gh_token)
        repo_url = f"https://github.com/{gh_user}/{slug}"

        git_dir = target_dir / ".git"
        if not git_dir.exists():
            run(["git", "init", "-b", "main"])
            run(["git", "add", "."])
            run(["git", "commit", "-m",
                 f"Initial build: {app_name}\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"])
        else:
            run(["git", "add", "."])
            subprocess.run(
                ["git", "commit", "-m", "Rebuild: regenerated application files"],
                cwd=str(target_dir), capture_output=True, text=True, timeout=30,
            )

        # Create private GitHub repo — ignore "already exists"
        out = subprocess.run(
            ["gh", "repo", "create", slug, "--private"],
            cwd=str(target_dir), capture_output=True, text=True, timeout=60,
            env={**os.environ, "GH_PROTOCOL": "https"},
        )
        if out.returncode != 0 and "already exists" not in (out.stderr + out.stdout).lower():
            raise RuntimeError(f"gh repo create failed: {out.stderr.strip()}")

        # Set HTTPS remote with token (works without SSH keys)
        token_url = (
            f"https://{gh_token}@github.com/{gh_user}/{slug}.git"
            if gh_token else f"https://github.com/{gh_user}/{slug}.git"
        )
        subprocess.run(["git", "remote", "remove", "origin"],
                       cwd=str(target_dir), capture_output=True, text=True)
        run(["git", "remote", "add", "origin", token_url])
        run(["git", "push", "-u", "origin", "main"])

        return repo_url

    return await loop.run_in_executor(None, _sync_git)
