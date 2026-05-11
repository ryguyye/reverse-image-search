import asyncio
from io import BytesIO

import pytest
from PIL import Image

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


def make_image_bytes(*, color: tuple[int, int, int] = (200, 50, 30), size: int = 96) -> bytes:
    """Generate a small PNG with a simple gradient — distinct enough for pHash testing."""
    img = Image.new("RGB", (size, size), color)
    pixels = img.load()
    for y in range(size):
        for x in range(size):
            pixels[x, y] = (
                (color[0] + x) % 256,
                (color[1] + y) % 256,
                (color[2] + (x + y)) % 256,
            )
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def image_bytes_red() -> bytes:
    return make_image_bytes(color=(220, 10, 10))


@pytest.fixture
def image_bytes_blue() -> bytes:
    return make_image_bytes(color=(10, 10, 220))
