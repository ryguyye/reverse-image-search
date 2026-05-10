import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, scheduler, watches
from .models import (
    ProviderInfo,
    ScanResponse,
    SeenMatch,
    Watch,
    WatchRunResult,
    WatchUpdate,
)
from .providers import all_providers
from .scanning import run_scan

ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "static"
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    task = asyncio.create_task(scheduler.loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="selfwatch",
    description="Self-monitoring reverse image search",
    lifespan=lifespan,
)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/healthz")
async def healthz() -> dict:
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1")
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"
    return {"status": "ok" if db_status == "ok" else "degraded", "db": db_status}


@app.get("/api/providers", response_model=list[ProviderInfo])
async def providers() -> list[ProviderInfo]:
    return [
        ProviderInfo(
            name=p.name,
            enabled=p.is_enabled(),
            accepts_url=p.accepts_url,
            accepts_upload=p.accepts_upload,
            note=p.note(),
        )
        for p in all_providers()
    ]


def _save_upload(file: UploadFile, data: bytes) -> str:
    suffix = Path(file.filename or "upload").suffix.lower() or ".bin"
    name = f"{secrets.token_urlsafe(12)}{suffix}"
    (UPLOAD_DIR / name).write_bytes(data)
    return name


def _public_url(request: Request, upload_name: str) -> str:
    return str(request.url_for("uploads", path=upload_name))


async def _read_upload(file: UploadFile) -> bytes:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {file.content_type}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB).")
    return data


@app.post("/api/scan", response_model=ScanResponse)
async def scan(
    request: Request,
    image_url: str | None = Form(default=None),
    file: UploadFile | None = None,
) -> ScanResponse:
    if not image_url and not file:
        raise HTTPException(status_code=400, detail="Provide image_url or file.")

    image_bytes: bytes | None = None
    image_filename: str | None = None
    resolved_url = image_url

    if file is not None and file.filename:
        image_bytes = await _read_upload(file)
        image_filename = file.filename
        upload_name = _save_upload(file, image_bytes)
        if not resolved_url:
            resolved_url = _public_url(request, upload_name)

    result = await run_scan(
        image_url=resolved_url,
        image_bytes=image_bytes,
        image_filename=image_filename,
    )
    if not result.providers_used and any(
        f.get("name") == "config" for f in result.providers_failed
    ):
        raise HTTPException(
            status_code=503,
            detail="No providers enabled. Set SERPAPI_KEY in .env to enable Google Lens / Yandex.",
        )
    return result


@app.get("/api/watches", response_model=list[Watch])
async def list_watches() -> list[Watch]:
    return watches.list_all()


@app.post("/api/watches", response_model=Watch, status_code=201)
async def create_watch(
    name: str = Form(...),
    cadence_minutes: int = Form(...),
    webhook_url: str | None = Form(default=None),
    image_url: str | None = Form(default=None),
    file: UploadFile | None = None,
) -> Watch:
    if not image_url and not (file and file.filename):
        raise HTTPException(status_code=400, detail="Provide image_url or file.")

    image_filename: str | None = None
    if file is not None and file.filename:
        data = await _read_upload(file)
        image_filename = _save_upload(file, data)

    try:
        return watches.create(
            name=name,
            cadence_minutes=cadence_minutes,
            webhook_url=webhook_url,
            image_url=image_url,
            image_filename=image_filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/watches/{watch_id}", response_model=Watch)
async def get_watch(watch_id: int) -> Watch:
    watch = watches.get(watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="Watch not found.")
    return watch


@app.delete("/api/watches/{watch_id}", status_code=204)
async def delete_watch(watch_id: int) -> None:
    if not watches.delete(watch_id):
        raise HTTPException(status_code=404, detail="Watch not found.")


@app.patch("/api/watches/{watch_id}", response_model=Watch)
async def update_watch(watch_id: int, body: WatchUpdate) -> Watch:
    if body.active is None:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    updated = watches.set_active(watch_id, body.active)
    if updated is None:
        raise HTTPException(status_code=404, detail="Watch not found.")
    return updated


@app.get("/api/watches/{watch_id}/matches", response_model=list[SeenMatch])
async def list_watch_matches(
    watch_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[SeenMatch]:
    if watches.get(watch_id) is None:
        raise HTTPException(status_code=404, detail="Watch not found.")
    return watches.list_matches(watch_id, limit=limit, offset=offset)


@app.post("/api/watches/{watch_id}/run", response_model=WatchRunResult)
async def run_watch_now(watch_id: int) -> WatchRunResult:
    watch = watches.get(watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="Watch not found.")
    return await watches.run(watch)
