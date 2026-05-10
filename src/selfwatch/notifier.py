import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)


async def send_webhook(url: str, payload: dict) -> str:
    """POST payload as JSON to url. Returns "ok" on success, error message otherwise.

    Fire-and-forget semantics: errors are logged and returned, not raised.
    """
    try:
        async with httpx.AsyncClient(timeout=settings.webhook_timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return "ok"
    except httpx.HTTPError as exc:
        log.warning("webhook %s failed: %s", url, exc)
        return f"error: {exc}"
