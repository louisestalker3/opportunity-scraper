import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a product researcher and market analyst. You will be given a collection of user reviews, social posts, and comments about a software product.

Your task is to synthesise the feedback into a concise summary. Return a JSON object with:
- "pros": list of exactly 5 strings — the most praised features or benefits mentioned across the feedback.
- "cons": list of exactly 5 strings — the most complained-about pain points, missing features, or gaps.
- "summary": a single paragraph (3-5 sentences) summarising the product's market position, what users love and hate, and what opportunity gaps exist for a competitor.

Focus on recurring themes. Be specific and actionable — avoid generic statements like "good product" or "some issues".

Respond ONLY with the JSON object."""


class ReviewSummarizer:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def summarize(self, app_name: str, mention_texts: list[str]) -> dict[str, Any]:
        """
        Summarise a list of mentions for an app into pros, cons, and a summary paragraph.

        Returns: {"pros": [...], "cons": [...], "summary": "..."}
        """
        if not mention_texts:
            return {"pros": [], "cons": [], "summary": ""}

        # Cap total text to avoid token overflow
        combined = []
        total_chars = 0
        for text in mention_texts:
            snippet = text[:500]
            if total_chars + len(snippet) > 12000:
                break
            combined.append(snippet)
            total_chars += len(snippet)

        formatted = "\n---\n".join(combined)
        user_message = f"App: {app_name}\n\nFeedback:\n{formatted}"

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            parsed = json.loads(raw)

            pros = parsed.get("pros", [])[:5]
            cons = parsed.get("cons", [])[:5]
            summary = parsed.get("summary", "")

            # Pad to 5 items if short
            while len(pros) < 5:
                pros.append("")
            while len(cons) < 5:
                cons.append("")

            return {"pros": pros, "cons": cons, "summary": summary}

        except Exception as exc:
            logger.error("Review summarization failed for app=%r: %s", app_name, exc)
            return {"pros": [], "cons": [], "summary": ""}
