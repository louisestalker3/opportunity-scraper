import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a market intelligence analyst specialising in SaaS and software products.

Your job is to classify user-generated text (Reddit posts, reviews, tweets, forum comments) about software tools.

For each piece of text, return a JSON object with these fields:
- sentiment: "positive" | "negative" | "neutral"
  * positive = user is happy/satisfied with a product or feature
  * negative = user is unhappy, complaining, or frustrated
  * neutral = factual, informational, or mixed
- signal_type: "complaint" | "praise" | "alternative_seeking" | "pricing_objection" | "general"
  * complaint = specific pain point or bug report
  * praise = complimenting a feature or product
  * alternative_seeking = user is looking for a different/better tool
  * pricing_objection = user complains about cost or pricing model
  * general = doesn't fit the above categories
- confidence_score: float between 0.0 and 1.0 representing your certainty

Be conservative: only mark alternative_seeking if there is clear intent to switch or find another tool.
Only mark pricing_objection if pricing is the explicit or primary concern.

Respond ONLY with a JSON array, one object per input text."""

BATCH_SIZE = 10


class SentimentAnalyser:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def analyse_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        """Analyse a batch of texts (up to BATCH_SIZE). Returns list of classification dicts."""
        if not texts:
            return []

        numbered = "\n\n".join(
            f"[{i + 1}] {text[:1000]}" for i, text in enumerate(texts)
        )

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": numbered},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            parsed = json.loads(raw)

            # The model may return {"results": [...]} or just [...]
            if isinstance(parsed, list):
                results = parsed
            elif isinstance(parsed, dict):
                results = parsed.get("results", list(parsed.values())[0] if parsed else [])
            else:
                results = []

            # Ensure we have one result per input
            out = []
            for i, text in enumerate(texts):
                if i < len(results) and isinstance(results[i], dict):
                    item = results[i]
                else:
                    item = {}
                out.append({
                    "sentiment": item.get("sentiment", "neutral"),
                    "signal_type": item.get("signal_type", "general"),
                    "confidence_score": float(item.get("confidence_score", 0.5)),
                })
            return out

        except Exception as exc:
            logger.error("Sentiment analysis failed: %s", exc)
            return [
                {"sentiment": "neutral", "signal_type": "general", "confidence_score": 0.0}
                for _ in texts
            ]

    async def analyse_many(self, texts: list[str]) -> list[dict[str, Any]]:
        """Analyse an arbitrary number of texts in batches of BATCH_SIZE."""
        results: list[dict[str, Any]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i: i + BATCH_SIZE]
            batch_results = await self.analyse_batch(batch)
            results.extend(batch_results)
        return results
