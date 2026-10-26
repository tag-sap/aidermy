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

If the Docker Compose plugin is unavailable (for example on the current
Ubuntu host), run the equivalent container directly:

```bash
docker run -d --name aidermy-searxng --restart unless-stopped \
  --env-file .env \
  -v "$PWD/settings.yml:/etc/searxng/settings.yml:ro" \
  -p 127.0.0.1:8888:8080 \
  --memory 512m \
  searxng/searxng:latest
```

The `.env` file must contain at least:

```env
SEARXNG_SECRET=<long-random-value>
SEARXNG_BASE_URL=http://127.0.0.1:8888/
```

Check it before enabling `SEARXNG_URL` in the backend:

```bash
curl 'http://127.0.0.1:8888/search?q=celimax&format=json'
```

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
