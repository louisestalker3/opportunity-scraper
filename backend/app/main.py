import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import opportunities, apps, pipeline, scrape, analyze, ideas, names, logos, tasks, status, settings as settings_routes
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Opportunity Scraper API",
    description="SaaS market intelligence tool that scores market opportunities for indie developers.",
    version="0.1.0",
)

# CORS — allow all origins in development
origins = ["*"] if settings.is_development else [
    "https://opportunity-scraper.up.railway.app",
    "https://opportunity-scraper.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Opportunity Scraper API starting up (env=%s)", settings.environment)


@app.get("/health", tags=["meta"])
async def health_check() -> dict:
    return {"status": "ok", "environment": settings.environment}


app.include_router(opportunities.router, prefix="/api/opportunities", tags=["opportunities"])
app.include_router(apps.router, prefix="/api/apps", tags=["apps"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])
app.include_router(scrape.router, prefix="/api/scrape", tags=["scrape"])
app.include_router(analyze.router, prefix="/api/analyze", tags=["analyze"])
app.include_router(ideas.router, prefix="/api/ideas", tags=["ideas"])

# Per-project sub-resources (nested under pipeline items)
app.include_router(names.router, prefix="/api/pipeline/{item_id}/names", tags=["names"])
app.include_router(logos.router, prefix="/api/pipeline/{item_id}/logos", tags=["logos"])
app.include_router(tasks.router, prefix="/api/pipeline/{item_id}/tasks", tags=["tasks"])
app.include_router(tasks.runner_router, prefix="/api/tasks", tags=["task-runner"])
app.include_router(status.router, prefix="/api/status", tags=["status"])
app.include_router(settings_routes.router, prefix="/api/settings", tags=["settings"])
