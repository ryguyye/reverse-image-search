import asyncio

import pytest

from selfwatch import db
from selfwatch.config import settings


@pytest.fixture(autouse=True)
def disable_scheduler(monkeypatch):
    """Stop the in-process scheduler from racing with tests that use TestClient."""

    async def noop() -> None:
        await asyncio.sleep(0)

    monkeypatch.setattr("selfwatch.scheduler.loop", noop)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    db.init()
    yield
