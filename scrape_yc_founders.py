#!/usr/bin/env python3
"""
YC Founder Scraper — Extract founder LinkedIn and Twitter/X links from YC companies.

Uses the yc-oss API for fast company filtering, then scrapes individual YC company
pages for founder social links.

Usage:
    python scrape_yc_founders.py --batch S24 --limit 5 --format json --output test.json
    python scrape_yc_founders.py --batch S24 --tag AI --region "United States" --format csv
    python scrape_yc_founders.py --top-companies --limit 20
"""

import argparse
import csv
import html
import json
import re
import sys
import time
from pathlib import Path

import httpx
from tqdm import tqdm

YC_OSS_BASE = "https://yc-oss.github.io/api"
YC_COMPANY_URL = "https://www.ycombinator.com/companies"

DEFAULT_DELAY = 1.0
DEFAULT_TIMEOUT = 15.0


def normalize_batch(batch: str) -> str:
    """Normalize a user-friendly batch name to the yc-oss API slug.

    Examples:
        S24 -> s24, W23 -> w23, X25 -> x25
        F24 -> fall-2024, F25 -> fall-2025
        SP25 -> spring-2025
        "Fall 2025" -> fall-2025, "Winter 2026" -> winter-2026
    """
    batch = batch.strip()

    # Full name with space: "Fall 2025" -> "fall-2025"
    if " " in batch:
        return batch.lower().replace(" ", "-")

    # SP prefix: SP25 -> spring-2025
    m = re.match(r'^[Ss][Pp](\d{2})$', batch)
    if m:
        return f"spring-20{m.group(1)}"

    # F prefix: F25 -> fall-2025
    m = re.match(r'^[Ff](\d{2})$', batch)
    if m:
        return f"fall-20{m.group(1)}"

    # S, W, X prefix: S24 -> s24, W23 -> w23, X25 -> x25
    m = re.match(r'^[SsWwXx]\d{2}$', batch)
    if m:
        return batch.lower()

    # Fallback: just lowercase
    return batch.lower()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scrape YC founder LinkedIn and Twitter/X links."
    )
    parser.add_argument("--batch",
                        help="YC batch, e.g. S24, W23, F25, SP25, 'Fall 2025'")
    parser.add_argument("--industry", help="Industry filter, e.g. B2B, Fintech")
    parser.add_argument("--tag", help="Tag filter, e.g. AI, SaaS")
    parser.add_argument("--region", help="Region filter (client-side), e.g. 'United States of America'")
    parser.add_argument("--status", help="Company status filter, e.g. Active, Inactive")
    parser.add_argument("--top-companies", action="store_true", help="Only top companies")
    parser.add_argument("--limit", type=int, help="Max number of companies to scrape")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    parser.add_argument("--format", "-f", choices=["csv", "json"], default="csv",
                        help="Output format (default: csv)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help=f"Seconds between requests (default: {DEFAULT_DELAY})")
    return parser.parse_args()


def fetch_json(client: httpx.Client, url: str) -> list[dict] | None:
    """Fetch JSON from a URL, return parsed list or None on error."""
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        print(f"  Warning: {url} returned {e.response.status_code}", file=sys.stderr)
        return None
    except httpx.RequestError as e:
        print(f"  Warning: request failed for {url}: {e}", file=sys.stderr)
        return None


def fetch_company_list(client: httpx.Client, args) -> list[dict]:
    """Fetch and filter company list from yc-oss API."""
    filter_lists = []

    # Fetch each filter source
    if args.batch:
        batch_slug = normalize_batch(args.batch)
        url = f"{YC_OSS_BASE}/batches/{batch_slug}.json"
        data = fetch_json(client, url)
        if data is not None:
            filter_lists.append({c["slug"] for c in data})
            if not filter_lists[-1]:
                print(f"  Warning: batch '{args.batch}' (slug: {batch_slug}) "
                      "returned 0 companies", file=sys.stderr)
        else:
            print(f"  Error: could not fetch batch '{args.batch}' "
                  f"(resolved to slug: {batch_slug}).", file=sys.stderr)
            return []

    if args.industry:
        url = f"{YC_OSS_BASE}/industries/{args.industry.lower()}.json"
        data = fetch_json(client, url)
        if data is not None:
            filter_lists.append({c["slug"] for c in data})
        else:
            print(f"  Error: could not fetch industry '{args.industry}'.", file=sys.stderr)
            return []

    if args.tag:
        url = f"{YC_OSS_BASE}/tags/{args.tag.lower()}.json"
        data = fetch_json(client, url)
        if data is not None:
            filter_lists.append({c["slug"] for c in data})
        else:
            print(f"  Error: could not fetch tag '{args.tag}'.", file=sys.stderr)
            return []

    if args.top_companies:
        url = f"{YC_OSS_BASE}/companies/top.json"
        data = fetch_json(client, url)
        if data is not None:
            filter_lists.append({c["slug"] for c in data})
        else:
            print("  Error: could not fetch top companies.", file=sys.stderr)
            return []

    # If any API filters were used, we need the full data for the intersected slugs.
    # Fetch the broadest list that covers our filters.
    if filter_lists:
        # Intersect all slug sets
        intersected = filter_lists[0]
        for s in filter_lists[1:]:
            intersected &= s

        # We need full company objects for client-side filtering.
        # Use the first filter's data if only one filter, otherwise fetch all.
        if len(filter_lists) == 1 and not args.region and not args.status:
            # Re-fetch the single source to get full objects
            # (we only stored slugs above for intersection)
            pass

        # Fetch all companies and filter to intersected slugs
        # This is more reliable than re-fetching individual sources
        all_url = f"{YC_OSS_BASE}/companies/all.json"
        all_data = fetch_json(client, all_url)
        if all_data is None:
            print("  Error: could not fetch all companies for filtering.", file=sys.stderr)
            return []
        companies = [c for c in all_data if c["slug"] in intersected]
    else:
        # No API filters — fetch all
        all_url = f"{YC_OSS_BASE}/companies/all.json"
        companies = fetch_json(client, all_url)
        if companies is None:
            print("  Error: could not fetch company list.", file=sys.stderr)
            return []

    # Client-side filters
    if args.region:
        region_lower = args.region.lower()
        companies = [
            c for c in companies
            if region_lower in c.get("all_locations", "").lower()
        ]

    if args.status:
        status_lower = args.status.lower()
        companies = [
            c for c in companies
            if c.get("status", "").lower() == status_lower
        ]

    # Apply limit
    if args.limit:
        companies = companies[:args.limit]

    return companies


def scrape_company_page(client: httpx.Client, slug: str) -> dict | None:
    """Scrape founder and company social details from a YC company page.

    Returns a dict with 'founders', 'company_linkedin', and 'company_twitter',
    or None on failure.
    """
    url = f"{YC_COMPANY_URL}/{slug}"
    try:
        resp = client.get(url, follow_redirects=True)
        resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"  Warning: failed to fetch {url}: {e}", file=sys.stderr)
        return None

    page_html = resp.text

    # The YC company page stores structured data in a React component's data-page attribute
    match = re.search(r'data-page="(.*?)"', page_html, re.DOTALL)
    if not match:
        print(f"  Warning: no data-page found for {slug}", file=sys.stderr)
        return None

    try:
        decoded = html.unescape(match.group(1))
        page_data = json.loads(decoded)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  Warning: failed to parse JSON for {slug}: {e}", file=sys.stderr)
        return None

    company = page_data.get("props", {}).get("company", {})

    founders = []
    for f in company.get("founders", []):
        founders.append({
            "name": f.get("full_name", ""),
            "title": f.get("title", ""),
            "linkedin": f.get("linkedin_url", ""),
            "twitter": f.get("twitter_url", ""),
        })

    return {
        "founders": founders,
        "company_linkedin": company.get("linkedin_url", ""),
        "company_twitter": company.get("twitter_url", ""),
    }


