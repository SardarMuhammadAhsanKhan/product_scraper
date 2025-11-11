import asyncio
import csv
import os
import re
from pathlib import Path
import sys
import requests
import json  # Import the json library
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# --- Sitemap Functions (Fast URL Fetching) ---
# (These are unchanged and still work)

SITEMAP_INDEX_URL = "https://alfatah.pk/sitemap.xml"

def get_product_sitemap_urls(index_url):
    """Fetches the main sitemap and finds all product sitemap URLs."""
    print(f"Fetching sitemap index from {index_url}...")
    try:
        r = requests.get(index_url)
        r.raise_for_status()
        # Requires 'lxml' to be in requirements.txt
        soup = BeautifulSoup(r.text, 'xml')
        sitemap_urls = [loc.text for loc in soup.find_all('loc') if 'sitemap_products' in loc.text]
        print(f"Found {len(sitemap_urls)} product sitemaps.")
        return sitemap_urls
    except requests.RequestException as e:
        print(f"Error fetching sitemap index: {e}")
        return []

def get_all_product_links_from_sitemaps(sitemap_urls):
    """Scrapes all product URLs from the list of product sitemaps."""
    product_links = []
    print(f"Processing {len(sitemap_urls)} sitemaps to get product links...")
    for url in sitemap_urls:
        try:
            r = requests.get(url)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'xml')
            
            for tag in soup.find_all('url'):
                loc_tag = tag.find('loc')
                if loc_tag and '/products/' in loc_tag.text:
                    product_links.append(loc_tag.text)
        except requests.RequestException as e:
            print(f"Error fetching sitemap {url}: {e}")
            
    print(f"Found a total of {len(product_links)} product links from all sitemaps.")
    return product_links

# --- Playwright Scraper (NEW ROBUST VERSION) ---

async def scrape_product_page(page, url):
    """
    Scrapes detailed data from a single product page
    by parsing the JSON-LD structured data.
    """
    print(f"  Scraping page: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"  Error navigating to {url}: {e}")
        return None

    try:
        # This selector finds the structured data script
        script_selector = 'script[type="application/ld+json"]'
        script_elements = await page.query_selector_all(script_selector)
        
        if not script_elements:
            print(f"  No JSON-LD script found on {url}")
            return None

        for element in script_elements:
            json_text = await element.inner_text()
            data = json.loads(json_text)
            
            # Find the JSON block that is about a "Product"
            # Sometimes it's a list, sometimes a single object
            data_list = [data] if not isinstance(data, list) else data
            
            for item in data_list:
                if item.get('@type') == 'Product':
                    # Found the product data block, now extract it
                    name = item.get('name', 'N/A')
                    sku = item.get('sku', 'N/A')
                    description = item.get('description', 'N/A').replace("\n", " ").strip()
                    
                    price = 'N/A'
                    price_currency = 'N/A'
                    availability = 'N/A'
                    
                    # Offers can be an object or a list
                    offers = item.get('offers')
                    if isinstance(offers, list):
                        offers = offers[0] # Get the first offer
                    
                    if offers:
                        price = offers.get('price', 'N/A')
                        price_currency = offers.get('priceCurrency', 'N/A')
                        
                        # Clean up availability
                        raw_availability = offers.get('availability', 'N/A')
                        if 'InStock' in raw_availability:
                            availability = 'In Stock'
                        elif 'OutOfStock' in raw_availability:
                            availability = 'Out of Stock'
                        else:
                            availability = raw_availability

                    return {
                        "name": name,
                        "url": url,
                        "price": price,
                        "price_currency": price_currency,
                        "sku": sku,
                        "availability": availability,
                        "description": description
                    }
        
        print(f"  Found JSON-LD but no '@type': 'Product' on {url}")
        return None

    except Exception as e:
        print(f"  Error parsing JSON-LD from {url}: {e}")
        return None


async def main():
    print("Starting scraper...")
    
    try:
        max_products_str = os.environ.get("MAX_PRODUCTS", "20")
        max_products = int(max_products_str)
    except ValueError:
        print(f"Invalid MAX_PRODUCTS value: {max_products_str}. Defaulting to 20.")
        max_products = 20

    print(f"Targeting a maximum of {max_products} products.")

    # 1. Get all product URLs from sitemaps (fast)
    sitemap_urls = get_product_sitemap_urls(SITEMAP_INDEX_URL)
    if not sitemap_urls:
        print("No sitemaps found. Exiting.")
        return

    product_links = get_all_product_links_from_sitemaps(sitemap_urls)
    if not product_links:
        print("No product links found in sitemaps. Exiting.")
        return
        
    links_to_scrape = product_links[:max_products]
    print(f"Will scrape detailed data for {len(links_to_scrape)} products.")

    # 2. Scrape each product page for details (slow)
    all_products_data = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        
        for i, link in enumerate(links_to_scrape):
            print(f"Processing item {i+1}/{len(links_to_scrape)}...")
            data = await scrape_product_page(page, link)
            if data:
                all_products_data.append(data)
        
        await browser.close()

    # 3. Save to CSV
    if not all_products_data:
        print("No product data was successfully scraped.")
        return
        
    outdir = Path("output")
    outdir.mkdir(exist_ok=True)
    filepath = outdir / "products_scraped.csv"
    
    # NEW fieldnames for the CSV
    fieldnames = ["name", "url", "price", "price_currency", "sku", "availability", "description"]
    
    try:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_products_data)
            
        print(f"\nSuccessfully scraped and saved {len(all_products_data)} product items to {filepath}")
    except Exception as e:
        print(f"Error writing to CSV: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
