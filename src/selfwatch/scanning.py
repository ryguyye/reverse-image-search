import asyncio

import httpx

from .config import settings
from .dedupe import merge
from .models import ScanResponse
from .providers import all_providers
from .providers.base import ProviderResult


async def run_scan(
    *,
    image_url: str | None,
    image_bytes: bytes | None,
    image_filename: str | None,
) -> ScanResponse:
    providers = [p for p in all_providers() if p.is_enabled()]
    if not providers:
        return ScanResponse(
            providers_used=[],
            providers_failed=[{"name": "config", "error": "no providers enabled"}],
            matches=[],
        )

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        tasks = [
            p.search(
                client,
                image_url=image_url,
                image_bytes=image_bytes,
                image_filename=image_filename,
            )
            for p in providers
        ]
        results: list[ProviderResult] = await asyncio.gather(*tasks)

    used = [r.name for r in results if not r.error]
    failed = [{"name": r.name, "error": r.error} for r in results if r.error]
    return ScanResponse(providers_used=used, providers_failed=failed, matches=merge(results))
