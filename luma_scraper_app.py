#!/usr/bin/env python3
"""
Luma Map Scraper — Playwright Browser Automation

Opens a real Chrome browser to lu.ma/category/tech/map, navigates the Mapbox GL
map to target cities, clicks cluster markers, and intercepts the API responses
to capture event data automatically.

Usage:
    python luma_scraper_app.py                          # All default cities
    python luma_scraper_app.py --city "San Francisco"   # Single city
    python luma_scraper_app.py --headless               # No visible browser
    python luma_scraper_app.py -o events.json           # Output file
    python luma_scraper_app.py -f csv -o events.csv     # CSV output
    python luma_scraper_app.py --merge a.json b.json -o combined.json

Dependencies:
    pip install playwright && playwright install chromium
"""

import argparse
import asyncio
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LUMA_MAP_URL = "https://lu.ma/category/tech/map"

FIELDNAMES = [
    "event_name", "event_url", "start_at", "end_at", "timezone",
    "location_type", "city", "region", "country", "full_address",
    "latitude", "longitude", "is_free", "price_cents", "currency",
    "is_sold_out", "guest_count", "hosts", "calendar_name",
    "calendar_slug", "cover_url",
]

# ---------------------------------------------------------------------------
# City hubs for scraping
# ---------------------------------------------------------------------------

CITY_HUBS = [
    ("San Francisco", 37.77, -122.42),
    ("New York", 40.71, -74.01),
    ("London", 51.51, -0.13),
    ("Berlin", 52.52, 13.41),
    ("Paris", 48.86, 2.35),
    ("Singapore", 1.35, 103.82),
    ("Tokyo", 35.68, 139.65),
    ("Austin", 30.27, -97.74),
    ("Los Angeles", 34.05, -118.24),
    ("Toronto", 43.65, -79.38),
    ("Amsterdam", 52.37, 4.90),
    ("Dubai", 25.20, 55.27),
    ("Sydney", -33.87, 151.21),
    ("Bangalore", 12.97, 77.59),
    ("Seoul", 37.57, 126.98),
    ("Tel Aviv", 32.09, 34.78),
]

# ---------------------------------------------------------------------------
# Event parsing (same as scrape_luma_events.py)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Playwright scraper
# ---------------------------------------------------------------------------


async def scrape(cities: list[tuple], headless: bool = False) -> list[dict]:
    """Open Luma map in a browser, navigate to cities, and capture events."""
    captured: dict[str, dict] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})

        # Intercept API responses for event data
        async def on_response(resp):
            if "discover/get-paginated-events" not in resp.url:
                return
            try:
                data = await resp.json()
                for entry in data.get("entries", []):
                    parsed = parse_event_entry(entry)
                    url = parsed["event_url"]
                    if url and url not in captured:
                        captured[url] = parsed
            except Exception:
                pass

        page.on("response", on_response)

        print(f"Opening {LUMA_MAP_URL} ...", file=sys.stderr)
        await page.goto(LUMA_MAP_URL, wait_until="networkidle")

        # Wait for the Mapbox GL map to be ready
        try:
            await page.wait_for_function(
                """() => {
                    const canvases = document.querySelectorAll('.mapboxgl-canvas');
                    return canvases.length > 0;
                }""",
                timeout=15000,
            )
        except Exception:
            print("Warning: Mapbox canvas not detected, continuing anyway...",
                  file=sys.stderr)

        # Give the initial map load a moment to settle
        await page.wait_for_timeout(3000)
        before = len(captured)
        print(f"  Initial load captured {before} events", file=sys.stderr)

        try:
            for name, lat, lng in cities:
                print(f"\nNavigating to {name} ({lat}, {lng})...", file=sys.stderr)
                before_city = len(captured)

                # Try multiple zoom levels to maximize coverage
                for zoom in [12, 13, 14]:
                    prev = len(captured)
                    await _fly_to(page, lat, lng, zoom=zoom)
                    await page.wait_for_timeout(3500)

                    # Click each marker and scroll the sidebar it opens
                    await _click_and_scroll_markers(page, captured)

                    gained = len(captured) - prev
                    if zoom > 12 and gained == 0:
                        break  # No new events at higher zoom, stop

                new_count = len(captured) - before_city
                print(f"  {name}: +{new_count} new events ({len(captured)} total)",
                      file=sys.stderr)
        except (KeyboardInterrupt, Exception) as e:
            if not isinstance(e, KeyboardInterrupt):
                print(f"\nError: {e}", file=sys.stderr)
            print(f"\nInterrupted — saving {len(captured)} events captured so far.",
                  file=sys.stderr)
        finally:
            await browser.close()

    events = list(captured.values())
    events.sort(key=lambda e: e.get("start_at") or "")
    return events


