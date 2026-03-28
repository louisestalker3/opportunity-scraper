import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Abstract base scraper with retry logic and exponential backoff."""

    MAX_RETRIES = 3
    BASE_BACKOFF = 2.0  # seconds

    @property
    @abstractmethod
    def source(self) -> str:
        """Return the source name, e.g. 'reddit'."""

    @abstractmethod
    async def scrape(self) -> list[dict[str, Any]]:
        """
        Scrape the source and return a list of raw mention dicts.

        Each dict must contain at minimum:
            source_id (str)  - unique ID within the source platform
            content   (str)  - the text of the mention
            url       (str)  - link to the original post/comment
            raw_data  (dict) - full raw payload from the source
        """

    async def scrape_with_retry(self) -> list[dict[str, Any]]:
        """Run scrape() with exponential backoff retries."""
        last_exc: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info("[%s] Scrape attempt %d/%d", self.source, attempt, self.MAX_RETRIES)
                results = await self.scrape()
                logger.info("[%s] Scrape returned %d items", self.source, len(results))
                return results
            except Exception as exc:
                last_exc = exc
                wait = self.BASE_BACKOFF ** attempt
                logger.warning(
                    "[%s] Attempt %d failed (%s). Retrying in %.1fs…",
                    self.source,
                    attempt,
                    exc,
                    wait,
                )
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(wait)

        logger.error("[%s] All %d attempts failed: %s", self.source, self.MAX_RETRIES, last_exc)
        raise RuntimeError(f"[{self.source}] Scraping failed after {self.MAX_RETRIES} retries") from last_exc
