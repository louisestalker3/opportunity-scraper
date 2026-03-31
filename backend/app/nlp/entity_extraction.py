"""
App name extraction using Claude (if ANTHROPIC_API_KEY is set) with regex fallback.
"""
import logging
import re
from typing import Any

from app.nlp.claude_cli import call_claude_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a product intelligence analyst. Extract named software products and web apps from user-generated text.

Rules:
1. Only extract specific named software products, web apps, SaaS tools, or platforms (e.g. "Notion", "Slack", "Jira").
2. Do NOT extract generic terms like "Google", "Excel", "email", "spreadsheet", "tool", "app", "software".
3. Detect "alternative_seeking" intent — if the author is actively looking for a different tool.
4. Return JSON:
   { "apps": [{"name": str, "confidence": float}], "alternative_seeking": bool, "apps_being_replaced": [str] }

Respond ONLY with the JSON object."""

# Curated list of popular SaaS apps for keyless matching
KNOWN_APPS = {
    "notion", "airtable", "asana", "monday", "jira", "trello", "linear", "clickup",
    "basecamp", "todoist", "slack", "discord", "teams", "zoom", "loom",
    "figma", "sketch", "canva", "github", "gitlab", "vercel", "netlify", "heroku", "railway",
    "stripe", "paddle", "hubspot", "salesforce", "pipedrive",
    "mailchimp", "convertkit", "klaviyo", "activecampaign", "sendgrid",
    "intercom", "zendesk", "freshdesk", "helpscout", "crisp",
    "zapier", "make", "n8n", "pipedream",
    "confluence", "coda", "obsidian", "roam", "logseq",
    "webflow", "wix", "squarespace", "wordpress", "ghost", "framer",
    "shopify", "woocommerce", "bigcommerce",
    "typeform", "surveymonkey", "tally", "paperform",
    "calendly", "buffer", "hootsuite", "later",
    "mixpanel", "amplitude", "hotjar", "posthog", "sentry", "datadog",
    "supabase", "firebase", "planetscale", "neon",
    "retool", "bubble", "glide", "appsmith",
    "lemon squeezy", "gumroad", "podia", "teachable", "kajabi",
}

EXTRACT_PATTERNS = [
    r"alternative(?:s)? to ([A-Z][A-Za-z0-9\s\.\-]{1,25}?)(?=\s|,|\.|$|'s)",
    r"(?:switched?|switching|moved?|moving) (?:away )?from ([A-Z][A-Za-z0-9\s\.\-]{1,25}?)(?=\s|,|\.|$| to)",
    r"replace(?:ment for)? ([A-Z][A-Za-z0-9\s\.\-]{1,25}?)(?=\s|,|\.|$)",
    r"instead of ([A-Z][A-Za-z0-9\s\.\-]{1,25}?)(?=\s|,|\.|$)",
    r"([A-Z][A-Za-z0-9]{2,20}) is (?:too expensive|broken|too slow|not working)",
    r"cancel(?:led)? (?:my )?([A-Z][A-Za-z0-9]{2,20}) subscription",
    r"([A-Z][A-Za-z0-9]{2,20}) doesn'?t (?:have|support|do|work)",
    r"love ([A-Z][A-Za-z0-9]{2,20})(?=\s|,|\.|$|'s)",
    r"hate ([A-Z][A-Za-z0-9]{2,20})(?=\s|,|\.|$)",
]

_SKIP = {"the", "a", "an", "i", "we", "they", "it", "he", "she", "my", "our",
         "this", "that", "what", "which", "some", "any", "all", "just", "very"}

ALTERNATIVE_SIGNALS = [
    "alternative to", "alternatives to", "looking for", "recommend",
    "switched from", "switch from", "moving away from", "replace",
    "replacement for", "instead of", "better than",
]


class AppNameExtractor:
    def __init__(self) -> None:
        pass

    async def extract(self, text: str) -> dict[str, Any]:
        result = await self._extract_with_claude(text)
        return result if result else self._extract_local(text)

    async def _extract_with_claude(self, text: str) -> dict[str, Any] | None:
        parsed = await call_claude_json(text[:2000], system=SYSTEM_PROMPT)
        if not parsed or not isinstance(parsed, dict):
            return None
        apps = []
        for app in parsed.get("apps", []):
            if isinstance(app, dict) and app.get("name"):
                apps.append({"name": str(app["name"]).strip(), "confidence": float(app.get("confidence", 0.7))})
            elif isinstance(app, str) and app:
                apps.append({"name": app.strip(), "confidence": 0.7})
        return {
            "apps": apps,
            "alternative_seeking": bool(parsed.get("alternative_seeking", False)),
            "apps_being_replaced": parsed.get("apps_being_replaced", []),
        }

    def _extract_local(self, text: str) -> dict[str, Any]:
        lower = text.lower()
        found: dict[str, float] = {}

        # Match known apps (high confidence)
        for app in KNOWN_APPS:
            if re.search(r'\b' + re.escape(app) + r'\b', lower):
                found[app.title()] = 0.9

        # Pattern-based extraction (medium confidence)
        for pattern in EXTRACT_PATTERNS:
            for match in re.finditer(pattern, text):
                name = match.group(1).strip().rstrip(".,;:'")
                if len(name) < 2 or name.lower() in _SKIP:
                    continue
                if name not in found:
                    found[name] = 0.7

        alternative_seeking = any(s in lower for s in ALTERNATIVE_SIGNALS)
        apps_being_replaced: list[str] = []
        if alternative_seeking:
            for pat in [
                r"alternative(?:s)? to ([A-Z][A-Za-z0-9\s\.\-]{1,25}?)(?=\s|,|\.|$)",
                r"(?:switched?|switching) from ([A-Z][A-Za-z0-9\s\.\-]{1,25}?)(?=\s|,|\.|$| to)",
            ]:
                for m in re.finditer(pat, text):
                    apps_being_replaced.append(m.group(1).strip())

        return {
            "apps": [{"name": n, "confidence": c} for n, c in found.items() if n],
            "alternative_seeking": alternative_seeking,
            "apps_being_replaced": apps_being_replaced,
        }

    def high_confidence_names(self, result: dict[str, Any], threshold: float = 0.7) -> list[str]:
        return [a["name"] for a in result.get("apps", []) if a["confidence"] >= threshold]
