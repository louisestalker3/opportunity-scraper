"""
Generates a detailed competitive product proposal for a saved opportunity.
Uses Claude if ANTHROPIC_API_KEY is set, otherwise produces a structured template.
"""
import logging
from typing import Any

from app.nlp.claude_cli import call_claude

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior product strategist and startup advisor. You help indie developers and small teams identify and capitalise on gaps in the SaaS market.

When given a market opportunity (an existing app with user complaints and switching signals), generate a detailed, actionable product proposal for a competitor or complementary product that addresses those gaps.

Structure the proposal in markdown with these sections:

## Executive Summary
2-3 sentences on the opportunity and what makes now the right time to build.

## Proposed Product Concept
Name suggestion, one-liner positioning statement, and the core "why" — what unsolved pain does this product fix?

## Core Feature Set
5-8 features that directly address the top complaints about the existing app. For each feature, explain *why* it addresses a real user pain point.

## Differentiation Strategy
How this product stands apart from the existing app AND other competitors in the space. Be specific about the positioning angle.

## Target Audience
Primary persona (who they are, what they need, why they'd switch). Secondary persona if relevant.

## Pricing Strategy
Recommended pricing model and tiers with rationale. Reference the existing app's pricing as context.

## Suggested Tech Stack
Pragmatic stack recommendation for an indie developer or small team to ship this quickly. Include: backend, frontend, database, auth, payments, deployment.

## MVP Scope (0-3 Months)
What to build first to validate the opportunity and acquire the first 100 users. Be ruthlessly scoped — what is the absolute minimum to prove the concept?

## Go-to-Market Entry Point
One specific, executable first move to acquire early users (e.g. a subreddit post, a free tool, a cold email sequence to a specific audience segment).

Be direct, specific, and actionable. Avoid generic advice."""


async def generate_proposal(
    app_name: str,
    category: str | None,
    description: str | None,
    pros: list[str],
    cons: list[str],
    pricing_tiers: list[Any],
    target_audience: str | None,
    viability_score: float | None,
    complaint_severity: float | None,
    mention_count: int,
    alternative_seeking_count: int,
) -> str:
    context = f"""**App being analysed:** {app_name}
**Category:** {category or "Unknown"}
**Description:** {description or "N/A"}
**Target audience:** {target_audience or "N/A"}
**Viability score:** {f"{viability_score:.0f}/100" if viability_score else "N/A"}
**Total mentions:** {mention_count} ({alternative_seeking_count} actively seeking alternatives)

**What users love (Pros):**
{chr(10).join(f"- {p}" for p in pros) if pros else "- No data yet"}

**What users hate (Cons / Pain Points):**
{chr(10).join(f"- {c}" for c in cons) if cons else "- No data yet"}

**Current pricing:**
{chr(10).join(f"- {tier}" for tier in pricing_tiers) if pricing_tiers else "- Unknown"}
"""

    result = await _generate_with_claude(app_name, context)
    return result if result else _generate_template(app_name, category, cons, pricing_tiers)


async def _generate_with_claude(app_name: str, context: str) -> str:
    result = await call_claude(
        f"Generate a competitive product proposal based on this market opportunity:\n\n{context}",
        system=SYSTEM_PROMPT,
    )
    if not result:
        logger.error("Proposal generation returned no data")
    return result


def _generate_template(
    app_name: str,
    category: str | None,
    cons: list[str],
    pricing_tiers: list[Any],
) -> str:
    top_pains = "\n".join(f"- {c}" for c in cons[:3]) if cons else "- See app profile for details"
    return f"""## Executive Summary

{app_name} has significant user frustration signals indicating a market gap. Users are actively seeking alternatives, making this a strong opportunity for a well-positioned competitor.

## Proposed Product Concept

**Working name:** {app_name} Alternative — *[rename to reflect your positioning]*

A simpler, more affordable alternative to {app_name} that solves the core pain points without the bloat.

## Core Feature Set

Based on the top user complaints about {app_name}:

{top_pains}

Build features that directly address each of these. Prioritise the top 3 for MVP.

## Differentiation Strategy

- Simpler onboarding (under 5 minutes to first value)
- Transparent, affordable pricing
- Focused on the core use case — no feature bloat
- Responsive support (a key weakness of most incumbents)

## Target Audience

Indie developers, small teams, and bootstrapped founders who find {app_name} too complex or expensive for their needs.

## Pricing Strategy

Undercut {app_name} by 30-50%. Start with a generous free tier to reduce friction. Move to a simple flat-rate paid tier (no per-seat surprises).

## Suggested Tech Stack

- **Backend:** FastAPI (Python) or Rails
- **Frontend:** React + Tailwind or Next.js
- **Database:** PostgreSQL (Supabase for managed)
- **Auth:** Clerk or Supabase Auth
- **Payments:** Lemon Squeezy or Stripe
- **Deploy:** Railway or Vercel

## MVP Scope (0-3 Months)

Ship only the core feature that {app_name} does poorly. One thing, done right. Get 10 paying customers before adding anything else.

## Go-to-Market Entry Point

Post a comparison article on Reddit (r/SaaS or category-specific subreddit): *"I was frustrated with {app_name} so I built an alternative — here's what I learned"*. Genuine, not spammy. Link to a landing page with a waitlist.
"""
