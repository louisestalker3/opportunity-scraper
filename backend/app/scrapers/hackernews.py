import logging
from typing import Any

import httpx

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

ALGOLIA_BASE = "https://hn.algolia.com/api/v1"

SEARCH_QUERIES = [
    "alternative to",
    "looking for tool",
    "anyone know a good",
    "recommend a tool",
    "what do you use for",
    "SaaS",
    "web app",
]


class HNScraper(BaseScraper):
    source = "hackernews"

    async def _fetch_hits(
        self, client: httpx.AsyncClient, query: str, tags: str = "story,comment"
    ) -> list[dict]:
        params = {
            "query": query,
            "tags": tags,
            "hitsPerPage": 50,
            "numericFilters": "created_at_i>1700000000",  # roughly ~Nov 2023
        }
        resp = await client.get(f"{ALGOLIA_BASE}/search", params=params, timeout=15.0)
        resp.raise_for_status()
        return resp.json().get("hits", [])

    async def scrape(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(
            headers={"User-Agent": "OpportunityScraper/1.0 (market intelligence tool)"}
        ) as client:
            for query in SEARCH_QUERIES:
                try:
                    hits = await self._fetch_hits(client, query)
                    for hit in hits:
                        object_id = hit.get("objectID", "")
                        if not object_id or object_id in seen_ids:
                            continue
                        seen_ids.add(object_id)

                        story_id = hit.get("story_id") or hit.get("objectID")
                        url = (
                            hit.get("url")
                            or f"https://news.ycombinator.com/item?id={story_id}"
                        )

                        # Prefer comment_text, then story_text, then title
                        content = (
                            hit.get("comment_text")
                            or hit.get("story_text")
                            or hit.get("title")
                            or ""
                        )
                        if not content:
                            continue

                        raw = {
                            "objectID": object_id,
                            "title": hit.get("title"),
                            "url": url,
                            "author": hit.get("author"),
                            "points": hit.get("points"),
                            "num_comments": hit.get("num_comments"),
                            "created_at": hit.get("created_at"),
                            "tags": hit.get("_tags", []),
                            "story_id": story_id,
                        }

                        results.append(
                            {
                                "source_id": object_id,
                                "content": content[:4000],
                                "url": url,
                                "raw_data": raw,
                            }
                        )
                except Exception as exc:
                    logger.warning("HN scrape failed for query=%r: %s", query, exc)

        logger.info("HN scraper collected %d items", len(results))
        return results
