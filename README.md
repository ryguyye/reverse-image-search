# selfwatch

A consent-based reverse image search tool. You upload **your own** photo (or paste a URL to one), and the app queries public reverse image search providers to find where copies of that image appear online. Useful for:

- Detecting impersonation accounts using your photos
- Finding scrapers / unauthorized reuse of your images
- Copyright enforcement for photographers and artists
- Auditing your own digital footprint

This tool is intentionally scoped to monitoring images you own or have rights to. It does not identify people, aggregate profiles by face, or match images you don't have permission to search.

## How it works

1. You provide an image (URL or upload).
2. The app fan-outs the query to enabled reverse image search providers.
3. Results are deduplicated by canonical URL and merged across providers.

### Providers

| Provider | Engine | Input | Status |
| --- | --- | --- | --- |
| Google Lens | SerpAPI (`engine=google_lens`) | Public image URL | Enabled when `SERPAPI_KEY` is set |
| Yandex Images | SerpAPI (`engine=yandex_images`) | Public image URL | Enabled when `SERPAPI_KEY` is set |
| Bing Reverse Image | SerpAPI (`engine=bing_reverse_image`) | Public image URL | Enabled when `SERPAPI_KEY` is set. **Experimental** — Microsoft retired the official Bing Visual Search API in 2025; results come from SerpAPI scraping Bing's public UI and may break upstream. |
| TinEye | Direct API (HMAC-signed) | Upload or URL | Enabled when `TINEYE_API_KEY` and `TINEYE_PRIVATE_KEY` are set. **Experimental** — signing follows TinEye's documented spec but Anthropic does not have live credentials to validate it end-to-end. Run `make tineye-ping ARGS="--image-url <url>"` to verify your own keys in 30 seconds. |

Only providers with credentials configured will run. If none are configured, the API returns 503.

## Setup

Local dev:

```bash
make install
cp .env.example .env       # edit and add SERPAPI_KEY
make dev                   # http://localhost:8000
```

Other targets: `make run` (production-ish, with proxy headers), `make tunnel` (Cloudflare quick tunnel), `make tineye-ping ARGS=...` (one-shot live TinEye credential check), `make test` (lint + pytest), `make clean`.

Docker:

```bash
cp .env.example .env
docker compose up -d --build
```

State (DB + uploads) lives on a named volume; the container runs as non-root and ships with a healthcheck. See [docs/deploy.md](docs/deploy.md) for the full deployment guide including the optional cloudflared sidecar.

## Uploading vs. providing a URL

The current providers (Google Lens, Yandex via SerpAPI) require a **publicly reachable image URL**. If you upload a file, the app saves it under `./uploads/` and serves it at `/uploads/<name>`. For SerpAPI to fetch it, your instance has to be on the public internet.

The recommended path is **Cloudflare Tunnel** — see [docs/deploy.md](docs/deploy.md). Quick start:

```bash
make dev          # in one terminal
make tunnel       # in another; prints a https://*.trycloudflare.com URL
# add PUBLIC_BASE_URL=https://that-url to .env, restart the app
```

For a stable URL on your own domain, follow the named-tunnel section of `docs/deploy.md`. You can also layer **Cloudflare Access** on top to put SSO in front of the app without writing any auth code.

If a tunnel doesn't fit your setup, host the image somewhere stable (your own site, S3, etc.) and paste the URL into the form.

## Recurring scans (watches)

You can save an image as a **watch** and have selfwatch re-scan it on a schedule. When new matches appear (URLs not seen on previous runs of that watch), it can notify you via:

- **Webhook** — POST a JSON payload to a URL (Slack, Discord, Zapier, your own endpoint).
- **Email** — plaintext message to one address. Requires `SMTP_*` env vars.

A single watch can use either, both, or neither — they're independent.

