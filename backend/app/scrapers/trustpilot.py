import asyncio
import logging
import random
from typing import Any

from playwright.async_api import async_playwright, Browser, Page

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# TODO: Add proxy rotation to avoid IP bans.
# Example integration point: pass proxy={'server': 'http://proxy:port'} to browser.new_context()

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

TRUSTPILOT_CATEGORY_URLS = [
    "https://www.trustpilot.com/categories/software_company",
    "https://www.trustpilot.com/categories/it_and_software",
]


class TrustpilotScraper(BaseScraper):
    source = "trustpilot"

    async def _scrape_category(self, page: Page, category_url: str) -> list[dict]:
        """Collect company links from a Trustpilot category page."""
        companies = []
        try:
            await page.goto(category_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(2.0, 4.0))

            cards = await page.query_selector_all(
                "[data-testid='business-unit-card'], .businessUnit, article"
            )
            for card in cards[:20]:
                try:
                    name_el = await card.query_selector("h3, h2, p[class*='title']")
                    name = (await name_el.inner_text()).strip() if name_el else None
                    link_el = await card.query_selector("a")
                    href = await link_el.get_attribute("href") if link_el else None
                    if name and href:
                        full_url = (
                            f"https://www.trustpilot.com{href}"
                            if href.startswith("/")
                            else href
                        )
                        companies.append({"name": name, "url": full_url})
                except Exception as exc:
                    logger.debug("Trustpilot card parse error: %s", exc)
        except Exception as exc:
            logger.warning("Trustpilot category scrape failed for %s: %s", category_url, exc)
        return companies

    async def _scrape_reviews(self, page: Page, company_url: str, app_name: str) -> list[dict]:
        """Scrape reviews for a specific Trustpilot company."""
        results = []
        try:
            await page.goto(company_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(2.0, 3.5))

            review_cards = await page.query_selector_all(
                "[data-testid='review-card'], article.review, section.review"
            )
            for card in review_cards[:20]:
                try:
                    body_el = await card.query_selector(
                        "[data-testid='review-body'], p.review-content__body, p"
                    )
                    body = (await body_el.inner_text()).strip() if body_el else ""
                    if not body:
                        continue

                    title_el = await card.query_selector("h2, h3, [data-testid='review-title']")
                    title = (await title_el.inner_text()).strip() if title_el else ""

                    rating_el = await card.query_selector("[data-rating], .star-rating")
                    rating = None
                    if rating_el:
                        raw = await rating_el.get_attribute("data-rating")
                        try:
                            rating = float(raw) if raw else None
                        except ValueError:
                            pass

                    content = f"{title}\n{body}".strip()
                    source_id = f"trustpilot_{hash(company_url + content[:50])}"

                    results.append({
                        "source_id": source_id,
                        "content": content[:4000],
                        "url": company_url,
                        "raw_data": {
                            "app_name": app_name,
                            "rating": rating,
                            "title": title,
                            "body": body,
                            "company_url": company_url,
                        },
                    })
                except Exception as exc:
                    logger.debug("Trustpilot review parse error: %s", exc)
        except Exception as exc:
            logger.warning("Trustpilot reviews scrape failed for %s: %s", company_url, exc)
        return results

    async def scrape(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            page = await context.new_page()

            try:
                for cat_url in TRUSTPILOT_CATEGORY_URLS:
                    companies = await self._scrape_category(page, cat_url)
                    await asyncio.sleep(random.uniform(1.5, 3.0))

                    for company in companies[:10]:
                        reviews = await self._scrape_reviews(
                            page, company["url"], company["name"]
                        )
                        results.extend(reviews)
                        await asyncio.sleep(random.uniform(1.0, 2.5))
            finally:
                await browser.close()

        logger.info("Trustpilot scraper collected %d items", len(results))
        return results
