"""
Reddit scraper using the public JSON API — no API keys required.
"""
import asyncio
import logging
from typing import Any

import httpx

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SUBREDDITS = [
    "SaaS",
    "webdev",
    "entrepreneur",
    "startups",
    "smallbusiness",
]

SEARCH_QUERIES = [
    "alternative to",
    "looking for",
    "too expensive",
    "frustrated with",
    "switched from",
    "cancel my subscription",
    "doesn't do",
    "I hate",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OpportunityScraper/1.0; research tool)",
    "Accept": "application/json",
}


class RedditScraper(BaseScraper):
    source = "reddit"

    async def scrape(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
            for subreddit in SUBREDDITS:
                for query in SEARCH_QUERIES:
                    try:
                        url = f"https://www.reddit.com/r/{subreddit}/search.json"
                        params = {
                            "q": query,
                            "sort": "new",
                            "limit": 25,
                            "t": "month",
                            "restrict_sr": "1",
                        }
                        resp = await client.get(url, params=params)
                        if resp.status_code != 200:
                            logger.warning(
                                "Reddit public API returned %d for r/%s q=%r",
                                resp.status_code, subreddit, query,
                            )
                            continue

                        data = resp.json()
                        posts = data.get("data", {}).get("children", [])

                        for wrapper in posts:
                            post = wrapper.get("data", {})
                            pid = post.get("id", "")
                            if not pid or pid in seen_ids:
                                continue
                            seen_ids.add(pid)

                            title = post.get("title", "")
                            selftext = post.get("selftext", "")
                            permalink = "https://reddit.com" + post.get("permalink", "")

                            content = f"{title}\n\n{selftext}".strip()
                            if not content or len(content) < 20:
                                continue

                            results.append({
                                "source_id": f"post_{pid}",
                                "content": content[:4000],
                                "url": permalink,
                                "raw_data": {
                                    "id": pid,
                                    "title": title,
                                    "subreddit": subreddit,
                                    "score": post.get("score", 0),
                                    "num_comments": post.get("num_comments", 0),
                                    "created_utc": post.get("created_utc", 0),
                                    "search_query": query,
                                },
                            })

                        # Respect rate limits — Reddit allows ~1 req/sec without auth
                        await asyncio.sleep(1.2)

                    except Exception as exc:
                        logger.warning(
                            "Reddit scrape failed for r/%s q=%r: %s", subreddit, query, exc
                        )

        logger.info("Reddit scraper (keyless) collected %d items", len(results))
        return results
