"""
Generates a structured JSON app plan for a saved opportunity.
The plan drives the automated build step.
"""
import json
import logging
import re
from typing import Any

from app.nlp.claude_cli import call_claude

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior software architect and product strategist. Given a SaaS market opportunity (an existing app with user complaints), design a concrete, buildable app plan for a competing product.

Return ONLY a valid JSON object — no markdown fences, no prose before or after. The JSON must match this exact schema:

{
  "app_name": "ProductName",
  "slug": "product-name",
  "tagline": "One punchy line — what it does and for whom",
  "description": "2-3 sentences describing the product and the gap it fills",
  "scale": "large" or "small",
  "tech_stack": {
    "frontend": "...",
    "backend": "...",
    "database": "PostgreSQL",
    "auth": "...",
    "payments": "Stripe",
    "deployment": "Docker + Railway"
  },
  "features": [
    {"name": "Feature Name", "description": "What it does and why it matters", "priority": "mvp"},
    {"name": "Feature Name", "description": "What it does and why it matters", "priority": "v2"}
  ],
  "target_audience": "Primary persona description",
  "pricing_model": "Description of pricing tiers",
  "mvp_summary": "1-2 sentences on the absolute minimum to ship and validate"
}

## Tech stack selection rules — follow these exactly:

**Small apps** (simple CRUD tools, invoice generators, form builders, calculators, single-purpose utilities with ≤5 core features):
- scale: "small"
- frontend: "PHP + Tailwind CSS (server-rendered)"
- backend: "PHP 8.3 (vanilla, no framework)"
- auth: "PHP sessions"

**Large apps** (project management, CRMs, multi-tenant SaaS, collaboration tools, platforms with APIs, complex workflows, ≥6 core features):
- scale: "large"
- frontend: "Next.js 14 + TypeScript + Tailwind CSS"
- backend: "NestJS + TypeScript"
- auth: "NextAuth.js"

Use PostgreSQL for the database in all cases.

## Other rules:
- slug must be lowercase, hyphens only, no spaces (e.g. "invoice-flow")
- Include 4-6 mvp features and 2-3 v2 features
- The app_name must be original — do not use the competitor's name"""


async def generate_app_plan(
    app_name: str,
    category: str | None,
    description: str | None,
    pros: list[str],
    cons: list[str],
    target_audience: str | None,
    viability_score: float | None,
    mention_count: int,
    alternative_seeking_count: int,
) -> str:
    """Returns a JSON string representing the app plan."""
    context = f"""**Competitor being analysed:** {app_name}
**Category:** {category or "Unknown"}
**Description:** {description or "N/A"}
**Target audience:** {target_audience or "N/A"}
**Viability score:** {f"{viability_score:.0f}/100" if viability_score else "N/A"}
**Mentions:** {mention_count} ({alternative_seeking_count} actively seeking alternatives)

**What users love:**
{chr(10).join(f"- {p}" for p in pros) if pros else "- No data yet"}

**Top pain points (build for these):**
{chr(10).join(f"- {c}" for c in cons) if cons else "- No data yet"}
"""

    result = await _generate_with_claude(context)
    return result if result else _generate_fallback(app_name, category, cons)


async def _generate_with_claude(context: str) -> str:
    raw = await call_claude(
        f"Generate an app plan JSON for a competitor to this product:\n\n{context}",
        system=SYSTEM_PROMPT,
    )
    if not raw:
        logger.error("App plan generation returned no data")
        return ""
    # Strip markdown fences if Claude wraps anyway
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError as exc:
        logger.error("App plan JSON parse failed: %s", exc)
        return ""


def _generate_fallback(app_name: str, category: str | None, cons: list[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (app_name + "-alternative").lower()).strip("-")
    plan: dict[str, Any] = {
        "app_name": f"{app_name} Alternative",
        "slug": slug,
        "tagline": f"The simpler, faster alternative to {app_name}",
        "description": (
            f"A focused alternative to {app_name} that fixes the top user complaints. "
            f"Built for {category or 'indie developers'} who need the core functionality without the bloat."
        ),
        "scale": "large",
        "tech_stack": {
            "frontend": "Next.js 14 + TypeScript + Tailwind CSS",
            "backend": "NestJS + TypeScript",
            "database": "PostgreSQL",
            "auth": "NextAuth.js",
            "payments": "Stripe",
            "deployment": "Docker + Railway",
        },
        "features": [
            {"name": "Core Workspace", "description": "The main product area — fast, clean, no bloat.", "priority": "mvp"},
            {"name": "Onboarding Flow", "description": "Get users to first value in under 5 minutes.", "priority": "mvp"},
            {"name": "Simple Billing", "description": "Transparent flat-rate pricing via Stripe.", "priority": "mvp"},
            {"name": "Team Sharing", "description": "Share and collaborate without per-seat fees.", "priority": "v2"},
            {"name": "Integrations", "description": "Connect to the tools your users already use.", "priority": "v2"},
        ],
        "target_audience": f"Indie developers and small teams frustrated with {app_name}'s complexity and pricing.",
        "pricing_model": "Free tier (limited). Pro at $9/month flat. No per-seat fees.",
        "mvp_summary": f"Ship the one thing {app_name} does poorly, done right. Get 10 paying users before adding anything else.",
    }
    return json.dumps(plan, indent=2)
