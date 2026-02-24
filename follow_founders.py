#!/usr/bin/env python3
"""
Manual-Assist Browser for Following Founders on LinkedIn & Twitter/X.

Opens each founder's profile page in your default browser one at a time,
letting you manually click Follow/Connect. Progress is saved so you can stop and resume.

Usage:
    python follow_founders.py founders.json
    python follow_founders.py founders.json --platform linkedin
    python follow_founders.py founders.json --delay 8
    python follow_founders.py founders.json --limit 20 --resume

With --delay, the script auto-advances after N seconds (no need to switch back
to the terminal). Without --delay, press Enter/s/q in the terminal to control flow.

No external dependencies — uses Python's webbrowser module.
"""

import argparse
import json
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

PROGRESS_FILE = "follow_progress.json"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Open founder LinkedIn/Twitter profiles in your browser for manual follow/connect."
    )
    parser.add_argument("input", help="Path to JSON output from scrape_yc_founders.py")
    parser.add_argument("--platform", choices=["linkedin", "twitter", "both"],
                        default="both", help="Which platform(s) to open (default: both)")
    parser.add_argument("--limit", type=int, help="Max number of profiles to open this session")
    parser.add_argument("--range", metavar="START-END", dest="range_str",
                        help="Only process profiles in this 1-based range, e.g. 25-50")
    parser.add_argument("--resume", action="store_true",
                        help="Skip founders already visited in progress file")
    parser.add_argument("--delay", type=int, metavar="SECONDS",
                        help="Auto-advance after N seconds (no terminal interaction needed). "
                             "Ctrl+C to stop.")
    parser.add_argument("--no-close", action="store_true",
                        help="Don't close the previous tab when advancing")
    return parser.parse_args()


def close_browser_tab():
    """Send Ctrl+W to the focused window to close the current browser tab.

    Uses PowerShell SendKeys on WSL/Windows. No-op on other platforms.
    """
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             'Add-Type -AssemblyName System.Windows.Forms; '
             '[System.Windows.Forms.SendKeys]::SendWait("^w")'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def build_profile_list(data: list[dict], platform: str) -> list[dict]:
    """Build flat list of (founder_name, company, url, platform) from scraper JSON output."""
    profiles = []
    for company in data:
        company_name = company.get("name", "Unknown")
        for founder in company.get("founders", []):
            founder_name = founder.get("name", "Unknown")
            if platform in ("linkedin", "both") and founder.get("linkedin"):
                profiles.append({
                    "founder": founder_name,
                    "company": company_name,
                    "url": founder["linkedin"],
                    "platform": "linkedin",
                })
            if platform in ("twitter", "both") and founder.get("twitter"):
                profiles.append({
                    "founder": founder_name,
                    "company": company_name,
                    "url": founder["twitter"],
                    "platform": "twitter",
                })
    return profiles


def load_progress() -> dict:
    """Load progress file if it exists."""
    path = Path(PROGRESS_FILE)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return {"visited": {}}
    return {"visited": {}}


def save_progress(progress: dict):
    """Save progress to file."""
    Path(PROGRESS_FILE).write_text(
        json.dumps(progress, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main():
    args = parse_args()

    # Load founder data
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    profiles = build_profile_list(data, args.platform)
    if not profiles:
        print("No profiles found for the selected platform(s).", file=sys.stderr)
        sys.exit(1)

    # Load progress and filter if resuming
    progress = load_progress()
    if args.resume:
        profiles = [p for p in profiles if p["url"] not in progress["visited"]]
        if not profiles:
            print("All profiles already visited. Nothing to do.", file=sys.stderr)
            sys.exit(0)

    # Apply range (1-based, inclusive)
    if args.range_str:
        try:
            start_s, end_s = args.range_str.split("-", 1)
            start, end = int(start_s), int(end_s)
        except ValueError:
            print(f"Error: invalid range '{args.range_str}', expected format: START-END (e.g. 25-50)",
                  file=sys.stderr)
            sys.exit(1)
        if start < 1 or end < start:
            print(f"Error: invalid range {start}-{end}", file=sys.stderr)
            sys.exit(1)
        total_before = len(profiles)
        profiles = profiles[start - 1:end]
        print(f"Selected range {start}-{end} of {total_before} profiles.", file=sys.stderr)

    # Apply limit
    if args.limit:
        profiles = profiles[:args.limit]

    print(f"Found {len(profiles)} profiles to visit.", file=sys.stderr)
    if args.delay:
        print(f"Auto-advancing every {args.delay}s. Ctrl+C to stop.", file=sys.stderr)

    auto_close = not args.no_close
    done_count = 0
    skipped_count = 0

    try:
        for i, profile in enumerate(profiles, 1):
            platform_label = profile["platform"].capitalize()
            print(f"\n[{i}/{len(profiles)}] Opening {platform_label} for "
                  f"{profile['founder']} ({profile['company']})...")
            print(f"  {profile['url']}")

            # Close previous tab before opening the next one
            if auto_close and i > 1:
                close_browser_tab()
                time.sleep(0.3)

            webbrowser.open(profile["url"])

            timestamp = datetime.now(timezone.utc).isoformat()

            if args.delay:
                # Auto-advance mode: wait N seconds then move on
                try:
                    time.sleep(args.delay)
                except KeyboardInterrupt:
                    progress["visited"][profile["url"]] = {
                        "status": "done", "timestamp": timestamp,
                    }
                    save_progress(progress)
                    done_count += 1
                    print("\nStopped by user.")
                    break
                progress["visited"][profile["url"]] = {
                    "status": "done", "timestamp": timestamp,
                }
                done_count += 1
            else:
                # Manual mode: wait for Enter/s/q
                try:
                    action = input("  Press Enter when done, 's' to skip, 'q' to quit: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    action = "q"

                if action == "q":
                    progress["visited"][profile["url"]] = {
                        "status": "skipped", "timestamp": timestamp,
                    }
                    save_progress(progress)
                    skipped_count += 1
                    print("\nQuitting...")
                    break
                elif action == "s":
                    progress["visited"][profile["url"]] = {
                        "status": "skipped", "timestamp": timestamp,
                    }
                    skipped_count += 1
                else:
                    progress["visited"][profile["url"]] = {
                        "status": "done", "timestamp": timestamp,
                    }
                    done_count += 1

            save_progress(progress)
    finally:
        # Close the last tab
        if auto_close:
            close_browser_tab()

    # Summary
    total = done_count + skipped_count
    print(f"\nVisited {total} profiles ({done_count} done, {skipped_count} skipped)")


if __name__ == "__main__":
    main()