def write_csv(results: list[dict], output):
    """Write results as CSV (one row per founder)."""
    fieldnames = [
        "company", "slug", "batch", "website", "location",
        "company_linkedin", "company_twitter",
        "founder_name", "founder_title", "linkedin", "twitter",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for company in results:
        for founder in company["founders"]:
            writer.writerow({
                "company": company["name"],
                "slug": company["slug"],
                "batch": company["batch"],
                "website": company["website"],
                "location": company["location"],
                "company_linkedin": company.get("company_linkedin", ""),
                "company_twitter": company.get("company_twitter", ""),
                "founder_name": founder["name"],
                "founder_title": founder["title"],
                "linkedin": founder["linkedin"],
                "twitter": founder["twitter"],
            })


def write_json(results: list[dict], output):
    """Write results as JSON."""
    json.dump(results, output, indent=2, ensure_ascii=False)
    output.write("\n")


def main():
    args = parse_args()

    client = httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": "yc-founder-scraper/1.0"},
        follow_redirects=True,
    )

    # Phase 1: Get company list
    print("Fetching company list...", file=sys.stderr)
    companies = fetch_company_list(client, args)
    if not companies:
        print("No companies matched the given filters.", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(companies)} companies to scrape.", file=sys.stderr)

    # Phase 2: Scrape founder details
    results = []
    total_founders = 0
    failures = 0

    for company in tqdm(companies, desc="Scraping founders", file=sys.stderr):
        slug = company["slug"]
        scraped = scrape_company_page(client, slug)

        if scraped and scraped["founders"]:
            results.append({
                "name": company.get("name", ""),
                "slug": slug,
                "batch": company.get("batch", ""),
                "website": company.get("website", ""),
                "location": company.get("all_locations", ""),
                "company_linkedin": scraped["company_linkedin"],
                "company_twitter": scraped["company_twitter"],
                "founders": scraped["founders"],
            })
            total_founders += len(scraped["founders"])
        else:
            failures += 1

        time.sleep(args.delay)

    client.close()

    # Output
    if args.output:
        outpath = Path(args.output)
        with open(outpath, "w", newline="", encoding="utf-8") as f:
            if args.format == "json":
                write_json(results, f)
            else:
                write_csv(results, f)
        print(f"Wrote {outpath}", file=sys.stderr)
    else:
        if args.format == "json":
            write_json(results, sys.stdout)
        else:
            write_csv(results, sys.stdout)

    # Summary
    print(
        f"\nDone: {len(results)} companies, {total_founders} founders, "
        f"{failures} failures.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
