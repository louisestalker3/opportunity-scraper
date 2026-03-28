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
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

G2_CATEGORIES_URL = "https://www.g2.com/categories"


class G2Scraper(BaseScraper):
    source = "g2"

    async def _scrape_category_page(self, page: Page, category_url: str) -> list[dict]:
        """Scrape individual software reviews from a G2 category page."""
        results = []
        try:
            await page.goto(category_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(2.0, 4.0))

            # Extract product cards
            products = await page.query_selector_all("[data-testid='product-card'], .product-card, article.product")
            for product in products[:10]:
                try:
                    name_el = await product.query_selector("h3, h2, .product-name")
                    name = (await name_el.inner_text()).strip() if name_el else None
                    if not name:
                        continue

                    rating_el = await product.query_selector("[data-star-rating], .star-rating, .rating")
                    rating_text = (await rating_el.get_attribute("data-star-rating") or await rating_el.inner_text()) if rating_el else None
                    rating = float(rating_text) if rating_text else None

                    link_el = await product.query_selector("a")
                    href = await link_el.get_attribute("href") if link_el else None
                    product_url = f"https://www.g2.com{href}" if href and href.startswith("/") else href

                    results.append({
                        "app_name": name,
                        "rating": rating,
                        "product_url": product_url or category_url,
                        "review_text": "",
                        "pros": [],
                        "cons": [],
                    })
                except Exception as exc:
                    logger.debug("G2 product parse error: %s", exc)
        except Exception as exc:
            logger.warning("G2 category scrape failed for %s: %s", category_url, exc)
        return results

    async def _scrape_reviews(self, page: Page, product_url: str, app_name: str) -> list[dict]:
        """Scrape reviews for a specific product."""
        results = []
        reviews_url = product_url.rstrip("/") + "/reviews"
        try:
            await page.goto(reviews_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(1.5, 3.0))

            review_cards = await page.query_selector_all(".review, [data-testid='review'], .paper")
            for card in review_cards[:15]:
                try:
                    body_el = await card.query_selector(".review-text, .body, p")
                    body = (await body_el.inner_text()).strip() if body_el else ""

                    pros_el = await card.query_selector(".pros, [data-field='pros']")
                    pros_text = (await pros_el.inner_text()).strip() if pros_el else ""

                    cons_el = await card.query_selector(".cons, [data-field='cons']")
                    cons_text = (await cons_el.inner_text()).strip() if cons_el else ""

                    rating_el = await card.query_selector("[data-star-rating]")
                    rating_val = None
                    if rating_el:
                        raw = await rating_el.get_attribute("data-star-rating")
                        try:
                            rating_val = float(raw) if raw else None
                        except ValueError:
                            pass

                    content = "\n".join(filter(None, [body, pros_text, cons_text]))
                    if not content:
                        continue

                    # Build a pseudo source_id from URL + index
                    source_id = f"g2_{hash(reviews_url + content[:50])}"

                    results.append({
                        "source_id": source_id,
                        "content": content[:4000],
                        "url": reviews_url,
                        "raw_data": {
                            "app_name": app_name,
                            "rating": rating_val,
                            "pros": pros_text,
                            "cons": cons_text,
                            "review_url": reviews_url,
                        },
                    })
                except Exception as exc:
                    logger.debug("G2 review parse error: %s", exc)
        except Exception as exc:
            logger.warning("G2 reviews scrape failed for %s: %s", reviews_url, exc)
        return results

    async def scrape(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            page = await context.new_page()

            try:
                await page.goto(G2_CATEGORIES_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(random.uniform(2.0, 3.5))

                # Collect category links
                category_links = await page.query_selector_all("a[href*='/categories/']")
                category_urls: list[str] = []
                for link in category_links[:20]:
                    href = await link.get_attribute("href")
                    if href and "/categories/" in href:
                        full_url = f"https://www.g2.com{href}" if href.startswith("/") else href
                        if full_url not in category_urls:
                            category_urls.append(full_url)

                # Scrape top categories
                for cat_url in category_urls[:5]:
                    products = await self._scrape_category_page(page, cat_url)
                    await asyncio.sleep(random.uniform(1.0, 2.5))

                    for product in products[:5]:
                        if product.get("product_url"):
                            reviews = await self._scrape_reviews(
                                page, product["product_url"], product["app_name"]
                            )
                            results.extend(reviews)
                            await asyncio.sleep(random.uniform(1.0, 2.0))

            finally:
                await browser.close()

        logger.info("G2 scraper collected %d review items", len(results))
        return results
