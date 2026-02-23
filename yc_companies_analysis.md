# YC Companies Directory - Scraping Analysis

## Overview

The YC Companies directory at `https://www.ycombinator.com/companies` lists all Y Combinator-backed startups. Each company has a detail page at `https://www.ycombinator.com/companies/{slug}` (e.g., `/companies/doordash`, `/companies/airbnb`). The detail pages contain **founder profiles with LinkedIn and Twitter/X links**.

---

## Page Architecture

### Main Directory (`/companies`)

- **Tech stack**: React SPA (Vite bundler), assets served from `bookface-static.ycombinator.com/vite`
- **Search**: Algolia-powered — app ID `45BWZJ1SGC`, index `YCCompany_production`
- **Rendering**: Client-side rendered (CSR). The initial HTML is a shell; company cards are rendered by JavaScript after load. This means a simple HTTP GET won't return company data — you need a headless browser or the Algolia API.
- **Filters**: Industry, batch, region, company size, hiring status, nonprofit, top companies
- **Sorting**: Default and "By Launch Date" (index `YCCompany_By_Launch_Date_production`)

### Company Detail Page (`/companies/{slug}`)

Server-rendered with full HTML content. Sections from top to bottom:

1. **Header** — YC navigation bar
2. **Company summary** — Name, one-liner tagline, batch (e.g., "Summer 2013")
3. **Tags/badges** — Status (Active, Public, Acquired), industry tags
4. **Company details** — Location, founded year, team size, website URL
5. **Social links** — Company-level Twitter/X
6. **Latest news** — Press articles with dates
7. **Jobs** — Open positions with titles and salary ranges
8. **Founders section** — Profile cards with social media links ← **TARGET DATA**
9. **Footer** — Standard YC footer

---

## Founder Data Structure

Each founder card on a company detail page contains:

| Field | Example (DoorDash) |
|---|---|
| **Photo** | S3-hosted image (`bookface-images.s3.us-west-2.amazonaws.com/...`) |
| **Name** | Tony Xu |
| **Title** | Founder/CEO |
| **LinkedIn** | `https://www.linkedin.com/in/xutony` |
| **Twitter/X** | (not always present per founder — sometimes only at company level) |

### Verified Examples

| Company | Founder | LinkedIn | Twitter/X |
|---|---|---|---|
| DoorDash | Tony Xu | `linkedin.com/in/xutony` | — |
| DoorDash | Andy Fang | `linkedin.com/in/fangsterr` | — |
| DoorDash | Stanley Tang | `linkedin.com/in/stanleytang` | — |
| Airbnb | Brian Chesky | `linkedin.com/in/brianchesky/` | `twitter.com/bchesky` |
| Airbnb | Nathan Blecharczyk | `linkedin.com/in/blecharczyk/` | `twitter.com/nathanblec` |
| Airbnb | Joe Gebbia | `linkedin.com/in/jgebbia/` | `x.com/jgebbia` |
| Stripe | Patrick Collison | `linkedin.com/in/patrickcollison/` | `twitter.com/patrickc` |
| Stripe | John Collison | `linkedin.com/in/johnbcollison/` | `twitter.com/collision` |

**Key observations:**
- LinkedIn links are nearly universal across founders
- Twitter/X links are common but not guaranteed for every founder
- Some founders use `twitter.com`, others use `x.com` — handle both domains
- Company-level Twitter is also present (e.g., `twitter.com/doordash`)

---

## Scraping Strategy

### Step 1: Get All Company Slugs

The main `/companies` page is a client-side rendered SPA powered by Algolia. Options to get the full company list:

#### Option A: Algolia Search API (Recommended)
The page uses Algolia with public-facing config:
- **App ID**: `45BWZJ1SGC`
- **Index**: `YCCompany_production`
- **Tag filter**: `ycdc_public`

