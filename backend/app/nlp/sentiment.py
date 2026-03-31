"""
Sentiment analysis using Claude (if ANTHROPIC_API_KEY is set) with VADER as fallback.
"""
import logging
from typing import Any

from app.nlp.claude_cli import call_claude_json

logger = logging.getLogger(__name__)

BATCH_SIZE = 10

SYSTEM_PROMPT = """You are a market intelligence analyst specialising in SaaS products.

Classify each piece of user-generated text (Reddit posts, reviews, forum comments) about software tools.

For each text, return a JSON object with:
- sentiment: "positive" | "negative" | "neutral"
- signal_type: "complaint" | "praise" | "alternative_seeking" | "pricing_objection" | "general"
  * complaint = specific pain point or frustration
  * praise = complimenting a feature or product
  * alternative_seeking = user is looking for a different/better tool
  * pricing_objection = user complains explicitly about cost or pricing
  * general = informational or doesn't fit above
- confidence_score: float 0.0–1.0

Respond ONLY with a JSON array, one object per input text, in the same order."""


class SentimentAnalyser:
    def __init__(self) -> None:
        self._vader = None
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._vader = SentimentIntensityAnalyzer()
        except ImportError:
            logger.warning("SentimentAnalyser: vaderSentiment not installed — using keyword fallback")

    # ── Claude-based analysis ────────────────────────────────────────────────

    async def _analyse_with_claude(self, texts: list[str]) -> list[dict[str, Any]]:
        numbered = "\n\n".join(f"[{i + 1}] {t[:800]}" for i, t in enumerate(texts))

        parsed = await call_claude_json(numbered, system=SYSTEM_PROMPT)
        if not parsed:
            return [{"sentiment": "neutral", "signal_type": "general", "confidence_score": 0.0} for _ in texts]

        if not isinstance(parsed, list):
            parsed = list(parsed.values())[0] if isinstance(parsed, dict) else []

        out = []
        for i, _ in enumerate(texts):
            item = parsed[i] if i < len(parsed) and isinstance(parsed[i], dict) else {}
            out.append({
                "sentiment": item.get("sentiment", "neutral"),
                "signal_type": item.get("signal_type", "general"),
                "confidence_score": float(item.get("confidence_score", 0.5)),
            })
        return out

    # ── VADER / keyword fallback ─────────────────────────────────────────────

    _COMPLAINT_KW = ["broken", "bug", "issue", "problem", "frustrat", "hate", "terrible",
                     "awful", "slow", "crash", "useless", "disappoint", "annoying", "worst",
                     "doesn't work", "not work", "stopped working"]
    _ALTERNATIVE_KW = ["alternative to", "alternatives to", "looking for", "recommend",
                       "switched from", "switch from", "moving away", "replace", "instead of"]
    _PRICING_KW = ["too expensive", "overpriced", "pricing", "cost", "afford",
                   "subscription fee", "price hike", "can't afford", "cheaper"]
    _PRAISE_KW = ["love", "great", "amazing", "excellent", "perfect", "awesome",
                  "fantastic", "best", "recommend", "happy with", "works great"]

    def _classify_local(self, text: str) -> dict[str, Any]:
        lower = text.lower()

        signal_type = "general"
        if any(k in lower for k in self._ALTERNATIVE_KW):
            signal_type = "alternative_seeking"
        elif any(k in lower for k in self._PRICING_KW):
            signal_type = "pricing_objection"
        elif any(k in lower for k in self._COMPLAINT_KW):
            signal_type = "complaint"
        elif any(k in lower for k in self._PRAISE_KW):
            signal_type = "praise"

        if self._vader:
            scores = self._vader.polarity_scores(text)
            compound = scores["compound"]
            sentiment = "positive" if compound >= 0.05 else "negative" if compound <= -0.05 else "neutral"
            confidence = round(min(abs(compound) + 0.5, 1.0), 3)
        else:
            pos = sum(1 for k in self._PRAISE_KW if k in lower)
            neg = sum(1 for k in self._COMPLAINT_KW if k in lower)
            if pos > neg:
                sentiment, confidence = "positive", 0.6
            elif neg > pos:
                sentiment, confidence = "negative", 0.6
            else:
                sentiment, confidence = "neutral", 0.5

        # Complaints shouldn't be positive
        if signal_type in ("complaint", "pricing_objection", "alternative_seeking") and sentiment == "positive":
            sentiment = "neutral"

        return {"sentiment": sentiment, "signal_type": signal_type, "confidence_score": confidence}

    # ── Public interface ─────────────────────────────────────────────────────

    async def analyse_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        if not texts:
            return []
        result = await self._analyse_with_claude(texts)
        if result and any(r.get("confidence_score", 0) > 0 for r in result):
            return result
        return [self._classify_local(t) for t in texts]

    async def analyse_many(self, texts: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i: i + BATCH_SIZE]
            results.extend(await self.analyse_batch(batch))
        return results
