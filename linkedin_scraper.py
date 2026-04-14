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
    # TODO: call scraper
    print("Scraper not yet implemented.", file=sys.stderr)


if __name__ == "__main__":
    main()