The API key is embedded in the page JavaScript — you'd need to extract it from the rendered page or network requests. Then you can paginate through all results programmatically using the Algolia REST API (`hitsPerPage` + `page` params). Each hit returns `name`, `slug`, `batch`, `url`, and other metadata.

#### Option B: YC-OSS Community API
An open-source mirror exists at `https://yc-oss.github.io/api/batches/{batch}.json` (e.g., `s23.json`). This provides company-level data (name, slug, website, industry, team size) but **does NOT include founder names or social links**. Useful only for getting the slug list to then scrape individual pages.

#### Option C: Headless Browser on `/companies`
Use Playwright/Puppeteer to load the page, scroll to trigger infinite loading, and extract all company card links. Company cards link to `/companies/{slug}`.

### Step 2: Scrape Each Company Detail Page

For each slug, fetch `https://www.ycombinator.com/companies/{slug}`. These pages are server-rendered, so a simple HTTP GET (requests/httpx) is sufficient — no headless browser needed.

#### Extract Founder Data
Parse the HTML to find:
- **Founder names**: Text content within the founders section heading elements
- **LinkedIn URLs**: All `<a href>` containing `linkedin.com/in/`
- **Twitter/X URLs**: All `<a href>` containing `twitter.com/` or `x.com/`

#### Pseudocode
```python
import httpx
from bs4 import BeautifulSoup

def scrape_company(slug: str) -> dict:
    url = f"https://www.ycombinator.com/companies/{slug}"
    resp = httpx.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    founders = []
    # Find all links in the founders section
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "linkedin.com/in/" in href:
            founders.append({"linkedin": href})
        elif "twitter.com/" in href or "x.com/" in href:
            # Associate with nearest founder
            founders.append({"twitter": href})

    return {"slug": slug, "founders": founders}
```

> **Note**: The actual HTML class names and nesting aren't fully visible from server responses due to the React rendering. A more robust approach would use a headless browser or inspect the DOM to identify exact CSS selectors for the founder card container.

### Step 3: Rate Limiting & Politeness

- Add delays between requests (1-2 seconds minimum)
- Respect `robots.txt`
- Use a reasonable User-Agent string
- Consider caching responses to avoid re-fetching

---

## Recommended Tech Stack

| Component | Tool | Why |
|---|---|---|
| Company list | Algolia API or yc-oss API + Playwright fallback | Get all slugs efficiently |
| Detail page scraping | `httpx` + `BeautifulSoup` | Pages are SSR, no JS needed |
| Headless browser (if needed) | Playwright | For CSR pages or JS-rendered content |
| Rate limiting | `asyncio` + semaphore | Control concurrency |
| Storage | SQLite or CSV | Store founder + social link data |

---

## Data Output Schema

```json
{
  "company": "DoorDash",
  "slug": "doordash",
  "yc_url": "https://www.ycombinator.com/companies/doordash",
  "batch": "S13",
  "founders": [
    {
      "name": "Tony Xu",
      "title": "Founder/CEO",
      "linkedin": "https://www.linkedin.com/in/xutony",
      "twitter": null
    },
    {
      "name": "Andy Fang",
      "title": "Founder",
      "linkedin": "https://www.linkedin.com/in/fangsterr",
      "twitter": null
    }
  ]
}
```

---

## Potential Challenges

1. **Rate limiting / blocking** — YC may rate-limit or block scrapers. Use delays and rotate User-Agents.
2. **Algolia API key rotation** — The embedded API key may change. Extract it dynamically from the page source.
3. **Incomplete social links** — Not all founders have LinkedIn/Twitter listed. Some profiles are minimal.
4. **Disambiguating founder vs. company social links** — Company-level Twitter (e.g., `twitter.com/doordash`) appears alongside founder Twitter. Filter by context/section.
5. **Scale** — There are 5,000+ YC companies. At 1 req/sec, scraping all detail pages takes ~1.5 hours.
6. **HTML structure changes** — YC can change their markup at any time. Build selectors that are resilient to minor changes.
