# Founder Finder - Claude Context

## What This Project Does

This is a CLI scraper that extracts **founder LinkedIn and Twitter/X links** from Y Combinator company pages. It uses a two-phase approach:

1. **Phase 1 - Company list**: Fetches company slugs from the [yc-oss community API](https://yc-oss.github.io/api) with filters (batch, industry, tag, top companies, region, status).
2. **Phase 2 - Founder scraping**: For each company slug, fetches the YC company detail page (`ycombinator.com/companies/{slug}`), extracts structured founder data from the `data-page` React attribute embedded in the HTML.

## Key File

- `scrape_yc_founders.py` - The entire scraper in a single file. ~330 lines.

## Architecture Decisions

- **Single-file script** - intentionally kept simple, no package structure.
- **yc-oss API for filtering** - avoids needing Algolia keys or a headless browser for the company directory (which is client-side rendered). The yc-oss API mirrors YC data as static JSON files at paths like `/batches/s24.json`, `/tags/ai.json`, `/industries/b2b.json`.
- **`data-page` attribute parsing** - YC company detail pages are server-rendered and embed all structured data (including founders) in a `data-page="..."` HTML attribute as HTML-escaped JSON. This is more reliable than DOM scraping.
- **httpx + tqdm** - only external dependencies. No BeautifulSoup needed since we regex the `data-page` attribute directly.

## Batch Name Normalization

The yc-oss API uses inconsistent slug formats across eras:
- Classic batches: `s24`, `w23`, `s05` (letter + 2-digit year)
- Newer batches: `fall-2024`, `fall-2025`, `spring-2025`, `x25`

The `normalize_batch()` function handles this mapping so users can pass friendly names like `F25`, `SP25`, or `"Fall 2025"`. See the function docstring for the full mapping.

## Common Gotchas

- The yc-oss API serves static `.json` files from GitHub Pages. A bad batch slug returns a 404, not an empty list.
- YC company pages may change their HTML structure. If `data-page` attribute parsing breaks, check if YC has changed how they embed React props.
- Rate limiting: the script defaults to 1 second between company page requests. YC may block faster scraping.
- The `all.json` endpoint returns every YC company (~5000+). It's fetched when filters need intersection or client-side filtering.

## Output Formats

- **CSV**: One row per founder (company fields repeated per founder).
- **JSON**: Array of company objects, each with a nested `founders` array.

## Dependencies

- `httpx` - HTTP client
- `tqdm` - progress bar

## Reference File

- `yc_companies_analysis.md` - Detailed analysis of YC's page structure, Algolia config, and scraping strategies. Useful context if the scraping approach needs to change.
