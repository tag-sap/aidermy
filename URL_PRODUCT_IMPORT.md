# URL Product Import

`POST /api/products/import-url` accepts `{ "url": "https://..." }`, validates the target against SSRF risks, and returns a normalized product. The importer saves the product in the existing `products.db` table and preserves existing non-empty fields when the same source URL or brand/name is imported again.

The provider order is adaptive:

1. HTTPX + Beautiful Soup for server-rendered HTML (`SCRAPER_HTTPX_ENABLED=1`).
2. The optional `amerkurev/scrapper` REST service for configured browser-only domains (`SCRAPPER_URL`, `SCRAPPER_DOMAINS`; `SCRAPPER_ALL_DOMAINS=1` for all sites).
3. Scrapling `Fetcher`, then `DynamicFetcher`, then `StealthyFetcher`.
4. Optional Crawl4AI only when explicitly installed and `CRAWL4AI_ENABLED=1`.

A domain can skip the plain HTTP pass with `SCRAPER_HTTPX_SKIP_DOMAINS` (default: `goldapple.ru`). Successful imports can be cached briefly with `SCRAPER_IMPORT_CACHE_TTL` (disabled by default; production may use `300`). No per-domain DB table is required for the single-worker deployment; provider outcomes are logged and measured separately.

Extraction is deterministic: JSON-LD, OpenGraph/meta tags, DOM selectors, embedded Next.js JSON, and ingredient sections. Missing INCI remains `null`; it is never generated or replaced by a search result. Errors are classified as invalid URL, not found, access denied, anti-bot, timeout, unsupported format, network error, or no product data, with the corresponding HTTP status.

Install backend dependencies with `pip install -r backend/requirements.txt`. Scrapling browser fetchers may require `scrapling install` in the deployment environment. Run importer tests with `cd backend && python -m unittest tests.test_product_import tests.test_scraper_url_import tests.test_scraper_provider_routing -v`. Site-specific selectors can be added as adapters under `backend/app/scraper/` without changing the API or scoring engine.

If a system Chrome/Chromium is already installed, set `SCRAPLING_BROWSER_EXECUTABLE` to its executable path. This avoids downloading a separate browser runtime. The production host uses the already-installed Playwright Chromium through version-compatible cache symlinks; the optional Scrapper image itself is not deployed because it requires roughly 2 GB while the host has under 1 GB free.