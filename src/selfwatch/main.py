import asyncio
import secrets
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .dedupe import merge
from .models import ProviderInfo, ScanResponse
from .providers import all_providers
from .providers.base import ProviderResult

ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "static"
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

app = FastAPI(title="selfwatch", description="Self-monitoring reverse image search")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported content type: {file.content_type}")
        image_bytes = await file.read()
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 10 MB).")
        image_filename = file.filename
        upload_name = _save_upload(file, image_bytes)
        if not resolved_url:
            resolved_url = _public_url(request, upload_name)

    providers_list = [p for p in all_providers() if p.is_enabled()]
    if not providers_list:
        raise HTTPException(
            status_code=503,
            detail="No providers enabled. Set SERPAPI_KEY in .env to enable Google Lens / Yandex.",
        )

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        tasks = [
            p.search(
                client,
                image_url=resolved_url,
                image_bytes=image_bytes,
                image_filename=image_filename,
            )
            for p in providers_list
        ]
        results: list[ProviderResult] = await asyncio.gather(*tasks)

    used = [r.name for r in results if not r.error]
    failed = [{"name": r.name, "error": r.error} for r in results if r.error]
    return ScanResponse(providers_used=used, providers_failed=failed, matches=merge(results))
