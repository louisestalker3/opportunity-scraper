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

CAPTERRA_CATEGORIES = [
    "https://www.capterra.com/project-management-software/",
    "https://www.capterra.com/crm-software/",
    "https://www.capterra.com/accounting-software/",
    "https://www.capterra.com/marketing-automation-software/",
    "https://www.capterra.com/email-marketing-software/",
]


class CapterraScraper(BaseScraper):
    source = "capterra"

    async def _scrape_listing(self, page: Page, category_url: str) -> list[dict]:
        """Scrape software listings from a Capterra category page."""
        products = []
        try:
            await page.goto(category_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(2.0, 4.0))

            product_cards = await page.query_selector_all(
                "[data-testid='product-card'], .product-listing-card, article"
            )
            for card in product_cards[:15]:
                try:
                    name_el = await card.query_selector("h3, h2, [data-testid='product-name']")
                    name = (await name_el.inner_text()).strip() if name_el else None
                    if not name:
                        continue

                    link_el = await card.query_selector("a[href*='/p/'], a[href*='/reviews/']")
                    href = await link_el.get_attribute("href") if link_el else None
                    product_url = (
                        f"https://www.capterra.com{href}"
                        if href and href.startswith("/")
                        else href or category_url
                    )

                    rating_el = await card.query_selector("[data-star-rating], .rating-value, .star")
                    rating_text = None
                    if rating_el:
                        rating_text = await rating_el.get_attribute("data-star-rating") or await rating_el.inner_text()
                    try:
                        rating = float(rating_text.strip()) if rating_text else None
                    except (ValueError, AttributeError):
                        rating = None

                    products.append({"name": name, "url": product_url, "rating": rating})
                except Exception as exc:
                    logger.debug("Capterra card parse error: %s", exc)
        except Exception as exc:
            logger.warning("Capterra listing scrape failed for %s: %s", category_url, exc)
        return products

    async def _scrape_reviews(self, page: Page, product_url: str, app_name: str) -> list[dict]:
        """Scrape individual reviews for a product."""
        results = []
        reviews_url = product_url if "/reviews" in product_url else product_url.rstrip("/") + "#reviews"
        try:
            await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(1.5, 3.0))

            review_els = await page.query_selector_all(
                ".review-card, [data-testid='review'], .review-content"
            )
            for review_el in review_els[:15]:
                try:
                    body_el = await review_el.query_selector(".review-body, p, .review-text")
                    body = (await body_el.inner_text()).strip() if body_el else ""

                    pros_el = await review_el.query_selector(".pros, [class*='pros']")
                    pros_text = (await pros_el.inner_text()).strip() if pros_el else ""

                    cons_el = await review_el.query_selector(".cons, [class*='cons']")
                    cons_text = (await cons_el.inner_text()).strip() if cons_el else ""

                    content = "\n".join(filter(None, [body, pros_text, cons_text]))
                    if not content:
                        continue

                    source_id = f"capterra_{hash(product_url + content[:50])}"
                    results.append({
                        "source_id": source_id,
                        "content": content[:4000],
                        "url": product_url,
                        "raw_data": {
                            "app_name": app_name,
                            "pros": pros_text,
                            "cons": cons_text,
                            "product_url": product_url,
                        },
                    })
                except Exception as exc:
                    logger.debug("Capterra review parse error: %s", exc)
        except Exception as exc:
            logger.warning("Capterra reviews scrape failed for %s: %s", product_url, exc)
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
                for cat_url in CAPTERRA_CATEGORIES:
                    products = await self._scrape_listing(page, cat_url)
                    await asyncio.sleep(random.uniform(1.5, 3.0))

                    for product in products[:5]:
                        reviews = await self._scrape_reviews(page, product["url"], product["name"])
                        results.extend(reviews)
                        await asyncio.sleep(random.uniform(1.0, 2.5))
            finally:
                await browser.close()

        logger.info("Capterra scraper collected %d items", len(results))
        return results
