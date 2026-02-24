# Founder Finder

A command-line tool to extract founder LinkedIn and Twitter/X profiles from [Y Combinator](https://www.ycombinator.com/companies) company pages.

## How It Works

1. Queries the [yc-oss API](https://github.com/yc-oss/api) to get a filtered list of YC companies.
2. Scrapes each company's YC page to extract founder names, titles, LinkedIn URLs, and Twitter/X URLs.
3. Outputs results as CSV or JSON.

## Installation

Requires Python 3.10+.

```bash
pip install httpx tqdm
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

One row per founder with columns: `company`, `slug`, `batch`, `website`, `location`, `founder_name`, `founder_title`, `linkedin`, `twitter`.

## Rate Limiting

The script waits 1 second between requests by default. Adjust with `--delay`. Scraping large batches (100+ companies) will take several minutes.
