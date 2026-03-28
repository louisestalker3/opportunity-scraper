import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import praw

from app.config import settings
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
    "doesn't do",
    "I hate",
    "frustrated with",
    "switched from",
    "cancel my subscription",
]


class RedditScraper(BaseScraper):
    source = "reddit"

    def _build_client(self) -> praw.Reddit:
        return praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
            read_only=True,
        )

    def _scrape_sync(self) -> list[dict[str, Any]]:
        reddit = self._build_client()
        results: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for subreddit_name in SUBREDDITS:
            subreddit = reddit.subreddit(subreddit_name)
            for query in SEARCH_QUERIES:
                try:
                    posts = subreddit.search(query, limit=25, sort="new", time_filter="week")
                    for post in posts:
                        if post.id in seen_ids:
                            continue
                        seen_ids.add(post.id)

                        raw = {
                            "id": post.id,
                            "title": post.title,
                            "selftext": post.selftext,
                            "subreddit": subreddit_name,
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "created_utc": post.created_utc,
                            "author": str(post.author) if post.author else "[deleted]",
                            "url": post.url,
                            "permalink": f"https://reddit.com{post.permalink}",
                        }

                        content = f"{post.title}\n\n{post.selftext}".strip()
                        results.append(
                            {
                                "source_id": f"post_{post.id}",
                                "content": content[:4000],  # cap length
                                "url": raw["permalink"],
                                "raw_data": raw,
                            }
                        )

                        # Fetch top 10 comments
                        post.comments.replace_more(limit=0)
                        for comment in list(post.comments)[:10]:
                            if not comment.body or comment.body in ("[deleted]", "[removed]"):
                                continue
                            comment_id = f"comment_{comment.id}"
                            if comment_id in seen_ids:
                                continue
                            seen_ids.add(comment_id)

                            comment_raw = {
                                "id": comment.id,
                                "post_id": post.id,
                                "body": comment.body,
                                "score": comment.score,
                                "created_utc": comment.created_utc,
                                "author": str(comment.author) if comment.author else "[deleted]",
                                "permalink": f"https://reddit.com{comment.permalink}",
                                "subreddit": subreddit_name,
                            }
                            results.append(
                                {
                                    "source_id": comment_id,
                                    "content": comment.body[:4000],
                                    "url": comment_raw["permalink"],
                                    "raw_data": comment_raw,
                                }
                            )
                except Exception as exc:
                    logger.warning(
                        "Reddit scrape failed for r/%s query=%r: %s", subreddit_name, query, exc
                    )

        logger.info("Reddit scraper collected %d items", len(results))
        return results

    async def scrape(self) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._scrape_sync)
