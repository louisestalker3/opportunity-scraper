import logging
from typing import Any

import httpx

from app.config import settings
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

TWITTER_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

SEARCH_QUERIES = [
    "alternative to",
    "looking for a tool",
    "too expensive",
    "frustrated with",
    "cancel subscription",
    "switched from",
]

TWEET_FIELDS = "created_at,author_id,public_metrics,entities,lang"
MAX_RESULTS_PER_QUERY = 100


class TwitterScraper(BaseScraper):
    source = "twitter"

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {settings.twitter_bearer_token}"}

    async def _search_tweets(
        self, client: httpx.AsyncClient, query: str
    ) -> list[dict]:
        """Search recent tweets using Twitter API v2."""
        params = {
            "query": f"{query} lang:en -is:retweet",
            "max_results": MAX_RESULTS_PER_QUERY,
            "tweet.fields": TWEET_FIELDS,
        }
        try:
            resp = await client.get(
                TWITTER_SEARCH_URL,
                params=params,
                headers=self._auth_headers(),
                timeout=15.0,
            )
            if resp.status_code == 401:
                logger.warning("Twitter API: Unauthorized — check TWITTER_BEARER_TOKEN")
                return []
            if resp.status_code == 429:
                logger.warning("Twitter API: Rate limited")
                return []
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except httpx.HTTPStatusError as exc:
            logger.warning("Twitter API error for query=%r: %s", query, exc)
            return []

    async def scrape(self) -> list[dict[str, Any]]:
        if not settings.twitter_bearer_token:
            logger.warning("TWITTER_BEARER_TOKEN not set — skipping Twitter scrape")
            return []

        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient() as client:
            for query in SEARCH_QUERIES:
                tweets = await self._search_tweets(client, query)
                for tweet in tweets:
                    tweet_id = tweet.get("id", "")
                    if not tweet_id or tweet_id in seen_ids:
                        continue
                    seen_ids.add(tweet_id)

                    text = tweet.get("text", "")
                    if not text:
                        continue

                    metrics = tweet.get("public_metrics", {})
                    raw = {
                        "id": tweet_id,
                        "text": text,
                        "author_id": tweet.get("author_id"),
                        "created_at": tweet.get("created_at"),
                        "retweet_count": metrics.get("retweet_count", 0),
                        "like_count": metrics.get("like_count", 0),
                        "reply_count": metrics.get("reply_count", 0),
                        "entities": tweet.get("entities", {}),
                        "search_query": query,
                    }

                    results.append({
                        "source_id": tweet_id,
                        "content": text[:4000],
                        "url": f"https://twitter.com/i/web/status/{tweet_id}",
                        "raw_data": raw,
                    })

        logger.info("Twitter scraper collected %d tweets", len(results))
        return results
