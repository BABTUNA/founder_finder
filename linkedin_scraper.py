#!/usr/bin/env python3
"""
LinkedIn Company Scraper — Playwright Browser Automation

Opens a real Chrome browser to a LinkedIn company page and scrapes:
  - Company location (headquarters)
  - Number of job openings (if any)
  - Total associated members
  - Top 3 categories (specialties / industry)
  - Top 3 locations where employees live

Usage:
    python linkedin_scraper.py "https://www.linkedin.com/company/openai"
    python linkedin_scraper.py "https://www.linkedin.com/company/openai" --headless
    python linkedin_scraper.py "https://www.linkedin.com/company/openai" -o company_info.json
    python linkedin_scraper.py --file companies.txt -o results.json

Dependencies:
    pip install playwright && playwright install chromium
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright


# ---------------------------------------------------------------------------
# Scraping logic
# ---------------------------------------------------------------------------


async def scrape_linkedin_company(page, url: str) -> dict:
    """Navigate to a LinkedIn company page and extract key info."""
    result = {
        "url": url,
        "company_name": "",
        "location": "",
        "job_count": 0,
        "associated_members": "",
        "top_categories": [],
        "top_employee_locations": [],
        "scraped_at": datetime.now().isoformat(),
    }

    print(f"\n  Navigating to {url} ...", file=sys.stderr)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        # TODO: extract fields
    except Exception as e:
        print(f"  Error scraping {url}: {e}", file=sys.stderr)
        result["error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Main scraper orchestration
# ---------------------------------------------------------------------------


async def scrape(urls: list[str], headless: bool = False) -> list[dict]:
    """Open each LinkedIn company page in a browser and scrape info."""
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            for i, url in enumerate(urls):
                print(f"\n[{i+1}/{len(urls)}] Scraping: {url}", file=sys.stderr)
                data = await scrape_linkedin_company(page, url)
                results.append(data)

                # Brief pause between companies to avoid rate limits
                if i < len(urls) - 1:
                    print("  Waiting before next company...", file=sys.stderr)
                    await page.wait_for_timeout(3000)

        except KeyboardInterrupt:
            print(f"\nInterrupted — saving {len(results)} results so far.",
                  file=sys.stderr)
        finally:
            await browser.close()

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="LinkedIn company page scraper — Playwright browser automation."
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="One or more LinkedIn company URLs to scrape",
    )
    parser.add_argument(
        "--file",
        help="Text file with one LinkedIn company URL per line",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (no visible window)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["csv", "json"],
        default="json",
        help="Output format (default: json)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    urls = list(args.urls or [])

    # Load URLs from file if provided
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)

    if not urls:
        print("Error: provide at least one LinkedIn company URL (or use --file).",
              file=sys.stderr)
        sys.exit(1)

    # Normalize URLs
    normalized = []
    for u in urls:
        u = u.strip().rstrip("/")
        if not u.startswith("http"):
            u = "https://www.linkedin.com/company/" + u
        normalized.append(u)

    print(f"Scraping {len(normalized)} LinkedIn company page(s)...", file=sys.stderr)
    results = asyncio.run(scrape(normalized, headless=args.headless))

    print(f"\nTotal: {len(results)} companies scraped", file=sys.stderr)
    # TODO: write output
    json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
