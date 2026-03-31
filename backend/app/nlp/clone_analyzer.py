"""
Performs a market analysis on a specific app to determine if building a clone/alternative is viable.
Uses Claude to analyse the market opportunity, competition, and differentiation potential.
"""
import logging
from dataclasses import dataclass

from app.nlp.claude_cli import call_claude_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior market analyst and startup strategist specialising in SaaS products. You help indie developers evaluate whether it's worth building a clone or alternative to an existing app.

When given an app name, perform a comprehensive market analysis and give a clear, honest verdict on whether it's worth pursuing.

You must respond with a JSON object in this exact format:
{
  "verdict": "worth_building" | "risky" | "not_worth_it",
  "verdict_score": <integer 0-100, higher = more worth building>,
  "verdict_summary": "<1-2 sentence plain English verdict>",
  "market_size": "<estimated market size / TAM>",
  "growth_trend": "growing" | "stable" | "declining",
  "top_complaints": ["<complaint 1>", "<complaint 2>", "<complaint 3>"],
  "competitors": [{"name": "<name>", "weakness": "<key weakness>"}],
  "differentiation_angles": ["<angle 1>", "<angle 2>", "<angle 3>"],
  "pricing_gap": "<analysis of pricing opportunity>",
  "build_complexity": "low" | "medium" | "high",
  "time_to_mvp": "<realistic estimate e.g. 2-3 months>",
  "ideal_target": "<who should build this and why>",
  "biggest_risk": "<the main reason this could fail>",
  "report": "<full markdown analysis report — escape all newlines as \\n>"
}

The report field must be a complete markdown document with these sections:
## Market Overview
## User Pain Points
## Competitive Landscape
## Differentiation Opportunity
## Business Model Analysis
## Risk Assessment
## Verdict

Be honest and contrarian — if the market is saturated or the idea is weak, say so clearly."""


@dataclass
class CloneAnalysisResult:
    verdict: str          # worth_building | risky | not_worth_it
    verdict_score: int    # 0-100
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


async def analyze_clone_opportunity(
    app_name: str,
    app_url: str | None = None,
    extra_context: str | None = None,
) -> CloneAnalysisResult:
    result = await _analyze_with_claude(app_name, app_url, extra_context)
    return result if result else _fallback_analysis(app_name)


async def _analyze_with_claude(
    app_name: str,
    app_url: str | None,
    extra_context: str | None,
) -> CloneAnalysisResult | None:
    user_message = f"Analyse whether it is worth building a clone or alternative to: **{app_name}**"
    if app_url:
        user_message += f"\nApp URL: {app_url}"
    if extra_context:
        user_message += f"\nAdditional context: {extra_context}"
    user_message += "\n\nRespond only with the JSON object. No prose outside the JSON."

    data = await call_claude_json(user_message, system=SYSTEM_PROMPT)
    if not data or not isinstance(data, dict):
        return None

    return CloneAnalysisResult(
        verdict=data.get("verdict", "risky"),
        verdict_score=int(data.get("verdict_score", 50)),
        verdict_summary=data.get("verdict_summary", ""),
        market_size=data.get("market_size", "Unknown"),
        growth_trend=data.get("growth_trend", "stable"),
        top_complaints=data.get("top_complaints", []),
        competitors=data.get("competitors", []),
        differentiation_angles=data.get("differentiation_angles", []),
        pricing_gap=data.get("pricing_gap", ""),
        build_complexity=data.get("build_complexity", "medium"),
        time_to_mvp=data.get("time_to_mvp", "3-6 months"),
        ideal_target=data.get("ideal_target", ""),
        biggest_risk=data.get("biggest_risk", ""),
        report=data.get("report", ""),
    )


def _fallback_analysis(app_name: str) -> CloneAnalysisResult:
    report = f"""## Market Overview

Analysis of **{app_name}** as a clone/alternative opportunity.

*This is a template response — set ANTHROPIC_API_KEY for a full AI-powered analysis.*

## User Pain Points

Common pain points for apps in this category typically include pricing, complexity, and missing features.

## Competitive Landscape

Multiple competitors likely exist in this space. Further research is needed to map the full landscape.

## Differentiation Opportunity

Focus on simplicity, better pricing, or a specific niche that the incumbent ignores.

## Business Model Analysis

Consider a freemium model with a clear upgrade path.

## Risk Assessment

Market saturation and customer acquisition costs are the primary risks.

## Verdict

Without AI analysis, a definitive verdict cannot be provided. Set ANTHROPIC_API_KEY for full analysis."""

    return CloneAnalysisResult(
        verdict="risky",
        verdict_score=50,
        verdict_summary=f"Unable to fully analyse {app_name} without AI integration. Configure ANTHROPIC_API_KEY for a detailed report.",
        market_size="Unknown",
        growth_trend="stable",
        top_complaints=["Pricing concerns", "Missing features", "Poor support"],
        competitors=[],
        differentiation_angles=["Simpler UX", "Lower pricing", "Niche focus"],
        pricing_gap="Research needed",
        build_complexity="medium",
        time_to_mvp="3-6 months",
        ideal_target="Indie developers or small teams",
        biggest_risk="Market saturation",
        report=report,
    )
