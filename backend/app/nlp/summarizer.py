"""
Review summarizer using Claude (if ANTHROPIC_API_KEY is set) with extractive fallback.
"""
import logging
from typing import Any

from app.nlp.claude_cli import call_claude_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a product researcher and market analyst. Synthesise user feedback about a software product.

Return a JSON object with:
- "pros": list of exactly 5 strings — the most praised features or benefits
- "cons": list of exactly 5 strings — the most complained-about pain points or gaps
- "summary": single paragraph (3-5 sentences) on the product's market position, what users love/hate, and opportunity gaps

Be specific and actionable. Avoid generic statements like "good product" or "some issues".
Respond ONLY with the JSON object."""

_COMPLAINT_KW = ["broken", "bug", "issue", "problem", "frustrat", "hate", "terrible", "awful",
                 "slow", "crash", "useless", "disappoint", "annoying", "worst", "doesn't work",
                 "not work", "stopped", "too expensive", "overpriced", "can't afford"]
_PRAISE_KW = ["love", "great", "amazing", "excellent", "perfect", "awesome",
              "fantastic", "best", "recommend", "happy with", "works great", "impressed"]


class ReviewSummarizer:
    async def summarize(self, app_name: str, mention_texts: list[str]) -> dict[str, Any]:
        if not mention_texts:
            return {"pros": [], "cons": [], "summary": ""}

        result = await self._summarize_with_claude(app_name, mention_texts)
        return result if result else self._summarize_extractive(app_name, mention_texts)

    async def _summarize_with_claude(self, app_name: str, mention_texts: list[str]) -> dict[str, Any] | None:
        # Cap total tokens
        combined: list[str] = []
        total = 0
        for text in mention_texts:
            snippet = text[:500]
            if total + len(snippet) > 12000:
                break
            combined.append(snippet)
            total += len(snippet)

        user_message = f"App: {app_name}\n\nFeedback:\n" + "\n---\n".join(combined)

        parsed = await call_claude_json(user_message, system=SYSTEM_PROMPT)
        if not parsed or not isinstance(parsed, dict):
            return None

        pros = [p for p in parsed.get("pros", []) if p][:5]
        cons = [c for c in parsed.get("cons", []) if c][:5]
        summary = parsed.get("summary", "")
        return {"pros": pros, "cons": cons, "summary": summary}

    def _summarize_extractive(self, app_name: str, mention_texts: list[str]) -> dict[str, Any]:
        complaint_sentences: list[str] = []
        praise_sentences: list[str] = []

        for text in mention_texts:
            lower = text.lower()
            first = text.split('.')[0].strip()[:200]
            if not first:
                continue
            if any(k in lower for k in _COMPLAINT_KW):
                complaint_sentences.append(first)
            elif any(k in lower for k in _PRAISE_KW):
                praise_sentences.append(first)

        # Deduplicate
        def dedup(sentences: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for s in sentences:
                key = s[:40].lower()
                if key not in seen:
                    seen.add(key)
                    out.append(s)
            return out

        cons = dedup(complaint_sentences)[:5]
        pros = dedup(praise_sentences)[:5]

        total = len(mention_texts)
        c_pct = int(len(complaint_sentences) / total * 100) if total else 0
        p_pct = int(len(praise_sentences) / total * 100) if total else 0

        summary = (
            f"{app_name} has been mentioned {total} times across monitored sources. "
            f"{c_pct}% of mentions contain complaints or switching signals, "
            f"while {p_pct}% are positive. "
            f"Top pain points: {', '.join(cons[:2]) if cons else 'none detected yet'}."
        )
        return {"pros": pros, "cons": cons, "summary": summary}
