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

        # Dismiss any login modals / overlays that might pop up
        await _dismiss_overlays(page)
        await page.wait_for_timeout(1000)

        # --- Company Name ---
        result["company_name"] = await _extract_company_name(page)
        print(f"  Company: {result['company_name']}", file=sys.stderr)

        # --- Location (headquarters) ---
        result["location"] = await _extract_location(page)
        print(f"  Location: {result['location']}", file=sys.stderr)

        # --- Associated members ---
        result["associated_members"] = await _extract_members(page)
        print(f"  Members: {result['associated_members']}", file=sys.stderr)

        # --- Job count ---
        result["job_count"] = await _extract_job_count(page)
        print(f"  Jobs: {result['job_count']}", file=sys.stderr)

        # --- Navigate to About page for categories / specialties ---
        about_url = url.rstrip("/") + "/about/"
        print(f"  Opening About page...", file=sys.stderr)
        await page.goto(about_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await _dismiss_overlays(page)

        result["top_categories"] = await _extract_categories(page)
        print(f"  Categories: {result['top_categories']}", file=sys.stderr)

        # Fallback location from About page if main page missed it
        result["location"] = result["location"] or await _extract_location_about(page)

        # --- Navigate to People page for employee locations ---
        people_url = url.rstrip("/") + "/people/"
        print(f"  Opening People page for employee locations...", file=sys.stderr)
        await page.goto(people_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await _dismiss_overlays(page)

        result["top_employee_locations"] = await _extract_employee_locations(page)
        print(f"  Employee locations: {result['top_employee_locations']}", file=sys.stderr)

    except Exception as e:
        print(f"  Error scraping {url}: {e}", file=sys.stderr)
        result["error"] = str(e)

    return result


async def _dismiss_overlays(page):
    """Try to close login modals and cookie banners."""
    dismiss_selectors = [
        "button.modal__dismiss",
        "[data-tracking-control-name='public_jobs_contextual-sign-in-modal_modal_dismiss']",
        ".contextual-sign-in-modal__modal-dismiss",
        ".artdeco-modal__dismiss",
        "button[aria-label='Dismiss']",
        "button[aria-label='Close']",
    ]
    for sel in dismiss_selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click(timeout=1000)
                await page.wait_for_timeout(500)
        except Exception:
            pass


async def _extract_company_name(page) -> str:
    """Get company name from the page header."""
    selectors = [
        "h1.top-card-layout__title",
        "h1[class*='org-top-card']",
        "h1",
        "span.top-card-layout__title",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=1000):
                text = (await el.inner_text()).strip()
                if text:
                    return text
        except Exception:
            continue
    return ""


async def _extract_location(page) -> str:
    """Extract headquarters location from main company page."""
    try:
        location_text = await page.evaluate("""() => {
            // Method 1: subtitle area near company header
            const subtitles = document.querySelectorAll(
                '.top-card-layout__first-subline, [class*="top-card"] .top-card-layout__first-subline'
            );
            for (const el of subtitles) {
                const text = el.innerText || '';
                const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
                for (const line of lines) {
                    if (!line.match(/follower|employee|member/i) && line.includes(',')) {
                        return line;
                    }
                }
            }

            // Method 2: dedicated headquarters element
            const allText = document.body.innerText;
            const hqMatch = allText.match(/(?:Headquarters|headquartered in|HQ)[:\\s]+([^\\n]+)/i);
            if (hqMatch) return hqMatch[1].trim();

            // Method 3: info section below header
            const infoItems = document.querySelectorAll(
                '.org-top-card-summary-info-list__info-item, [class*="info-item"]'
            );
            for (const item of infoItems) {
                const text = (item.innerText || '').trim();
                if (text.includes(',') && !text.match(/follower|employee|member|\\d+\\s/i)) {
                    return text;
                }
            }

            return '';
        }""")
        return location_text.strip() if location_text else ""
    except Exception:
        return ""


async def _extract_members(page) -> str:
    """Extract associated members count."""
    try:
        members = await page.evaluate("""() => {
            const body = document.body.innerText;

            const patterns = [
                /(\d[\d,]+)\s+associated\s+member/i,
                /(\d[\d,]+)\s+member/i,
                /(\d[\d,]+)\s+employees? on LinkedIn/i,
                /(\d[\d,]+)\s+employees?/i,
            ];

            for (const pat of patterns) {
                const m = body.match(pat);
                if (m) return m[1];
            }

            // Check specific elements
            const els = document.querySelectorAll(
                '[class*="face-pile"], [class*="member"], [class*="employee"]'
            );
            for (const el of els) {
                const text = (el.innerText || '').trim();
                const m = text.match(/(\d[\d,]+)/);
                if (m) return m[1];
            }

            return '';
        }""")
        return members.strip() if members else ""
    except Exception:
        return ""


async def _extract_job_count(page) -> int:
    """Extract the number of job openings."""
    try:
        count = await page.evaluate("""() => {
            const body = document.body.innerText;

            const patterns = [
                /See all\s+(\d[\d,]*)\s+jobs?/i,
                /(\d[\d,]*)\s+job openings?/i,
                /(\d[\d,]*)\s+jobs? at/i,
                /(\d[\d,]*)\s+open positions?/i,
            ];

            for (const pat of patterns) {
                const m = body.match(pat);
                if (m) return parseInt(m[1].replace(/,/g, ''), 10);
            }

            // Check job links/buttons
            const jobLinks = document.querySelectorAll('a[href*="/jobs"]');
            for (const link of jobLinks) {
                const text = (link.innerText || '').trim();
                const m = text.match(/(\d[\d,]*)/);
                if (m) return parseInt(m[1].replace(/,/g, ''), 10);
            }

            return 0;
        }""")
        return count if isinstance(count, int) else 0
    except Exception:
        return 0


async def _extract_categories(page) -> list:
    """Extract top 3 specialties/categories from the About page."""
    try:
        cats = await page.evaluate("""() => {
            const body = document.body.innerText;

            // Method 1: "Specialties" section
            const specMatch = body.match(
                /Specialties[\\s\\n]+([\\s\\S]*?)(?=\\n\\n|Company size|Headquarters|Founded|Type|$)/i
            );
            if (specMatch) {
                const raw = specMatch[1].trim();
                const items = raw.split(/[,\\n]/)
                    .map(s => s.trim())
                    .filter(s => s && s.length < 80);
                return items.slice(0, 3);
            }

            // Method 2: "Industries" or "Industry"
            const indMatch = body.match(/Industr(?:y|ies)[\\s\\n]+([^\\n]+)/i);
            if (indMatch) {
                const items = indMatch[1].split(',').map(s => s.trim()).filter(Boolean);
                return items.slice(0, 3);
            }

            // Method 3: category tags
            const tags = document.querySelectorAll(
                '[class*="tag"], [class*="category"], [class*="industry"]'
            );
            const result = [];
            for (const tag of tags) {
                const text = (tag.innerText || '').trim();
                if (text && text.length < 60 && !text.match(/follow|see|show/i)) {
                    result.push(text);
                }
                if (result.length >= 3) break;
            }
            return result;
        }""")
        return cats[:3] if cats else []
    except Exception:
        return []


async def _extract_location_about(page) -> str:
    """Extract headquarters location from the About page as fallback."""
    try:
        loc = await page.evaluate("""() => {
            const allText = document.body.innerText;

            // Look for "Headquarters" label
            const hqMatch = allText.match(/Headquarters[\\s\\n]+([^\\n]+)/i);
            if (hqMatch) return hqMatch[1].trim();

            // Look for "Locations" section
            const locMatch = allText.match(
                /Locations?[\\s\\n]+(?:Primary[\\s\\n]+)?([^\\n]+)/i
            );
            if (locMatch) return locMatch[1].trim();

            return '';
        }""")
        return loc.strip() if loc else ""
    except Exception:
        return ""


async def _extract_employee_locations(page) -> list:
    """Extract top 3 locations where employees live from People page."""
    try:
        locations = await page.evaluate("""() => {
            const body = document.body.innerText;

            // Method 1: "Where they live" section
            const whereMatch = body.match(/Where they live[\\s\\n]+((?:[^\\n]+\\n?){1,10})/i);
            if (whereMatch) {
                const raw = whereMatch[1].trim();
                const lines = raw.split('\\n').map(s => s.trim()).filter(s => {
                    return s && !s.match(/^show more|^see |^\\d+$/i) && s.length < 100;
                });
                const result = [];
                for (const line of lines) {
                    if (line && result.length < 3) {
                        result.push(line);
                    }
                }
                return result;
            }

            // Method 2: location distribution in insights
            const insightSections = document.querySelectorAll(
                '[class*="insight"], [class*="distribution"]'
            );
            for (const section of insightSections) {
                const text = (section.innerText || '').trim();
                if (text.toLowerCase().includes('where')
                    || text.toLowerCase().includes('location')) {
                    const lines = text.split('\\n').map(s => s.trim()).filter(s => {
                        return s && !s.match(/^where|^show|^see /i)
                            && s.length > 2 && s.length < 100;
                    });
                    return lines.slice(0, 3);
                }
            }

            return [];
        }""")
        return locations[:3] if locations else []
    except Exception:
        return []


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
# Output helpers
# ---------------------------------------------------------------------------


def write_output(results: list[dict], output_path: str | None, fmt: str):
    """Write results to file or stdout."""
    if not results:
        print("No results to write.", file=sys.stderr)
        return

    if fmt == "csv":
        import csv
        fieldnames = [
            "company_name", "url", "location", "job_count",
            "associated_members", "top_categories", "top_employee_locations",
            "scraped_at",
        ]
        # Flatten list fields for CSV
        for r in results:
            r["top_categories"] = "; ".join(r.get("top_categories", []))
            r["top_employee_locations"] = "; ".join(r.get("top_employee_locations", []))

        if output_path:
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(results)
        else:
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)
    else:
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
                f.write("\n")
        else:
            json.dump(results, sys.stdout, indent=2, ensure_ascii=False)
            sys.stdout.write("\n")

    if output_path:
        print(f"Wrote {len(results)} results to {output_path}", file=sys.stderr)


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
    write_output(results, args.output, args.format)


if __name__ == "__main__":
    main()
