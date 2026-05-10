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
| TinEye | Direct API (HMAC-signed) | Upload or URL | Enabled when `TINEYE_API_KEY` and `TINEYE_PRIVATE_KEY` are set. **Experimental** — signing follows TinEye's documented spec but has not been validated against live credentials. |
| Bing Visual Search | Microsoft API | Upload or URL | Roadmap |

Only providers with credentials configured will run. If none are configured, the API returns 503.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and add SERPAPI_KEY
```

Run the server:

```bash
uvicorn selfwatch.main:app --app-dir src --reload --port 8000
```

Then open <http://localhost:8000>.

## Uploading vs. providing a URL

The current providers (Google Lens, Yandex via SerpAPI) require a **publicly reachable image URL**. If you upload a file, the app saves it under `./uploads/` and serves it at `/uploads/<name>`. For SerpAPI to fetch it, your instance must be reachable from the public internet — either:

- deploy the app to a public host, or
- expose your local server with a tunnel: `ngrok http 8000`, then set `--forwarded-allow-ips="*"` and use the ngrok URL when accessing the UI.

If those constraints don't fit your setup, host the image somewhere stable (your own site, S3, etc.) and paste the URL into the form.

## Recurring scans (watches)

You can save an image as a **watch** and have selfwatch re-scan it on a schedule. When new matches appear (URLs not seen on previous runs of that watch), it can POST a JSON payload to a webhook of your choice (Slack incoming webhook, Discord, Zapier, your own endpoint).

```bash
# Create a watch from a hosted image, run hourly, post new matches to Slack
curl -X POST http://localhost:8000/api/watches \
  -F "name=my profile pic" \
  -F "cadence_minutes=60" \
  -F "webhook_url=https://hooks.slack.com/services/..." \
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

## API

- `GET /api/providers` — list providers and whether each is enabled.
- `GET /api/watches` — list watches.
- `POST /api/watches` — create a watch (multipart form: `name`, `cadence_minutes`, `webhook_url`, `image_url` and/or `file`).
- `GET /api/watches/{id}` — fetch a single watch.
- `DELETE /api/watches/{id}` — delete a watch (cascades to its seen-match history).
- `POST /api/watches/{id}/run` — run a watch immediately; returns `WatchRunResult` with `new_matches`.
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
    tineye.py        # TinEye Search API (HMAC-signed)
  scanning.py        # Provider fan-out + dedupe (used by /api/scan and watches)
  watches.py         # Watch CRUD, per-watch scan diff, run logic
  scheduler.py       # In-process asyncio loop that runs due watches
  notifier.py        # Webhook dispatch
  db.py              # SQLite schema + connection helper
static/index.html    # Upload UI
```

## What's intentionally not here

- No face recognition or face embedding. Reverse image search matches the image, not the person.
- No bulk crawling, scraping, or platform-of-record violations. The app uses public search APIs that respect their own indexing rules.
- No identity aggregation — each match is a URL where the image was found, not a profile of a person.

## Roadmap

- Bing Visual Search
- Email (SMTP) notification channel in addition to webhooks
- Perceptual-hash pre-filter for near-duplicate detection on the user's own image library
- End-to-end validation of TinEye against live credentials
