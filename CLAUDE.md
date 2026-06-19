# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

selfwatch is a consent-based reverse image search tool: a user uploads their own image (or supplies a URL) and the app fans out to public reverse-image-search providers, returns deduplicated matches, and optionally rescans on a schedule with webhook/email notifications. The README's "What's intentionally not here" section is a real product constraint, not boilerplate — **do not add face recognition, identity aggregation, or person-search features**. New providers and features must work on individual images the user owns, not on people.

## Common commands

Everything in development goes through the Makefile:

- `make install` — create `.venv`, install runtime + dev deps
- `make dev` — uvicorn on `:8000` with reload (no proxy headers; for local browser use only)
- `make run` — uvicorn for production-ish use with `--proxy-headers --forwarded-allow-ips="*"` so `request.url_for` reconstructs `https://` URLs behind Cloudflare
- `make tunnel` — Cloudflare quick tunnel to localhost (no account needed); prints a `*.trycloudflare.com` URL to set as `PUBLIC_BASE_URL`
- `make test` — runs `ruff check src tests` then `pytest -q`
- `make tineye-ping ARGS="--image-url <url>"` — one-shot HMAC-signed call against TinEye to verify keys

Run a single test: `PYTHONPATH=src .venv/bin/pytest tests/test_watches.py::test_create_with_force_bypasses_duplicate_check -q`. CI (`.github/workflows/ci.yml`) runs three steps on Python 3.11 — `ruff check src tests`, a smoke `from selfwatch.main import app` import, then `pytest -q`.

Docker: `docker compose up -d --build`. The compose file pins `DB_PATH=/app/data/selfwatch.db` and `UPLOADS_DIR=/app/data/uploads` in its `environment:` block — those overrides matter because `env_file: .env` would otherwise leak the local-dev defaults into the container and silently move state off the named volume. Keep them in sync if you change the Dockerfile defaults.

## Architecture

### Provider plugin model (`src/selfwatch/providers/`)

Each provider subclasses `Provider` (in `base.py`) and implements `is_enabled()`, `note()`, and `async search(client, *, image_url, image_bytes, image_filename) -> ProviderResult`. They also declare `accepts_url` / `accepts_upload` — these are **metadata only**, surfaced via `/api/providers` for UI display. The dispatcher (`scanning.py`) does **not** filter by them: it calls every enabled provider with whatever inputs the scan supplied. A new provider must defensively return a `ProviderResult(error="...")` when called with an input shape it can't handle — see `google_lens.py` / `yandex.py` / `bing.py` for the pattern. `all_providers()` in `providers/__init__.py` is the single registration point. Adding a new provider = one file + one line in `__init__.py` + tests; nothing in the rest of the app needs to know about it.

Current providers: `google_lens` (SerpAPI), `yandex_images` (SerpAPI), `bing_reverse_image` (SerpAPI, **experimental** — Microsoft retired the official Bing Visual Search API in Aug 2025; the SerpAPI engine scrapes the public UI and may break upstream), `tineye` (direct API, HMAC-SHA256 signed; signing implemented per docs but not validated against live credentials — see `tineye_ping.py` for a self-service check).

The two SerpAPI providers require a **publicly reachable** image URL because SerpAPI fetches the image itself. That's why `PUBLIC_BASE_URL` exists for the recurring-scan path.

### Scan dispatch (`scanning.py`)

`run_scan` is the single fan-out path used by both `POST /api/scan` and the watch scheduler. It runs every enabled provider via `asyncio.gather`, then merges results through `dedupe.merge`, which canonicalizes URLs (strip `www.`, lowercase scheme/host, strip trailing `/`) so the same hit from multiple providers collapses to one `Match` with both source names listed.

### Watches (recurring scans)

Watches live in SQLite (`db.py`, schema in module-level `SCHEMA` plus an idempotent `_MIGRATIONS` dict that `ALTER TABLE`s in new columns on startup — when adding a column, update both `SCHEMA` *and* `_MIGRATIONS` so existing DBs upgrade in place).

Lifecycle:
- `POST /api/watches` → `main.py` reads upload bytes *or* calls `image_utils.fetch_image_bytes` (which runs `validate_fetch_url` first as the SSRF guard, then streams up to `MAX_FETCH_BYTES`) → `image_utils.compute_phash` on the bytes → `watches.create` checks near-duplicates via `find_near_duplicate` (Hamming distance ≤ 10) → 409 with `force=true` override path. On 409 or 400 the upload file is unlinked to avoid orphans.
- `scheduler.loop` is an asyncio task started from FastAPI `lifespan`. It ticks every `SCHEDULER_TICK_SECONDS` (default 60), calls `watches.due(now)` (filters by `active=1` and cadence), and runs each due watch via `watches.run` which goes through `run_scan` → `record_matches` (canonical-URL diff against `seen_matches`) → fires `send_webhook` + `send_email` only on **new** URLs.
- Tests patch `scheduler.loop` to a no-op via an **autouse** fixture in `tests/conftest.py` to keep the in-process scheduler from racing with `TestClient` lifespan during tests. Keep this fixture if you add scheduler-related tests.

### Sync DB layer, async I/O

`db.py`, `watches.py` (CRUD) are synchronous and use `sqlite3` directly. The HTTP and provider code is async via `httpx`. Email is sync (`smtplib`) wrapped in `asyncio.to_thread`. Do not introduce a different DB driver or ORM — the sync-with-explicit-async-boundary pattern is intentional for this single-process app.

### Settings

`config.py` uses `pydantic-settings` with `env_file=".env", extra="ignore"`. `settings` is a module-level singleton; tests `monkeypatch.setattr(settings, "...", ...)`. Anything that needs to be configurable belongs here, not as a function arg threaded through.

### UI

`static/index.html` is one file with vanilla JS (no framework, no build step). Server renders nothing — the page just calls the JSON API. Keep it that way unless there's a real reason; the appeal is zero-dep deployment.

## Conventions that aren't obvious

- **Provider response parsing is intentionally defensive** — third-party APIs change shapes. Each provider tries a few common response keys before giving up (see `yandex.py` and `bing.py` for the pattern). Add to that fallback list rather than asserting a single shape.
- **Provider failures are surfaced, not swallowed** — `providers_failed` in `ScanResponse` / `WatchRunResult` carries `{name, error}` so the UI/webhook payload shows which provider broke. Don't catch-and-ignore.
- **`force=true` on watch create** bypasses pHash dedup but still runs through SMTP/validation. UI handles the 409 with a confirm dialog and re-submits.
- **No auth** — the app assumes single-user behind your own access layer (Cloudflare Access is documented in `docs/deploy.md`). Don't add half-baked auth; if real auth is needed, do it properly.
- **`/docs` and `/openapi.json` are intentionally public** for now (FastAPI defaults). If you need to hide them, do it via env-flag in `main.py`.

## When adding features

- New env var → add to `Settings` in `config.py` *and* `.env.example` (commented if it's a Docker-only override; see `DB_PATH` / `UPLOADS_DIR`).
- New DB column → SQL in `SCHEMA` *and* tuple in `_MIGRATIONS[table]` (the migration runs on every `db.init()`).
- New provider → new file in `providers/`, register in `providers/__init__.py`, add a `test_<name>.py` with respx-mocked HTTP. The existing `test_bing.py` is the template.
- New endpoint → return a Pydantic model from `models.py`; add a `TestClient` test in `tests/test_main.py`. The autouse scheduler-disable fixture in `conftest.py` covers you.
- New roadmap-style work → branch as `claude/<short-name>`, PR against `main` (current convention).