async def _fly_to(page, lat: float, lng: float, zoom: int = 12):
    """Navigate the Mapbox GL map to a lat/lng at the given zoom level."""
    await page.evaluate(f"""() => {{
        // Find the Mapbox GL map instance
        let mbMap = null;

        // Method 1: check canvas element
        const canvas = document.querySelector('.mapboxgl-canvas');
        if (canvas && canvas.__mapbox_map) {{
            mbMap = canvas.__mapbox_map;
        }}

        // Method 2: check window globals
        if (!mbMap && window.mapboxgl_map) {{
            mbMap = window.mapboxgl_map;
        }}

        // Method 3: check the map container
        if (!mbMap) {{
            const container = document.querySelector('.mapboxgl-map');
            if (container && container.__mapbox_map) {{
                mbMap = container.__mapbox_map;
            }}
        }}

        // Method 4: React fiber tree traversal
        if (!mbMap) {{
            const mapEl = document.querySelector('.mapboxgl-map');
            if (mapEl) {{
                const key = Object.keys(mapEl).find(k => k.startsWith('__reactFiber'));
                if (key) {{
                    let fiber = mapEl[key];
                    for (let i = 0; i < 50 && fiber; i++) {{
                        const props = fiber.memoizedProps || {{}};
                        for (const v of Object.values(props)) {{
                            if (v && typeof v === 'object' && typeof v.flyTo === 'function') {{
                                mbMap = v;
                                break;
                            }}
                        }}
                        if (mbMap) break;
                        fiber = fiber.return;
                    }}
                }}
            }}
        }}

        // Method 5: search all window properties
        if (!mbMap) {{
            for (const key of Object.keys(window)) {{
                try {{
                    const val = window[key];
                    if (val && typeof val === 'object' && typeof val.flyTo === 'function'
                        && typeof val.getCenter === 'function') {{
                        mbMap = val;
                        break;
                    }}
                }} catch(e) {{}}
            }}
        }}

        if (mbMap) {{
            mbMap.flyTo({{center: [{lng}, {lat}], zoom: {zoom}, speed: 3}});
            return true;
        }}
        return false;
    }}""")


async def _click_and_scroll_markers(page, captured: dict):
    """Click each visible marker, then scroll the sidebar it opens."""
    selectors = [
        ".mapboxgl-marker",
        "[class*='marker']",
        "[class*='cluster']",
        "[class*='MapMarker']",
        "[class*='map-pin']",
    ]

    markers = []
    for selector in selectors:
        try:
            found = await page.query_selector_all(selector)
            if found:
                markers = found
                break
        except Exception:
            continue

    if not markers:
        print("  No markers found", file=sys.stderr)
        return

    visible_markers = []
    for m in markers[:25]:
        try:
            if await m.is_visible():
                visible_markers.append(m)
        except Exception:
            continue

    print(f"  Found {len(visible_markers)} visible markers", file=sys.stderr)

    for i, marker in enumerate(visible_markers):
        before = len(captured)
        try:
            await marker.click(timeout=2000)
        except Exception:
            continue

        # Brief wait for sidebar to open and initial API response
        await page.wait_for_timeout(1500)

        # Now scroll the sidebar that opened (if it's scrollable)
        await _scroll_sidebar_once(page, captured)

        after = len(captured)
        gained = after - before
        if gained > 0:
            print(f"    Marker {i+1}: +{gained} events", file=sys.stderr)


