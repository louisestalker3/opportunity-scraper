"""
Generates original app ideas using Claude and evaluates their viability.
Creates AppProfile + Opportunity records for each generated idea.
"""
import logging
from dataclasses import dataclass, field

from app.nlp.claude_cli import call_claude, ProxyUnavailableError, strip_code_fence

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a seasoned indie developer and market analyst. You identify underserved niches in the SaaS market and generate ideas for apps with real commercial potential.

Generate original app ideas — NOT clones of existing popular apps. Focus on:
- B2B SaaS tools for specific workflows
- Developer tools
- Niche productivity apps
- Underserved industry verticals

For each idea, evaluate its market viability objectively and score it honestly.

Respond ONLY with a JSON array in this exact format (no prose outside the array):
[
  {
    "name": "<app name>",
    "tagline": "<one-liner value proposition>",
    "category": "<one of: Project Management, CRM, Marketing, Analytics, Communication, Finance, HR, E-commerce, Developer Tools, Design>",
    "description": "<2-3 sentence description of the app and who it's for>",
    "target_audience": "<specific target user>",
    "problem_solved": "<the specific pain point this addresses>",
    "why_now": "<why is this a good time to build this>",
    "market_size": "<estimated addressable market>",
    "competition_level": "<low | medium | high>",
    "competitor_names": ["<name 1>", "<name 2>"],
    "differentiators": ["<key differentiator 1>", "<key differentiator 2>"],
    "monetization": "<how it makes money>",
    "viability_score": <integer 0-100>,
    "market_demand_score": <integer 0-100>,
    "complaint_severity_score": <integer 0-100>,
    "competition_density_score": <integer 0-100>,
    "pricing_gap_score": <integer 0-100>,
    "build_complexity_score": <integer 0-100>,
    "differentiation_score": <integer 0-100>,
    "pros": ["<strength 1>", "<strength 2>", "<strength 3>"],
    "cons": ["<weakness or risk 1>", "<weakness or risk 2>", "<weakness or risk 3>"],
    "ai_rationale": "<2-3 sentences explaining the viability score and the key deciding factors>"
  }
]

Generate exactly {count} ideas. Score honestly — not everything should be high-scoring."""


@dataclass
class GeneratedIdea:
    name: str
    tagline: str
    category: str | None
    description: str
    target_audience: str
    problem_solved: str
    why_now: str
    market_size: str
    competition_level: str
    competitor_names: list[str]
    differentiators: list[str]
    monetization: str
    viability_score: int
    market_demand_score: int
    complaint_severity_score: int
    competition_density_score: int
    pricing_gap_score: int
    build_complexity_score: int
    differentiation_score: int
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    ai_rationale: str = ""


async def generate_ideas(
    count: int = 5,
    category: str | None = None,
) -> list[GeneratedIdea]:
    return await _generate_with_claude(count, category)


async def _generate_with_claude(count: int, category: str | None) -> list[GeneratedIdea]:
    prompt = f"Generate {count} original app ideas"
    if category:
        prompt += f" specifically in the **{category}** category"
    prompt += ". Respond only with the JSON array."

    system = SYSTEM_PROMPT.replace("{count}", str(count))

    # raise_on_unavailable=True so callers get a clear error instead of a silent fallback
    raw = await call_claude(prompt, system=system, raise_on_unavailable=True)
    if not raw:
        raise ProxyUnavailableError("NLP proxy returned empty response")

    import json as _json
    try:
        data = _json.loads(strip_code_fence(raw))
    except _json.JSONDecodeError as exc:
        logger.error("Failed to parse idea JSON: %s\nRaw: %.500s", exc, raw)
        raise ProxyUnavailableError(f"Claude returned invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ProxyUnavailableError("Claude returned unexpected format (expected JSON array)")

    return [_parse_idea(d) for d in data]


def _parse_idea(d: dict) -> GeneratedIdea:
    return GeneratedIdea(
        name=d.get("name", "Untitled App"),
        tagline=d.get("tagline", ""),
        category=d.get("category"),
        description=d.get("description", ""),
        target_audience=d.get("target_audience", ""),
        problem_solved=d.get("problem_solved", ""),
        why_now=d.get("why_now", ""),
        market_size=d.get("market_size", "Unknown"),
        competition_level=d.get("competition_level", "medium"),
        competitor_names=d.get("competitor_names", []),
        differentiators=d.get("differentiators", []),
        monetization=d.get("monetization", ""),
        viability_score=int(d.get("viability_score", 50)),
        market_demand_score=int(d.get("market_demand_score", 50)),
        complaint_severity_score=int(d.get("complaint_severity_score", 50)),
        competition_density_score=int(d.get("competition_density_score", 50)),
        pricing_gap_score=int(d.get("pricing_gap_score", 50)),
        build_complexity_score=int(d.get("build_complexity_score", 50)),
        differentiation_score=int(d.get("differentiation_score", 50)),
        pros=d.get("pros", []),
        cons=d.get("cons", []),
        ai_rationale=d.get("ai_rationale", ""),
    )


def _fallback_ideas() -> list[GeneratedIdea]:
    return [
        GeneratedIdea(
            name="AI Meeting Summarizer",
            tagline="Never write meeting notes again",
            category="Communication",
            description="Automatically transcribes and summarises meetings, extracts action items, and sends follow-up summaries. Integrates with Google Meet, Zoom, and Teams.",
            target_audience="Remote teams and busy managers",
            problem_solved="Meeting notes are time-consuming and often incomplete or missed entirely",
            why_now="AI transcription costs have dropped dramatically, making this viable at low price points",
            market_size="$2B+ productivity software market",
            competition_level="medium",
            competitor_names=["Otter.ai", "Fireflies.ai"],
            differentiators=["Better action item extraction", "CRM integration", "Simpler pricing"],
            monetization="$15/user/month SaaS",
            viability_score=72,
            market_demand_score=80,
            complaint_severity_score=65,
            competition_density_score=55,
            pricing_gap_score=60,
            build_complexity_score=70,
            differentiation_score=75,
            pros=["Clear pain point", "Strong AI leverage", "Recurring revenue potential"],
            cons=["Competitive market", "Privacy/data concerns", "Sticky incumbents"],
            ai_rationale="Strong demand with clear ROI for users. Competition exists but quality gaps remain. Set ANTHROPIC_API_KEY for real AI-generated ideas.",
        )
    ]
