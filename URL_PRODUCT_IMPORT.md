# URL Product Import

`POST /api/products/import-url` accepts `{ "url": "https://..." }`, validates the target against SSRF risks, and returns a normalized product. The importer saves the product in the existing `products.db` table and preserves existing non-empty fields when the same source URL or brand/name is imported again.

Scraping uses Scrapling in this order: `Fetcher` for a normal HTTP request, `DynamicFetcher` when the first response does not contain a product, then `StealthyFetcher` as the final browser fallback. Extraction is deterministic: JSON-LD, OpenGraph/meta tags, DOM selectors, embedded text, and ingredient sections. Missing INCI remains `null`; it is never generated.

Install backend dependencies with `pip install -r backend/requirements.txt`. Scrapling browser fetchers may require `scrapling install` in the deployment environment. Run importer tests with `cd backend && python -m unittest tests.test_product_import -v`. Site-specific selectors can be added as adapters under `backend/app/scraper/` without changing the API or scoring engine.

If a system Chrome/Chromium is already installed, set `SCRAPLING_BROWSER_EXECUTABLE` to its executable path. This avoids downloading a separate browser runtime.