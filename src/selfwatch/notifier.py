import asyncio
import logging
import smtplib
from email.message import EmailMessage

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


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


async def send_email(*, to: str, subject: str, body: str) -> str:
    """Send a plaintext email via configured SMTP. Returns "ok" or error message."""
    if not smtp_configured():
        return "error: SMTP not configured (set SMTP_HOST and SMTP_FROM)"

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    def _send_sync() -> None:
        if settings.smtp_use_ssl:
            client = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout
            )
        else:
            client = smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout
            )
        try:
            if not settings.smtp_use_ssl and settings.smtp_starttls:
                client.starttls()
            if settings.smtp_user:
                client.login(settings.smtp_user, settings.smtp_password or "")
            client.send_message(msg)
        finally:
            client.quit()

    try:
        await asyncio.to_thread(_send_sync)
        return "ok"
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("email to %s failed: %s", to, exc)
        return f"error: {exc}"