async def _scroll_sidebar_once(page, captured: dict):
    """Find the current scrollable sidebar and scroll it to exhaust pagination.

    Single-event panels have no scrollable container — we detect and skip them
    gracefully so clicking a lone-event marker never crashes the scraper.
    """
    # Find a scrollable panel — look for divs with overflow scroll/auto
    try:
        sidebar = await page.evaluate_handle("""() => {
            const divs = document.querySelectorAll('div');
            let best = null;
            let bestHeight = 0;
            for (const d of divs) {
                const style = getComputedStyle(d);
                const overflowY = style.overflowY;
                if ((overflowY === 'auto' || overflowY === 'scroll')
                    && d.scrollHeight > d.clientHeight + 50
                    && d.clientHeight > 150
                    && d.clientHeight < window.innerHeight * 0.95) {
                    if (d.clientHeight > bestHeight) {
                        best = d;
                        bestHeight = d.clientHeight;
                    }
                }
            }
            return best;
        }""")
    except Exception:
        return  # JS evaluation failed — single-event panel or no panel

    # Check if we got a valid element (not null / undefined)
    try:
        is_null = await sidebar.evaluate("el => el === null || el === undefined")
        if is_null:
            return  # No scrollable container — single-event detail panel
    except Exception:
        return

    stale = 0
    for _ in range(50):  # Hard limit on scroll iterations
        before = len(captured)
        try:
            at_bottom = await sidebar.evaluate(
                "el => el.scrollTop + el.clientHeight >= el.scrollHeight - 10"
            )
            if at_bottom and stale >= 1:
                break  # Already at bottom and no new events last time
            await sidebar.evaluate("el => el.scrollBy(0, el.clientHeight)")
        except Exception:
            break  # Element detached (panel closed) — stop scrolling

        await page.wait_for_timeout(1200)

        after = len(captured)
        if after > before:
            stale = 0
        else:
            stale += 1
            if stale >= 2:
                break  # 2 consecutive scrolls with nothing new — done


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def write_output(events: list[dict], output_path: str | None, fmt: str):
    """Write events to file or stdout."""
    if not events:
        print("No events to write.", file=sys.stderr)
        return
    if output_path:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            if fmt == "csv":
                writer = csv.DictWriter(
                    f, fieldnames=FIELDNAMES, extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(events)
            else:
                json.dump(events, f, indent=2, ensure_ascii=False)
                f.write("\n")
        print(f"Wrote {len(events)} events to {output_path}", file=sys.stderr)
    else:
        if fmt == "csv":
            writer = csv.DictWriter(
                sys.stdout, fieldnames=FIELDNAMES, extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(events)
        else:
            json.dump(events, sys.stdout, indent=2, ensure_ascii=False)
            sys.stdout.write("\n")


# ---------------------------------------------------------------------------
# Merge (for combining JSON files from multiple sessions)
# ---------------------------------------------------------------------------


def load_events(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(f"Error: {path} does not contain a JSON array.", file=sys.stderr)
        sys.exit(1)
    return data


def merge_events(file_paths: list[str]) -> list[dict]:
    seen = {}
    for path in file_paths:
        events = load_events(path)
        for event in events:
            url = event.get("event_url", "")
            if url and url not in seen:
                seen[url] = event
    merged = list(seen.values())
    merged.sort(key=lambda e: e.get("start_at") or "")
    return merged


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="Luma map event scraper — Playwright browser automation."
    )
    parser.add_argument(
        "--city",
        help="Scrape a single city (name must match a hub, case-insensitive)",
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
    parser.add_argument(
        "--merge",
        nargs="+",
        metavar="FILE",
        help="Merge and deduplicate multiple JSON downloads",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Merge mode — no browser needed
    if args.merge:
        events = merge_events(args.merge)
        print(
            f"Merged: {len(events)} unique events from {len(args.merge)} files.",
            file=sys.stderr,
        )
        write_output(events, args.output, args.format)
        return

    # Determine target cities
    if args.city:
        city_lower = args.city.lower()
        matches = [
            (name, lat, lng) for name, lat, lng in CITY_HUBS
            if city_lower in name.lower()
        ]
        if not matches:
            print(f"Error: No city hub matching '{args.city}'.", file=sys.stderr)
            print(f"Available cities: {', '.join(c[0] for c in CITY_HUBS)}",
                  file=sys.stderr)
            sys.exit(1)
        cities = matches
    else:
        cities = CITY_HUBS

    print(f"Scraping {len(cities)} cities...", file=sys.stderr)

    events = asyncio.run(scrape(cities, headless=args.headless))

    print(f"\nTotal: {len(events)} unique events", file=sys.stderr)
    write_output(events, args.output, args.format)


if __name__ == "__main__":
    main()
