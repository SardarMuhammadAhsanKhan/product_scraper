import asyncio, csv, json, re
from pathlib import Path
from playwright.async_api import async_playwright

async def scrape():
    print("Starting scraper...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        await page.goto("https://alfatah.pk/collections/buy-general-products-online")
        await page.wait_for_load_state("networkidle")
        links = await page.query_selector_all("a[href*='/products/']")
        products = []
        for link in links[:50]:
            url = await link.get_attribute("href")
            name = await link.inner_text()
            products.append({"name": name.strip(), "url": url})
        outdir = Path("output")
        outdir.mkdir(exist_ok=True)
        with open(outdir / "products_scraped.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "url"])
            writer.writeheader()
            writer.writerows(products)
        print(f"Scraped {len(products)} items.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape())
