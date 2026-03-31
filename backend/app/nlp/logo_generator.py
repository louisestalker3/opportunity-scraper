"""
Generates SVG logo concepts using Claude.
Claude writes clean SVG code for each logo concept.
"""
import logging
from dataclasses import dataclass, field

from app.nlp.claude_cli import call_claude_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert SVG logo designer for SaaS products.

Generate clean, professional SVG logo concepts. Each logo should:
- Be a valid, self-contained SVG (viewBox="0 0 200 60" for horizontal logos)
- Include the app name as text
- Have a simple icon/symbol to the left of the name
- Use the provided color palette
- Be minimal and modern — no gradients, no drop shadows, no complex paths unless needed
- Text: use font-family="system-ui, -apple-system, sans-serif"

Respond ONLY with a JSON array:
[
  {
    "concept_name": "<short concept label e.g. 'Wordmark', 'Bold Icon', 'Minimal'>",
    "description": "<1-2 sentences describing the design concept and what the icon represents>",
    "style": "<one of: minimal, bold, playful, tech, elegant>",
    "color_palette": {
      "primary": "<hex color>",
      "secondary": "<hex color>",
      "accent": "<hex color>"
    },
    "svg_content": "<complete SVG string — escape double quotes with &quot; or use single quotes for SVG attributes>"
  }
]

SVG requirements:
- Use single quotes for all SVG attributes (e.g. viewBox='0 0 200 60')
- The icon should be drawn with basic shapes: rect, circle, path, polygon
- Icon width ~32px, placed at x=8, vertically centered
- App name text at x=48, y=38, font-size=22, font-weight=600
- Keep paths simple — prefer geometric shapes over complex illustrations

Generate exactly {count} concepts with distinctly different visual approaches."""


@dataclass
class LogoConcept:
    concept_name: str
    description: str
    style: str
    color_palette: dict
    svg_content: str
    icon_paths: list[str] = field(default_factory=list)


async def generate_logos(
    app_name: str,
    tagline: str | None,
    category: str | None,
    count: int = 3,
) -> list[LogoConcept]:
    result = await _generate_with_claude(app_name, tagline, category, count)
    return result if result else _fallback_logos(app_name)


async def _generate_with_claude(
    app_name: str,
    tagline: str | None,
    category: str | None,
    count: int,
) -> list[LogoConcept]:
    prompt_parts = [f"Generate {count} SVG logo concepts for:"]
    prompt_parts.append(f"App name: {app_name}")
    if tagline:
        prompt_parts.append(f"Tagline: {tagline}")
    if category:
        prompt_parts.append(f"Category: {category}")
    prompt_parts.append("\nMake each concept visually distinct. Respond only with the JSON array.")

    system = SYSTEM_PROMPT.replace("{count}", str(count))

    data = await call_claude_json("\n".join(prompt_parts), system=system)
    if not data or not isinstance(data, list):
        logger.error("Logo generation returned no data")
        return []

    return [
        LogoConcept(
            concept_name=d.get("concept_name", "Concept"),
            description=d.get("description", ""),
            style=d.get("style", "minimal"),
            color_palette=d.get("color_palette", {"primary": "#16a34a", "secondary": "#166534", "accent": "#bbf7d0"}),
            svg_content=d.get("svg_content", _make_fallback_svg(app_name, "#16a34a")),
        )
        for d in data
    ]


def _make_fallback_svg(app_name: str, color: str) -> str:
    # Truncate long names for display
    display_name = app_name[:14] if len(app_name) > 14 else app_name
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 60'>"
        f"<rect x='8' y='14' width='32' height='32' rx='6' fill='{color}'/>"
        f"<text x='14' y='36' font-family='system-ui,sans-serif' font-size='16' "
        f"font-weight='700' fill='white'>{display_name[0].upper()}</text>"
        f"<text x='48' y='38' font-family='system-ui,sans-serif' font-size='22' "
        f"font-weight='600' fill='#111827'>{display_name}</text>"
        f"</svg>"
    )


def _fallback_logos(app_name: str) -> list[LogoConcept]:
    colors = [
        {"primary": "#16a34a", "secondary": "#166534", "accent": "#bbf7d0"},
        {"primary": "#2563eb", "secondary": "#1e40af", "accent": "#bfdbfe"},
        {"primary": "#7c3aed", "secondary": "#5b21b6", "accent": "#ddd6fe"},
    ]
    styles = ["minimal", "bold", "tech"]
    names = ["Wordmark", "Bold Block", "Tech Line"]

    return [
        LogoConcept(
            concept_name=names[i],
            description=f"A {styles[i]} logo concept using {colors[i]['primary']} as the primary color.",
            style=styles[i],
            color_palette=colors[i],
            svg_content=_make_fallback_svg(app_name, colors[i]["primary"]),
        )
        for i in range(3)
    ]
