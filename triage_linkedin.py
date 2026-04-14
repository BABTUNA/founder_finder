#!/usr/bin/env python3
"""
LinkedIn Triage Helper (manual, logged-in browser).

Opens each LinkedIn URL in a real Chrome profile and lets you triage quickly:
  - Up arrow   -> review later
  - Down arrow -> skip / idgaf

Writes decisions to a CSV and can resume safely.

Windows-focused (uses msvcrt for key capture).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import msvcrt
from playwright.sync_api import sync_playwright


DEFAULT_OUTPUT = "triage.csv"
DEFAULT_PROGRESS = "triage_progress.json"

REVIEW_LATER = "review_later"
SKIP = "skip"


@dataclass(frozen=True)
class TriageItem:
    url: str
    source: str = ""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Open LinkedIn links and label with Up/Down keys (review later vs skip)."
    )
    p.add_argument(
        "input",
        help="Input file with LinkedIn URLs. Supported: .txt (one per line), .csv (url column), .json (array of URLs).",
    )
    p.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help=f"CSV output path (default: {DEFAULT_OUTPUT})")
    p.add_argument(
        "--progress",
        default=DEFAULT_PROGRESS,
        help=f"Progress file path for resume (default: {DEFAULT_PROGRESS})",
    )
    p.add_argument("--resume", action="store_true", help="Skip URLs already present in progress file")
    p.add_argument("--limit", type=int, help="Max URLs to triage this run")
    p.add_argument(
        "--profile-dir",
        help=(
            "Chrome User Data directory to use for your real profile session. "
            "If omitted, defaults to Windows Chrome user data location."
        ),
    )
    p.add_argument("--headless", action="store_true", help="Run headless (not recommended for manual triage).")
    return p.parse_args()


def _read_nonempty_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return lines


def normalize_linkedin_url(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    # Allow passing just a handle/path-ish chunk
    if not s.startswith("http"):
        if s.startswith("linkedin.com/") or s.startswith("www.linkedin.com/"):
            s = "https://" + s.lstrip("/")
        else:
            return ""
    # Strip URL fragments and noisy query params (basic)
    s = s.split("#", 1)[0]
    if "?" in s:
        base, qs = s.split("?", 1)
        # keep minimal; LinkedIn URLs typically don't need query strings for identity
        s = base
    return s.rstrip("/")


def dedupe_items(items: Iterable[TriageItem]) -> list[TriageItem]:
    seen: set[str] = set()
    out: list[TriageItem] = []
    for it in items:
        if it.url in seen:
            continue
        seen.add(it.url)
        out.append(it)
    return out


def load_items(path: Path) -> list[TriageItem]:
    if not path.exists():
        raise FileNotFoundError(str(path))

    ext = path.suffix.lower()
    if ext == ".txt":
        raw = _read_nonempty_lines(path)
        items = [TriageItem(url=normalize_linkedin_url(u), source=path.name) for u in raw]
        return dedupe_items([it for it in items if it.url])
    if ext == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            items: list[TriageItem] = []
            for entry in data:
                # 1) Plain list of URLs
                if isinstance(entry, str):
                    u = normalize_linkedin_url(entry)
                    if u:
                        items.append(TriageItem(url=u, source=path.name))
                    continue

                # 2) YC founders output shape: [{..., founders:[{linkedin:"..."}]}]
                if isinstance(entry, dict):
                    founders = entry.get("founders")
                    if isinstance(founders, list):
                        for f in founders:
                            if not isinstance(f, dict):
                                continue
                            u = normalize_linkedin_url(f.get("linkedin", "") or "")
                            if u:
                                items.append(TriageItem(url=u, source=path.name))
                        continue

                    # 3) Generic dict with a url-ish field
                    for key in ("url", "linkedin", "linkedin_url", "link"):
                        if key in entry:
                            u = normalize_linkedin_url(str(entry.get(key) or ""))
                            if u:
                                items.append(TriageItem(url=u, source=path.name))
                            break
                    continue

                # Unknown entry type: ignore
                continue

            return dedupe_items(items)
        raise ValueError("JSON input must be an array of URLs")
    if ext == ".csv":
        rows: list[TriageItem] = []
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("CSV has no header row")
            url_key = None
            for k in reader.fieldnames:
                if k and k.strip().lower() in {"url", "linkedin", "linkedin_url", "link"}:
                    url_key = k
                    break
            if url_key is None:
                raise ValueError("CSV must contain a 'url' (or linkedin/linkedin_url/link) column")
            for r in reader:
                u = normalize_linkedin_url(r.get(url_key) or "")
                if u:
                    rows.append(TriageItem(url=u, source=path.name))
        return dedupe_items(rows)

    raise ValueError(f"Unsupported input type: {ext}. Use .txt, .csv, or .json")


def default_chrome_profile_dir() -> Path:
    return Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"


def open_persistent_chrome(profile_dir: Path, headless: bool):
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1400, "height": 900},
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            yield page
        finally:
            context.close()


def load_progress(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("decisions", {}), dict):
                return data
        except Exception:
            pass
    return {"decisions": {}}


def save_progress(path: Path, progress: dict) -> None:
    path.write_text(json.dumps(progress, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_csv_row(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    fieldnames = ["url", "decision", "decided_at", "source"]
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in fieldnames})


def read_triage_key() -> str:
    """Return REVIEW_LATER or SKIP based on Up/Down arrow keys.

    Also supports:
      - 'q' to quit
      - 'o' to open (re-open current URL)
    """
    while True:
        ch = msvcrt.getwch()
        if ch in ("q", "Q"):
            return "quit"
        if ch in ("o", "O"):
            return "open"
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            if ch2 == "H":  # up arrow
                return REVIEW_LATER
            if ch2 == "P":  # down arrow
                return SKIP


def main() -> int:
    args = parse_args()
    in_path = Path(args.input)

    try:
        items = load_items(in_path)
    except FileNotFoundError:
        print(f"Input file not found: {in_path.resolve()}", file=sys.stderr)
        print(
            "Create that file (one LinkedIn URL per line) or pass a real path to .txt / .csv / .json.",
            file=sys.stderr,
        )
        return 2
    except Exception as e:
        print(f"Error loading input: {e}", file=sys.stderr)
        return 2

    if not items:
        print("No URLs found.", file=sys.stderr)
        return 0

    if args.limit:
        items = items[: args.limit]

    profile_dir = Path(args.profile_dir) if args.profile_dir else default_chrome_profile_dir()
    if not profile_dir.exists():
        print(f"Error: Chrome profile dir not found: {profile_dir}", file=sys.stderr)
        print("Pass --profile-dir to point at your Chrome 'User Data' directory.", file=sys.stderr)
        return 2

    print(f"Loaded {len(items)} URL(s).", file=sys.stderr)
    print(f"Using Chrome profile: {profile_dir}", file=sys.stderr)
    print("Next: open browser + key controls.", file=sys.stderr)

    progress_path = Path(args.progress)
    progress = load_progress(progress_path)
    if args.resume:
        decided = set(progress["decisions"].keys())
        items = [it for it in items if it.url not in decided]

    if not items:
        print("Nothing to triage (all URLs already decided).", file=sys.stderr)
        return 0

    print(f"Triage queue: {len(items)} URL(s).", file=sys.stderr)

    out_path = Path(args.output)

    for page in open_persistent_chrome(profile_dir, headless=args.headless):
        for idx, item in enumerate(items, 1):
            print(f"\n[{idx}/{len(items)}] {item.url}", file=sys.stderr)
            try:
                page.goto(item.url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"  Navigation error: {e}", file=sys.stderr)

            print("  Up=review later | Down=skip | q=quit", file=sys.stderr)
            while True:
                action = read_triage_key()
                if action == "open":
                    try:
                        page.goto(item.url, wait_until="domcontentloaded", timeout=45000)
                    except Exception:
                        pass
                    continue
                if action == "quit":
                    save_progress(progress_path, progress)
                    print("\nQuitting (progress saved).", file=sys.stderr)
                    return 0

                decided_at = utc_now_iso()
                progress["decisions"][item.url] = {
                    "decision": action,
                    "decided_at": decided_at,
                    "source": item.source,
                }
                save_progress(progress_path, progress)
                append_csv_row(
                    out_path,
                    {"url": item.url, "decision": action, "decided_at": decided_at, "source": item.source},
                )
                break
        break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

