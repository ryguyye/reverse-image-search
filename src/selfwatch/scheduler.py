import asyncio
import logging
from datetime import UTC, datetime

from . import watches
from .config import settings

log = logging.getLogger(__name__)


async def tick() -> int:
    now = datetime.now(UTC)
    due_watches = watches.due(now)
    for watch in due_watches:
        try:
            await watches.run(watch)
        except Exception:
            log.exception("watch %s failed", watch.id)
    return len(due_watches)


async def loop() -> None:
    log.info("scheduler started (tick=%ss)", settings.scheduler_tick_seconds)
    try:
        while True:
            try:
                await tick()
            except Exception:
                log.exception("scheduler tick raised")
            await asyncio.sleep(settings.scheduler_tick_seconds)
    except asyncio.CancelledError:
        log.info("scheduler stopped")
        raise
