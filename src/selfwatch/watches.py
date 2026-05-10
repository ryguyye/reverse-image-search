import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse, urlunparse

from . import db
from .config import settings
from .models import Match, Watch, WatchRunResult
from .notifier import send_webhook
from .scanning import run_scan

log = logging.getLogger(__name__)


def _row_to_watch(row) -> Watch:
    return Watch(
        id=row["id"],
        name=row["name"],
        image_url=row["image_url"],
        image_filename=row["image_filename"],
        cadence_minutes=row["cadence_minutes"],
        webhook_url=row["webhook_url"],
        active=bool(row["active"]),
        created_at=row["created_at"],
        last_run_at=row["last_run_at"],
    )


def create(
    *,
    name: str,
    cadence_minutes: int,
    webhook_url: str | None,
    image_url: str | None = None,
    image_filename: str | None = None,
) -> Watch:
    if not image_url and not image_filename:
        raise ValueError("Provide image_url or image_filename")
    if cadence_minutes < settings.min_cadence_minutes:
        raise ValueError(f"cadence_minutes must be >= {settings.min_cadence_minutes}")
    with db.connect() as conn:
        cur = conn.execute(
            """INSERT INTO watches (name, image_url, image_filename, cadence_minutes, webhook_url)
               VALUES (?, ?, ?, ?, ?)""",
            (name, image_url, image_filename, cadence_minutes, webhook_url),
        )
        watch_id = cur.lastrowid
        row = conn.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone()
    return _row_to_watch(row)


def list_all() -> list[Watch]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM watches ORDER BY id DESC").fetchall()
    return [_row_to_watch(r) for r in rows]


def get(watch_id: int) -> Watch | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone()
    return _row_to_watch(row) if row else None


def delete(watch_id: int) -> bool:
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
    return cur.rowcount > 0


def due(now: datetime) -> list[Watch]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM watches WHERE active = 1").fetchall()
    out: list[Watch] = []
    for r in rows:
        watch = _row_to_watch(r)
        if watch.last_run_at is None:
            out.append(watch)
            continue
        last = datetime.fromisoformat(watch.last_run_at).replace(tzinfo=UTC)
        if now >= last + timedelta(minutes=watch.cadence_minutes):
            out.append(watch)
    return out


def _canonicalize(url: str) -> str:
    p = urlparse(url)
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower() or "https", netloc, path, "", p.query, ""))


def seen_urls(watch_id: int) -> set[str]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT canonical_url FROM seen_matches WHERE watch_id = ?",
            (watch_id,),
        ).fetchall()
    return {r["canonical_url"] for r in rows}


def record_matches(watch_id: int, matches: list[Match]) -> list[Match]:
    """Persist matches and return only the ones not previously seen."""
    if not matches:
        return []
    seen = seen_urls(watch_id)
    new: list[Match] = []
    with db.connect() as conn:
        for m in matches:
            canon = _canonicalize(m.url)
            if canon in seen:
                continue
            conn.execute(
                """INSERT OR IGNORE INTO seen_matches
                   (watch_id, canonical_url, domain, title, thumbnail_url, sources)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (watch_id, canon, m.domain, m.title, m.thumbnail_url, json.dumps(m.sources)),
            )
            new.append(m)
    return new


def _mark_run(watch_id: int, when: datetime) -> None:
    with db.connect() as conn:
        conn.execute(
            "UPDATE watches SET last_run_at = ? WHERE id = ?",
            (when.replace(tzinfo=None).isoformat(timespec="seconds"), watch_id),
        )


def _resolve_image_url(watch: Watch) -> str | None:
    if watch.image_url:
        return watch.image_url
    if watch.image_filename and settings.public_base_url:
        base = settings.public_base_url.rstrip("/")
        return f"{base}/uploads/{watch.image_filename}"
    return None


async def run(watch: Watch) -> WatchRunResult:
    ran_at = datetime.now(UTC)
    image_url = _resolve_image_url(watch)
    if image_url is None:
        result = WatchRunResult(
            watch_id=watch.id,
            ran_at=ran_at.isoformat(timespec="seconds"),
            providers_used=[],
            providers_failed=[{"name": "config", "error": "uploaded image needs PUBLIC_BASE_URL"}],
            new_matches=[],
        )
        _mark_run(watch.id, ran_at)
        return result

    scan = await run_scan(image_url=image_url, image_bytes=None, image_filename=None)
    new = record_matches(watch.id, scan.matches)
    _mark_run(watch.id, ran_at)

    webhook_status: str | None = None
    if new and watch.webhook_url:
        webhook_status = await send_webhook(
            watch.webhook_url,
            {
                "watch_id": watch.id,
                "watch_name": watch.name,
                "scanned_at": ran_at.isoformat(timespec="seconds"),
                "image_url": image_url,
                "new_matches": [m.model_dump() for m in new],
            },
        )

    return WatchRunResult(
        watch_id=watch.id,
        ran_at=ran_at.isoformat(timespec="seconds"),
        providers_used=scan.providers_used,
        providers_failed=scan.providers_failed,
        new_matches=new,
        webhook_status=webhook_status,
    )
