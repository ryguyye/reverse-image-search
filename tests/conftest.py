import pytest

from selfwatch import db
from selfwatch.config import settings


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    db.init()
    yield
