#!/usr/bin/env python3
"""
Luma Tech Events Scraper — Extract all upcoming tech events from lu.ma.

Uses the public Luma discover API (same endpoint as lu.ma/category/tech/map)
to fetch every event in a category. The API is geo-scoped, so we query from
multiple geographic hubs worldwide to collect all events and deduplicate.

Usage:
    python scrape_luma_events.py --format json --output events.json
    python scrape_luma_events.py --format csv --output events.csv
    python scrape_luma_events.py --city "San Francisco" --format json
    python scrape_luma_events.py --limit 100 --format json
    python scrape_luma_events.py --category design --format json
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import httpx
from tqdm import tqdm

LUMA_API_BASE = "https://api.lu.ma"

DEFAULT_DELAY = 1.0
DEFAULT_TIMEOUT = 15.0
DEFAULT_PAGE_SIZE = 50
DEFAULT_CATEGORY = "tech"

def build_geo_hubs() -> list[dict]:
    """Build a list of geographic query points.

    Combines major cities with a lat/lng grid to maximize event coverage.
    The Luma API returns ~50 events per location, so we need many points.
    """
    hubs = []

    # Major cities — these are densely populated with events
    cities = [
        # North America
        ("San Francisco", 37.77, -122.42), ("San Jose", 37.34, -121.89),
        ("Los Angeles", 34.05, -118.24), ("San Diego", 32.72, -117.16),
        ("Seattle", 47.61, -122.33), ("Portland", 45.52, -122.68),
        ("New York", 40.71, -74.01), ("Boston", 42.36, -71.06),
        ("Washington DC", 38.91, -77.04), ("Philadelphia", 39.95, -75.17),
        ("Miami", 25.76, -80.19), ("Atlanta", 33.75, -84.39),
        ("Austin", 30.27, -97.74), ("Dallas", 32.78, -96.80),
        ("Houston", 29.76, -95.37), ("Chicago", 41.88, -87.63),
        ("Denver", 39.74, -104.99), ("Phoenix", 33.45, -112.07),
        ("Detroit", 42.33, -83.05), ("Minneapolis", 44.98, -93.27),
        ("Toronto", 43.65, -79.38), ("Vancouver", 49.28, -123.12),
        ("Montreal", 45.50, -73.57), ("Mexico City", 19.43, -99.13),
        # Europe
        ("London", 51.51, -0.13), ("Manchester", 53.48, -2.24),
        ("Edinburgh", 55.95, -3.19), ("Dublin", 53.35, -6.26),
        ("Paris", 48.86, 2.35), ("Lyon", 45.76, 4.84),
        ("Berlin", 52.52, 13.41), ("Munich", 48.14, 11.58),
        ("Hamburg", 53.55, 9.99), ("Frankfurt", 50.11, 8.68),
        ("Amsterdam", 52.37, 4.90), ("Brussels", 50.85, 4.35),
        ("Barcelona", 41.39, 2.17), ("Madrid", 40.42, -3.70),
        ("Lisbon", 38.72, -9.14), ("Milan", 45.46, 9.19),
        ("Rome", 41.90, 12.50), ("Vienna", 48.21, 16.37),
        ("Zurich", 47.38, 8.54), ("Stockholm", 59.33, 18.07),
        ("Copenhagen", 55.68, 12.57), ("Oslo", 59.91, 10.75),
        ("Helsinki", 60.17, 24.94), ("Warsaw", 52.23, 21.01),
        ("Prague", 50.08, 14.44), ("Budapest", 47.50, 19.04),
        ("Bucharest", 44.43, 26.10), ("Athens", 37.98, 23.73),
        ("Istanbul", 41.01, 28.98),
        # Asia
        ("Singapore", 1.35, 103.82), ("Hong Kong", 22.32, 114.17),
        ("Tokyo", 35.68, 139.65), ("Osaka", 34.69, 135.50),
        ("Seoul", 37.57, 126.98), ("Taipei", 25.03, 121.57),
        ("Beijing", 39.90, 116.41), ("Shanghai", 31.23, 121.47),
        ("Shenzhen", 22.54, 114.06), ("Bangkok", 13.76, 100.50),
        ("Jakarta", -6.21, 106.85), ("Kuala Lumpur", 3.14, 101.69),
        ("Bangalore", 12.97, 77.59), ("Mumbai", 19.08, 72.88),
        ("Delhi", 28.61, 77.21), ("Hyderabad", 17.39, 78.49),
        ("Dubai", 25.20, 55.27), ("Tel Aviv", 32.09, 34.78),
        ("Riyadh", 24.71, 46.67),
        # Oceania
        ("Sydney", -33.87, 151.21), ("Melbourne", -37.81, 144.96),
        ("Auckland", -36.85, 174.76),
        # South America
        ("São Paulo", -23.55, -46.63), ("Rio de Janeiro", -22.91, -43.17),
        ("Buenos Aires", -34.60, -58.38), ("Bogotá", 4.71, -74.07),
        ("Santiago", -33.45, -70.67), ("Lima", -12.05, -77.04),
        ("Medellín", 6.25, -75.56),
        # Africa
        ("Lagos", 6.52, 3.38), ("Nairobi", -1.29, 36.82),
        ("Cape Town", -33.93, 18.42), ("Cairo", 30.04, 31.24),
        ("Accra", 5.60, -0.19), ("Johannesburg", -26.20, 28.05),
    ]

    for name, lat, lng in cities:
        hubs.append({"name": name, "lat": lat, "lng": lng})

    # Also query without coordinates (server-default region)
    hubs.append({"name": "Default", "lat": None, "lng": None})

    return hubs


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scrape all upcoming events from a Luma category."
    )
    parser.add_argument("--category", default=DEFAULT_CATEGORY,
                        help=f"Luma category slug (default: {DEFAULT_CATEGORY})")
    parser.add_argument("--limit", type=int,
                        help="Max total number of events to collect")
    parser.add_argument("--output", "-o",
                        help="Output file path (default: stdout)")
    parser.add_argument("--format", "-f", choices=["csv", "json"], default="csv",
                        help="Output format (default: csv)")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help=f"Seconds between paginated requests (default: {DEFAULT_DELAY})")
    parser.add_argument("--city",
                        help="Filter events by city (case-insensitive substring)")
    parser.add_argument("--country",
                        help="Filter events by country in address (case-insensitive substring)")
    parser.add_argument("--free-only", action="store_true",
                        help="Only include free events")
    return parser.parse_args()


def fetch_json(client: httpx.Client, url: str, params: dict = None) -> dict | None:
    """Fetch JSON from a URL with retry on rate-limit. Returns parsed dict or None."""
    for attempt in range(4):
        try:
            resp = client.get(url, params=params)
            if resp.status_code == 403 or resp.status_code == 429:
                wait = 2 ** attempt * 5  # 5s, 10s, 20s, 40s
                print(f"\n  Rate limited ({resp.status_code}), waiting {wait}s...",
                      file=sys.stderr, end="", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            print(f"  Warning: {url} returned {e.response.status_code}", file=sys.stderr)
            return None
        except httpx.RequestError as e:
            print(f"  Warning: request failed for {url}: {e}", file=sys.stderr)
            return None
    print(f"  Warning: gave up after retries for {url}", file=sys.stderr)
    return None


def fetch_category_info(client: httpx.Client, category_slug: str) -> dict | None:
    """Fetch category metadata (name, event count, subscriber count)."""
    data = fetch_json(client, f"{LUMA_API_BASE}/url", params={"url": category_slug})
    if data is None or data.get("kind") != "category":
        print(f"  Error: '{category_slug}' is not a valid Luma category.", file=sys.stderr)
        return None
    return data["data"]["category"]


def parse_event_entry(entry: dict) -> dict:
    """Extract flat event dict from an API entry."""
    event = entry.get("event", {})
    geo = event.get("geo_address_info") or {}
    ticket = entry.get("ticket_info") or {}
    price = ticket.get("price") or {}
    calendar = entry.get("calendar") or {}

    return {
        "event_name": event.get("name", ""),
        "event_url": f"https://lu.ma/{event['url']}" if event.get("url") else "",
        "start_at": event.get("start_at", ""),
        "end_at": event.get("end_at", ""),
        "timezone": event.get("timezone", ""),
        "location_type": event.get("location_type", ""),
        "city": geo.get("city", ""),
        "region": geo.get("region", ""),
        "country": geo.get("country", ""),
        "full_address": geo.get("full_address", ""),
        "latitude": geo.get("latitude", ""),
        "longitude": geo.get("longitude", ""),
        "is_free": ticket.get("is_free"),
        "price_cents": price.get("cents"),
        "currency": price.get("currency", ""),
        "is_sold_out": ticket.get("is_sold_out", False),
        "guest_count": entry.get("guest_count", 0),
        "hosts": ", ".join(
            h.get("name", "") for h in entry.get("hosts", []) if h.get("name")
        ),
        "calendar_name": calendar.get("name", ""),
        "calendar_slug": calendar.get("slug", ""),
        "cover_url": event.get("cover_url", ""),
    }


def fetch_events_from_hub(
    client: httpx.Client,
    category_slug: str,
    seen_urls: set,
    lat: float | None = None,
    lng: float | None = None,
    delay: float = DEFAULT_DELAY,
    limit: int | None = None,
) -> list[dict]:
    """Fetch events from the discover API for a single geo hub."""
    events = []
    cursor = None
    seen_cursors: set[str] = set()

    while True:
        params = {
            "category_slug": category_slug,
            "pagination_limit": DEFAULT_PAGE_SIZE,
        }
        if cursor:
            params["after"] = cursor
        if lat is not None and lng is not None:
            params["latitude"] = lat
            params["longitude"] = lng

        data = fetch_json(
            client,
            f"{LUMA_API_BASE}/discover/get-paginated-events",
            params=params,
        )
        if data is None:
            break

        entries = data.get("entries", [])
        if not entries:
            break

        for entry in entries:
            parsed = parse_event_entry(entry)
            url = parsed["event_url"]
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            events.append(parsed)

            if limit and len(events) >= limit:
                return events

        if not data.get("has_more"):
            break

        new_cursor = data.get("next_cursor")
        if not new_cursor or new_cursor in seen_cursors:
            break
        seen_cursors.add(new_cursor)
        cursor = new_cursor

        time.sleep(delay)

    return events


def fetch_all_events(
    client: httpx.Client,
    category_slug: str,
    limit: int | None = None,
    delay: float = DEFAULT_DELAY,
) -> list[dict]:
    """Fetch all events by querying from multiple geographic hubs."""
    all_events = []
    seen_urls: set[str] = set()
    hubs = build_geo_hubs()
    stale_streak = 0  # consecutive hubs with 0 new events

    with tqdm(desc="Fetching events", unit=" events", total=limit, file=sys.stderr) as pbar:
        for hub in hubs:
            hub_events = fetch_events_from_hub(
                client, category_slug, seen_urls,
                lat=hub["lat"], lng=hub["lng"],
                delay=delay,
                limit=(limit - len(all_events)) if limit else None,
            )

            new_count = len(hub_events)
            if new_count > 0:
                all_events.extend(hub_events)
                pbar.update(new_count)
                pbar.set_postfix(hub=hub["name"], new=new_count)
                stale_streak = 0
            else:
                stale_streak += 1

            # If many consecutive hubs return 0 new events, we've likely
            # exhausted the category
            if stale_streak >= 10:
                break

            if limit and len(all_events) >= limit:
                break

    return all_events


def write_csv(events: list[dict], output):
    """Write events as CSV."""
    if not events:
        return
    fieldnames = [
        "event_name", "event_url", "start_at", "end_at", "timezone",
        "location_type", "city", "region", "country", "full_address",
        "latitude", "longitude", "is_free", "price_cents", "currency",
        "is_sold_out", "guest_count", "hosts", "calendar_name",
        "calendar_slug", "cover_url",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(events)


def write_json(events: list[dict], output):
    """Write events as JSON."""
    json.dump(events, output, indent=2, ensure_ascii=False)
    output.write("\n")


def main():
    args = parse_args()

    client = httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": "luma-event-scraper/1.0"},
        follow_redirects=True,
    )

    # Fetch category info for display
    print(f"Fetching category '{args.category}'...", file=sys.stderr)
    cat_info = fetch_category_info(client, args.category)
    if not cat_info:
        sys.exit(1)

    expected = cat_info["event_count"]
    print(
        f"Category: {cat_info['name']} — "
        f"{expected} upcoming events, "
        f"{cat_info['subscriber_count']} subscribers",
        file=sys.stderr,
    )
    if not args.city:
        print(
            f"Querying {len(build_geo_hubs())} geographic hubs to collect all events...\n",
            file=sys.stderr,
        )

    # If a city filter is specified, try to find matching hub coordinates
    # to query directly instead of scanning all hubs
    city_hub = None
    if args.city:
        city_lower = args.city.lower()
        for hub in build_geo_hubs():
            if hub["lat"] is not None and city_lower in hub["name"].lower():
                city_hub = hub
                break

    if city_hub:
        print(f"Querying near {city_hub['name']}...\n", file=sys.stderr)
        seen_urls: set[str] = set()
        all_events = fetch_events_from_hub(
            client, args.category, seen_urls,
            lat=city_hub["lat"], lng=city_hub["lng"],
            delay=args.delay, limit=args.limit,
        )
    else:
        all_events = fetch_all_events(
            client, args.category,
            limit=args.limit, delay=args.delay,
        )

    client.close()

    # Post-fetch filters
    if args.city:
        city_lower = args.city.lower()
        all_events = [e for e in all_events if city_lower in (e.get("city") or "").lower()]

    if args.country:
        country_lower = args.country.lower()
        all_events = [
            e for e in all_events
            if country_lower in (e.get("country") or "").lower()
        ]

    if args.free_only:
        all_events = [e for e in all_events if e.get("is_free") is True]

    # Sort by start time
    all_events.sort(key=lambda e: e.get("start_at") or "")

    # Output
    if not all_events:
        print("\nNo events found.", file=sys.stderr)
        sys.exit(0)

    if args.output:
        outpath = Path(args.output)
        with open(outpath, "w", newline="", encoding="utf-8") as f:
            if args.format == "json":
                write_json(all_events, f)
            else:
                write_csv(all_events, f)
        print(f"\nWrote {outpath}", file=sys.stderr)
    else:
        if args.format == "json":
            write_json(all_events, sys.stdout)
        else:
            write_csv(all_events, sys.stdout)

    coverage = f" ({len(all_events)}/{expected} = {len(all_events)*100//expected}%)" if expected else ""
    print(f"\nDone: {len(all_events)} unique events{coverage}.", file=sys.stderr)


if __name__ == "__main__":
    main()
