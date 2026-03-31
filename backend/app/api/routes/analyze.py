from fastapi import APIRouter
from pydantic import BaseModel

from app.nlp.clone_analyzer import analyze_clone_opportunity

router = APIRouter()


class CloneAnalysisRequest(BaseModel):
    app_name: str
    app_url: str | None = None
    extra_context: str | None = None


class CloneAnalysisResponse(BaseModel):
    verdict: str
    verdict_score: int
    verdict_summary: str
    market_size: str
    growth_trend: str
    top_complaints: list[str]
    competitors: list[dict]
    differentiation_angles: list[str]
    pricing_gap: str
    build_complexity: str
    time_to_mvp: str
    ideal_target: str
    biggest_risk: str
    report: str


@router.post("/clone", response_model=CloneAnalysisResponse)
async def analyze_clone(body: CloneAnalysisRequest):
    """Analyse whether it's worth building a clone or alternative to a given app."""
    result = await analyze_clone_opportunity(
        app_name=body.app_name,
        app_url=body.app_url,
        extra_context=body.extra_context,
    )
    return CloneAnalysisResponse(
        verdict=result.verdict,
        verdict_score=result.verdict_score,
        verdict_summary=result.verdict_summary,
        market_size=result.market_size,
        growth_trend=result.growth_trend,
        top_complaints=result.top_complaints,
        competitors=result.competitors,
        differentiation_angles=result.differentiation_angles,
        pricing_gap=result.pricing_gap,
        build_complexity=result.build_complexity,
        time_to_mvp=result.time_to_mvp,
        ideal_target=result.ideal_target,
        biggest_risk=result.biggest_risk,
        report=result.report,
    )
