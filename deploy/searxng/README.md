# SearXNG (free self-hosted search)

SearXNG is optional. Without it, Aidermy keeps the existing free DuckDuckGo
fallback. The service is bound to loopback only; do not proxy it through nginx.

## Start

```bash
cd deploy/searxng
cp .env.example .env
# put a long random value in SEARXNG_SECRET
docker compose up -d
curl 'http://127.0.0.1:8888/search?q=celimax&format=json'
```

If `docker compose` is unavailable, run the equivalent container with
`docker run`, mount `settings.yml` read-only and publish
`127.0.0.1:8888:8080`.

## Aidermy backend

```env
SEARXNG_URL=http://127.0.0.1:8888
SEARXNG_TIMEOUT=12
# Optional: enable the fast server-rendered HTTPX provider.
SCRAPER_HTTPX_ENABLED=1
SCRAPER_HTTPX_TIMEOUT=20
# Optional: enable Crawl4AI only after installing it and its browser.
CRAWL4AI_ENABLED=0
CRAWL4AI_TIMEOUT=90
# Successful web-search results are public catalog data. 0 disables the
# process-local TTL cache; tests keep it at 0.
WEB_SEARCH_CACHE_TTL=3600
```

The backend never reads the SearXNG admin UI and never bypasses CAPTCHAs,
authorization, robots/access restrictions or anti-bot challenges.
