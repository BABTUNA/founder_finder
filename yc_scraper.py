#!/usr/bin/env python3
"""
YC Companies Founder Scraper

Scrapes founder LinkedIn and X/Twitter links from Y Combinator companies.
Supports filtering by batch, industry, and HQ region.

Usage examples:
    python yc_scraper.py
    python yc_scraper.py --batch W24
    python yc_scraper.py --industry Fintech --region "San Francisco Bay Area"
    python yc_scraper.py --batch S23 --industry Healthcare --max-companies 50
"""

import asyncio
import argparse
import csv
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


# ---------------------------------------------------------------------------
# Structured output model — Agent returns this, we write the CSV ourselves
# ---------------------------------------------------------------------------

class Founder(BaseModel):
    company_name: str = ""
    company_url: str = ""
    yc_batch: str = ""
    founder_name: str = ""
    founder_title: str = ""
    linkedin_url: str = ""
    twitter_x_url: str = ""


class FounderList(BaseModel):
    founders: list[Founder] = []


# ---------------------------------------------------------------------------
# Task prompt builder
# ---------------------------------------------------------------------------

def build_task(
    batch: str | None,
    industry: str | None,
    region: str | None,
    max_companies: int,
) -> str:
    """Build the Agent task description."""

    filter_steps = []
    if batch:
        filter_steps.append(
            f"  - Click the 'Batch' filter button and select the option '{batch}'."
            " Wait for the company list to refresh before continuing."
        )
    if industry:
        filter_steps.append(
            f"  - Click the 'Industry' filter button and select the option '{industry}'."
            " Wait for the company list to refresh before continuing."
        )
    if region:
        filter_steps.append(
            f"  - Click the 'Region' filter button and select the option '{region}'."
            " Wait for the company list to refresh before continuing."
        )

    if filter_steps:
        filter_block = "Apply these filters before collecting any companies:\n" + "\n".join(filter_steps)
    else:
        filter_block = "No filters requested — scrape all visible companies."

    return f"""
You are scraping Y Combinator company founder data. Follow every step carefully.

IMPORTANT: Do NOT write any files. Do NOT call done(). Just collect the data and
return it as structured output matching the output schema.

=== STEP 1: Navigate & Filter ===
Go to: https://www.ycombinator.com/companies

{filter_block}

=== STEP 2: Collect Company Profile URLs ===
Scroll down through the full company listing. The page uses infinite scroll — keep
scrolling until no more companies load or until you have collected at least
{max_companies} company URLs, whichever comes first.

Use JavaScript evaluation to efficiently collect all visible company links:
  evaluate("Array.from(document.querySelectorAll('a[href*=\\"/companies/\\"]')).map(a => a.href)")

Deduplicate the list. Take at most {max_companies} URLs.

=== STEP 3: Scrape Each Company Page ===
For every collected company URL:
  a. Navigate to the company page.
  b. Read the company name and YC batch (visible near the top of the page).
  c. Find the "Founders" section (usually toward the bottom of the page).
  d. For each founder listed, extract:
       - founder_name   : full name
       - founder_title  : role/title (e.g. "CEO", "CTO", "Co-founder") — empty string if not shown
       - linkedin_url   : full LinkedIn profile URL (contains "linkedin.com") — empty string if absent
       - twitter_x_url  : full X / Twitter URL (contains "twitter.com" or "x.com") — empty string if absent
       - company_name   : the company's name
       - company_url    : the YC profile URL you navigated to
       - yc_batch       : e.g. "W24", "S23" — empty string if not found

  Tips for finding social links:
    - Use: evaluate("Array.from(document.querySelectorAll('a[href*=\\"linkedin\\"], a[href*=\\"twitter\\"], a[href*=\\"x.com\\"]')).map(a => ({{href: a.href, text: a.textContent.trim()}}))")
    - Each founder card usually groups the founder's links together; map each link back
      to the nearest founder name.
    - If a company page errors or takes too long, skip it and move to the next.

=== STEP 4: Return Results ===
Return ALL collected founder records as structured output. One entry per founder.
A company with 3 founders = 3 entries in the founders list.
Leave fields as empty strings when data is missing.
""".strip()


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "company_name",
    "company_url",
    "yc_batch",
    "founder_name",
    "founder_title",
    "linkedin_url",
    "twitter_x_url",
]


def write_csv(founders: list[Founder], output_file: str) -> None:
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for founder in founders:
            writer.writerow(founder.model_dump())


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_scraper(task: str, output_file: str) -> None:
    from browser_use import Agent, Browser, ChatBrowserUse

    browser = Browser(headless=True)
    llm = ChatBrowserUse()

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        output_model_schema=FounderList,
        max_failures=5,
    )

    result = await agent.run()

    # Extract structured output from the agent result
    founder_list = result.get_structured_output(FounderList) if result else None
    founders = founder_list.founders if founder_list else []

    if founders:
        write_csv(founders, output_file)
        print(f"\nSaved {len(founders)} founders to {output_file}")
    else:
        print("\nNo founder data was returned by the agent.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape YC company founder LinkedIn/X links to CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python yc_scraper.py
  python yc_scraper.py --batch W24
  python yc_scraper.py --industry Fintech --region "San Francisco Bay Area"
  python yc_scraper.py --batch S23 --output s23_founders.csv --max-companies 200
        """,
    )

    parser.add_argument(
        "--batch", type=str, default=None, metavar="BATCH",
        help="YC batch to filter by (e.g. W24, S23, W25)",
    )
    parser.add_argument(
        "--industry", type=str, default=None, metavar="INDUSTRY",
        help="Industry to filter by (e.g. Fintech, Healthcare, B2B)",
    )
    parser.add_argument(
        "--region", type=str, default=None, metavar="REGION",
        help='HQ region to filter by (e.g. "San Francisco Bay Area", "New York")',
    )
    parser.add_argument(
        "--output", type=str, default="founders.csv", metavar="FILE",
        help="Output CSV file path (default: founders.csv)",
    )
    parser.add_argument(
        "--max-companies", type=int, default=100, metavar="N",
        help="Maximum number of companies to scrape (default: 100)",
    )

    return parser.parse_args()


def validate_env() -> bool:
    if not os.getenv("BROWSER_USE_API_KEY"):
        print("ERROR: BROWSER_USE_API_KEY is not set.")
        print("  Get a free key at https://cloud.browser-use.com/new-api-key")
        return False
    return True


async def main() -> None:
    args = parse_args()

    if not validate_env():
        sys.exit(1)

    task = build_task(
        batch=args.batch,
        industry=args.industry,
        region=args.region,
        max_companies=args.max_companies,
    )

    active_filters = [
        f"batch={args.batch}" if args.batch else None,
        f"industry={args.industry}" if args.industry else None,
        f"region={args.region}" if args.region else None,
    ]
    filter_summary = ", ".join(f for f in active_filters if f) or "none"

    print("=" * 60)
    print("YC Founder Scraper")
    print("=" * 60)
    print(f"  Filters      : {filter_summary}")
    print(f"  Max companies: {args.max_companies}")
    print(f"  Output file  : {args.output}")
    print("=" * 60)
    print()

    await run_scraper(task, args.output)


if __name__ == "__main__":
    asyncio.run(main())