```bash
# Create a watch from a hosted image, run hourly, post to Slack and email me
curl -X POST http://localhost:8000/api/watches \
  -F "name=my profile pic" \
  -F "cadence_minutes=60" \
  -F "webhook_url=https://hooks.slack.com/services/..." \
  -F "notify_email=me@example.com" \
  -F "image_url=https://me.example/photo.jpg"
```

Webhook payload:

```json
{
  "watch_id": 1,
  "watch_name": "my profile pic",
  "scanned_at": "2026-05-10T15:23:00+00:00",
  "image_url": "https://me.example/photo.jpg",
  "new_matches": [
    {
      "url": "https://impostor.example/profile",
      "domain": "impostor.example",
      "title": "...",
      "thumbnail_url": "...",
      "sources": ["google_lens"]
    }
  ]
}
```

Notes:
- The scheduler runs in the FastAPI process — no separate worker.
- For watches with **uploaded** images (not URL-based), set `PUBLIC_BASE_URL` so providers can fetch the image at `<base>/uploads/<name>`.
- State lives in SQLite at `DB_PATH` (default `./selfwatch.db`). Watches and previously-seen match URLs persist across restarts.
- New watches are perceptual-hashed (pHash) and rejected with **409** if they're a near-duplicate of an existing watch (Hamming distance ≤ 10). Resend the request with `force=true` to create anyway. If the image can't be fetched/decoded, the hash is omitted and dedup is silently skipped.

## API

- `GET /healthz` — liveness check; reports DB connectivity.
- `GET /api/providers` — list providers and whether each is enabled.
- `GET /api/watches` — list watches.
- `POST /api/watches` — create a watch (multipart form: `name`, `cadence_minutes`, `webhook_url`, `notify_email`, `image_url` and/or `file`).
- `GET /api/watches/{id}` — fetch a single watch.
- `PATCH /api/watches/{id}` — update a watch. Body: `{"active": true|false}` to pause/resume.
- `DELETE /api/watches/{id}` — delete a watch (cascades to its seen-match history).
- `POST /api/watches/{id}/run` — run a watch immediately; returns `WatchRunResult` with `new_matches`.
- `GET /api/watches/{id}/matches?limit=50&offset=0` — full history of matches recorded for a watch (URLs accumulated across all runs), newest first.
- `POST /api/scan` — multipart form with `image_url` (string) and/or `file` (image). Returns:
  ```json
  {
    "providers_used": ["google_lens", "yandex_images"],
    "providers_failed": [],
    "matches": [
      {
        "url": "https://example.com/page",
        "domain": "example.com",
        "title": "Page title",
        "thumbnail_url": "https://...",
        "sources": ["google_lens"],
        "score": null
      }
    ]
  }
  ```

## Project layout

```
src/selfwatch/
  main.py            # FastAPI app, /api/scan, /api/providers
  config.py          # Settings (env vars)
  models.py          # Pydantic response types
  dedupe.py          # Canonical-URL dedup + cross-provider merge
  providers/
    base.py          # Provider interface
    google_lens.py   # SerpAPI Google Lens
    yandex.py        # SerpAPI Yandex Images
    bing.py          # SerpAPI Bing Reverse Image (post-API-retirement)
    tineye.py        # TinEye Search API (HMAC-signed)
  scanning.py        # Provider fan-out + dedupe (used by /api/scan and watches)
  watches.py         # Watch CRUD, per-watch scan diff, run logic
  scheduler.py       # In-process asyncio loop that runs due watches
  notifier.py        # Webhook + email dispatch
  image_utils.py     # Perceptual-hash + image fetch helpers
  db.py              # SQLite schema + connection helper
static/index.html    # Upload UI
```

## What's intentionally not here

- No face recognition or face embedding. Reverse image search matches the image, not the person.
- No bulk crawling, scraping, or platform-of-record violations. The app uses public search APIs that respect their own indexing rules.
- No identity aggregation — each match is a URL where the image was found, not a profile of a person.

## Roadmap

The roadmap is currently empty — open an issue if there's a feature you want.
