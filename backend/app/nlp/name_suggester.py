"""
Generates original app name suggestions using Claude.
Names are based on what the app DOES, never on any competitor or trademarked product name.
"""
import logging
from dataclasses import dataclass

from app.nlp.claude_cli import call_claude_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a brand strategist and naming expert for SaaS products.

Generate creative, memorable, ORIGINAL app names. The names must be based entirely on:
- What problem the app solves
- Who it helps
- The core value it delivers

STRICT RULES — violating any of these is a failure:
1. Do NOT use any name that is already used by an existing product, business, or brand — anywhere in the world. Treat all existing brand names as off-limits.
2. Do NOT use, reference, or riff on any competitor or existing product name. Those are trademarks.
3. Do NOT use words like "Alternative", "Clone", "Like", or append/prepend a competitor name.
4. Every name must be completely original and standalone — as if the competitor never existed.
5. The name must not infringe on any copyright, trademark, or existing brand identity.
6. Names should be 1-3 words, easy to spell, and feel like a real SaaS product.
7. If forbidden names are provided, do not use them or any variation of them.
8. Think like a trademark lawyer: if someone could confuse this name with an existing product, pick a different name.

Respond ONLY with a JSON array:
[
  {
    "name": "<original app name>",
    "tagline": "<punchy one-liner, max 8 words>",
    "rationale": "<1 sentence: what inspired this name and why it works>"
  }
]

Generate exactly {count} suggestions. Vary the style — some abstract, some descriptive, some invented words."""


@dataclass
class NameSuggestion:
    name: str
    tagline: str
    rationale: str


async def suggest_names(
    description: str | None,
    category: str | None,
    tagline: str | None = None,
    features: list[str] | None = None,
    count: int = 6,
    existing_names: list[str] | None = None,
    forbidden_names: list[str] | None = None,
    hint: str | None = None,
) -> list[NameSuggestion]:
    result = await _suggest_with_claude(
        description, category, tagline, features,
        count, existing_names, forbidden_names, hint,
    )
    return result if result else _fallback_suggestions()


async def _suggest_with_claude(
    description: str | None,
    category: str | None,
    tagline: str | None,
    features: list[str] | None,
    count: int,
    existing_names: list[str] | None,
    forbidden_names: list[str] | None,
    hint: str | None,
) -> list[NameSuggestion]:
    prompt_parts = [f"Generate {count} original app names for a new SaaS product."]

    if category:
        prompt_parts.append(f"Category: {category}")
    if description:
        prompt_parts.append(f"What it does: {description}")
    if tagline:
        prompt_parts.append(f"Value proposition: {tagline}")
    if features:
        prompt_parts.append(f"Core features: {', '.join(features[:5])}")

    if forbidden_names:
        clean = [n for n in forbidden_names if n]
        if clean:
            prompt_parts.append(
                f"\nFORBIDDEN — do NOT use these names or any variation, derivative, or riff on them: {', '.join(clean)}"
            )

    if existing_names:
        prompt_parts.append(f"Already suggested (avoid repeating): {', '.join(existing_names)}")

    if hint:
        prompt_parts.append(f"\nUser direction: {hint}\nTake this into account when generating names.")

    prompt_parts.append("\nRespond only with the JSON array.")

    system = SYSTEM_PROMPT.replace("{count}", str(count))

    data = await call_claude_json("\n".join(prompt_parts), system=system)
    if not data or not isinstance(data, list):
        logger.error("Name suggestion returned no data")
        return []

    return [
        NameSuggestion(
            name=d.get("name", "Untitled"),
            tagline=d.get("tagline", ""),
            rationale=d.get("rationale", ""),
        )
        for d in data
    ]


_FALLBACK_POOL = [
    NameSuggestion("Flowspace", "Get more done, together", "Evokes productivity and open collaboration."),
    NameSuggestion("Tractiv", "Traction for your team", "Coined word: 'track' + 'active'."),
    NameSuggestion("Sprintly", "Ship faster, always", "Implies speed and iterative delivery."),
    NameSuggestion("Kanbu", "Work that flows", "Short invented word, easy to trademark."),
    NameSuggestion("Worklo", "Everything your team needs", "Compact blend of 'work' and 'flow'."),
    NameSuggestion("Taskvine", "Grow your work forward", "Organic metaphor for connected tasks."),
    NameSuggestion("Planexa", "Planning, simplified", "Blend of 'plan' and 'nexus'."),
    NameSuggestion("Orblane", "Your team's command centre", "Short, abstract, distinctive."),
]


def _fallback_suggestions() -> list[NameSuggestion]:
    import random
    return random.sample(_FALLBACK_POOL, min(6, len(_FALLBACK_POOL)))
