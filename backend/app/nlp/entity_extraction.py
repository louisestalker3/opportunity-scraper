import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a product intelligence analyst. Your job is to extract the names of specific software products and web apps mentioned in user-generated text.

Rules:
1. Only extract named software products, web apps, SaaS tools, or platforms (e.g. "Notion", "Slack", "Jira", "Trello").
2. Do NOT extract generic terms like "Google", "Excel", "Microsoft", "email", "spreadsheet", "database", "tool", "app", "software", "platform".
3. Do NOT extract company names that are not software products (e.g. "Salesforce" as a company name is OK, "Salesforce CRM" is better).
4. Also detect if the text shows "alternative_seeking" intent — meaning the author is actively looking for a different tool to replace one they are using.
5. Return a JSON object with:
   - "apps": list of objects with {"name": str, "confidence": float 0-1}
   - "alternative_seeking": true | false
   - "apps_being_replaced": list of app names the user wants to replace (subset of "apps")

Respond ONLY with the JSON object."""


class AppNameExtractor:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def extract(self, text: str) -> dict[str, Any]:
        """Extract app names and alternative-seeking signal from a single text."""
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text[:2000]},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            parsed = json.loads(raw)

            apps = parsed.get("apps", [])
            # Normalise to list of dicts
            normalised_apps = []
            for app in apps:
                if isinstance(app, dict):
                    normalised_apps.append({
                        "name": str(app.get("name", "")).strip(),
                        "confidence": float(app.get("confidence", 0.7)),
                    })
                elif isinstance(app, str):
                    normalised_apps.append({"name": app.strip(), "confidence": 0.7})

            # Filter out empty names
            normalised_apps = [a for a in normalised_apps if a["name"]]

            return {
                "apps": normalised_apps,
                "alternative_seeking": bool(parsed.get("alternative_seeking", False)),
                "apps_being_replaced": parsed.get("apps_being_replaced", []),
            }
        except Exception as exc:
            logger.error("Entity extraction failed: %s", exc)
            return {"apps": [], "alternative_seeking": False, "apps_being_replaced": []}

    def high_confidence_names(self, result: dict[str, Any], threshold: float = 0.7) -> list[str]:
        """Return only app names above a confidence threshold."""
        return [a["name"] for a in result.get("apps", []) if a["confidence"] >= threshold]
