# Founder Finder

A command-line tool to extract founder LinkedIn and Twitter/X profiles from [Y Combinator](https://www.ycombinator.com/companies) company pages.

## How It Works

1. Queries the [yc-oss API](https://github.com/yc-oss/api) to get a filtered list of YC companies.
2. Scrapes each company's YC page to extract founder names, titles, LinkedIn URLs, and Twitter/X URLs.
3. Outputs results as CSV or JSON.

## Installation

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Scrape founders from a specific YC batch
python scrape_yc_founders.py --batch S24 --format json --output s24_founders.json

# Newer batch formats are supported
python scrape_yc_founders.py --batch F25          # Fall 2025
python scrape_yc_founders.py --batch SP25         # Spring 2025
python scrape_yc_founders.py --batch "Fall 2025"  # Full name also works

# Filter by tag and region, output as CSV
python scrape_yc_founders.py --batch S24 --tag AI --region "United States" --format csv

# Top YC companies, limited to 20
python scrape_yc_founders.py --top-companies --limit 20 --format json
```

### Options

| Flag | Description | Example |
|---|---|---|
| `--batch` | YC batch | `S24`, `W23`, `F25`, `SP25`, `"Fall 2025"` |
| `--industry` | Industry filter | `B2B`, `Fintech` |
| `--tag` | Tag filter | `AI`, `SaaS` |
| `--region` | Region filter (substring match) | `"United States"` |
| `--status` | Company status | `Active`, `Inactive` |
| `--top-companies` | Only top companies | |
| `--limit` | Max companies to scrape | `50` |
| `--format`, `-f` | Output format | `csv` (default), `json` |
| `--output`, `-o` | Output file (default: stdout) | `results.json` |
| `--delay` | Seconds between requests (default: 1.0) | `2.0` |

Filters can be combined. When multiple API filters are used, results are intersected (AND logic).

### Batch Name Formats

The tool accepts several batch name formats:

| Input | Resolves To |
|---|---|
| `S24`, `W23`, `X25` | `s24`, `w23`, `x25` |
| `F24`, `F25` | `fall-2024`, `fall-2025` |
| `SP25` | `spring-2025` |
| `"Fall 2025"`, `"Winter 2026"` | `fall-2025`, `winter-2026` |

## Output

### JSON

```json
[
  {
    "name": "DoorDash",
    "slug": "doordash",
    "batch": "S13",
    "website": "https://www.doordash.com",
    "location": "San Francisco, CA",
    "company_linkedin": "https://www.linkedin.com/company/doordash",
    "company_twitter": "https://twitter.com/doordash",
    "founders": [
      {
        "name": "Tony Xu",
        "title": "Founder/CEO",
        "linkedin": "https://www.linkedin.com/in/xutony",
        "twitter": ""
      }
    ]
  }
]
```

### CSV

One row per founder with columns: `company`, `slug`, `batch`, `website`, `location`, `company_linkedin`, `company_twitter`, `founder_name`, `founder_title`, `linkedin`, `twitter`.

## Rate Limiting

The script waits 1 second between requests by default. Adjust with `--delay`. Scraping large batches (100+ companies) will take several minutes.

## Follow Founders

After scraping, use `follow_founders.py` to open each founder's profile in your browser for manual Follow/Connect. No external dependencies required.

```bash
# Open all profiles one at a time
python follow_founders.py s24_founders.json

# Only LinkedIn profiles
python follow_founders.py s24_founders.json --platform linkedin

# Only Twitter/X profiles
python follow_founders.py s24_founders.json --platform twitter

# Auto-advance every 8 seconds (no terminal interaction needed)
python follow_founders.py s24_founders.json --delay 8

# Process only profiles 25-50
python follow_founders.py s24_founders.json --range 25-50

# Resume where you left off, limit to 20
python follow_founders.py s24_founders.json --resume --limit 20
```

### Options

| Flag | Description | Example |
|---|---|---|
| `--platform` | Which platform(s) to open | `linkedin`, `twitter`, `both` (default) |
| `--delay` | Auto-advance after N seconds | `8` |
| `--range` | Only process profiles in this range (1-based, inclusive) | `25-50` |
| `--limit` | Max profiles to open this session | `20` |
| `--resume` | Skip profiles already visited | |
| `--no-close` | Don't auto-close the previous tab | |

### Controls

In manual mode (no `--delay`):
- **Enter** — mark as done, open next profile
- **s** — skip, open next profile
- **q** — quit (progress saved)

In auto mode (`--delay N`):
- **Ctrl+C** — stop

Progress is saved to `follow_progress.json` after each profile, so you can safely stop and resume later with `--resume`.

## LinkedIn Triage (Up/Down)

If you want a fast manual “review later vs skip” flow (using your real Chrome profile), use `triage_linkedin.py`.

### Install

```bash
pip install playwright
playwright install chromium
```

If you see `ModuleNotFoundError: No module named 'playwright'`, install the package in the **same** environment as `python` (for example `python -m pip install playwright`), then run `playwright install chromium` again if needed.

### Usage

```bash
# From a .txt file (one LinkedIn URL per line)
python triage_linkedin.py companies.txt --output triage.csv --resume

# From YC founders JSON (extracts founder linkedin URLs)
python triage_linkedin.py s24_founders.json --output triage.csv --resume

# If Chrome exits immediately or you see a profile/lock error: close all Chrome windows
# and retry, OR start Chrome with debugging then attach:
#   1) Run start_chrome_debug.bat (kills Chrome, restarts with port 9222; wait until it prints OK for 9222)
#   2) In another terminal:
python triage_linkedin.py companies.txt --output triage.csv --resume --cdp
# Optional: fail fast with  --cdp-wait 0  or wait longer with  --cdp-wait 60
```

### Controls

- **Up arrow** — `review_later`
- **Down arrow** — `skip`
- **q** — quit (progress saved)

Notes:
- Keystrokes are captured from the **terminal window**, so keep the terminal focused when pressing Up/Down.
- By default it launches Chrome with a persistent profile (default Windows path). If **Chrome is already running**, that profile is often **locked** and Playwright will fail—use **`--cdp`** after `start_chrome_debug.bat`, or quit Chrome first. Use `--profile-dir` if your Chrome user data lives elsewhere.
