from datetime import UTC, datetime, timedelta

import pytest

from selfwatch import watches
from selfwatch.models import Match


def test_create_and_get(temp_db):
    w = watches.create(
        name="me",
        cadence_minutes=10,
        webhook_url="https://hook.example/x",
        image_url="https://me.example/photo.jpg",
    )
    assert w.id > 0
    assert w.name == "me"
    fetched = watches.get(w.id)
    assert fetched.name == "me"
    assert fetched.image_url == "https://me.example/photo.jpg"


def test_create_requires_image(temp_db):
    with pytest.raises(ValueError):
        watches.create(name="x", cadence_minutes=10, webhook_url=None)


def test_create_with_email_requires_smtp(temp_db, monkeypatch):
    from selfwatch.config import settings

    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_from", None)
    with pytest.raises(ValueError, match="SMTP"):
        watches.create(
            name="x",
            cadence_minutes=10,
            webhook_url=None,
            notify_email="me@example.com",
            image_url="https://e.com/x",
        )


def test_create_with_email_succeeds_when_smtp_configured(temp_db, monkeypatch):
    from selfwatch.config import settings

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "noreply@example.com")
    w = watches.create(
        name="x",
        cadence_minutes=10,
        webhook_url=None,
        notify_email="me@example.com",
        image_url="https://e.com/x",
    )
    assert w.notify_email == "me@example.com"


def test_create_enforces_min_cadence(temp_db):
    with pytest.raises(ValueError, match="cadence_minutes"):
        watches.create(
            name="x",
            cadence_minutes=1,
            webhook_url=None,
            image_url="https://e.com/x",
        )


def test_list_and_delete(temp_db):
    w1 = watches.create(name="a", cadence_minutes=10, webhook_url=None, image_url="https://a.com/i")
    w2 = watches.create(name="b", cadence_minutes=10, webhook_url=None, image_url="https://b.com/i")
    listed = watches.list_all()
    assert {w.id for w in listed} == {w1.id, w2.id}
    assert watches.delete(w1.id) is True
    assert watches.delete(w1.id) is False
    assert {w.id for w in watches.list_all()} == {w2.id}


def test_due_includes_never_run(temp_db):
    w = watches.create(name="a", cadence_minutes=10, webhook_url=None, image_url="https://a.com/i")
    now = datetime.now(UTC)
    due = watches.due(now)
    assert any(x.id == w.id for x in due)


def test_due_respects_cadence(temp_db):
    w = watches.create(name="a", cadence_minutes=10, webhook_url=None, image_url="https://a.com/i")
    watches._mark_run(w.id, datetime.now(UTC))
    not_yet = watches.due(datetime.now(UTC) + timedelta(minutes=5))
    assert all(x.id != w.id for x in not_yet)
    later = watches.due(datetime.now(UTC) + timedelta(minutes=15))
    assert any(x.id == w.id for x in later)


def test_record_matches_returns_only_new(temp_db):
    w = watches.create(name="a", cadence_minutes=10, webhook_url=None, image_url="https://a.com/i")

    first = [
        Match(url="https://Example.com/foo/", domain="example.com", sources=["g"]),
        Match(url="https://other.com/x", domain="other.com", sources=["g"]),
    ]
    new1 = watches.record_matches(w.id, first)
    assert len(new1) == 2

    second = [
        Match(url="https://www.example.com/foo", domain="example.com", sources=["g"]),
        Match(url="https://fresh.com/y", domain="fresh.com", sources=["g"]),
    ]
    new2 = watches.record_matches(w.id, second)
    assert [m.url for m in new2] == ["https://fresh.com/y"]


def test_record_matches_handles_empty(temp_db):
    w = watches.create(name="a", cadence_minutes=10, webhook_url=None, image_url="https://a.com/i")
    assert watches.record_matches(w.id, []) == []


def test_set_active_toggles_and_excludes_from_due(temp_db):
    w = watches.create(name="a", cadence_minutes=10, webhook_url=None, image_url="https://a.com/i")
    paused = watches.set_active(w.id, False)
    assert paused is not None and paused.active is False
    assert all(x.id != w.id for x in watches.due(datetime.now(UTC)))
    resumed = watches.set_active(w.id, True)
    assert resumed.active is True
    assert any(x.id == w.id for x in watches.due(datetime.now(UTC)))


def test_set_active_returns_none_for_missing(temp_db):
    assert watches.set_active(999, False) is None


def test_list_matches_returns_history_with_timestamps(temp_db):
    w = watches.create(name="a", cadence_minutes=10, webhook_url=None, image_url="https://a.com/i")
    watches.record_matches(
        w.id,
        [
            Match(url="https://x.com/1", domain="x.com", title="t1", sources=["g"]),
            Match(url="https://x.com/2", domain="x.com", title="t2", sources=["g", "y"]),
        ],
    )
    history = watches.list_matches(w.id)
    assert len(history) == 2
    assert {m.canonical_url for m in history} == {"https://x.com/1", "https://x.com/2"}
    assert all(m.first_seen_at for m in history)
    multi = next(m for m in history if m.canonical_url == "https://x.com/2")
    assert sorted(multi.sources) == ["g", "y"]


def test_list_matches_pagination(temp_db):
    w = watches.create(name="a", cadence_minutes=10, webhook_url=None, image_url="https://a.com/i")
    watches.record_matches(
        w.id,
        [Match(url=f"https://x.com/{i}", domain="x.com", sources=["g"]) for i in range(5)],
    )
    page1 = watches.list_matches(w.id, limit=2, offset=0)
    page2 = watches.list_matches(w.id, limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {m.canonical_url for m in page1} & {m.canonical_url for m in page2} == set()


def test_resolve_image_url_uses_public_base(temp_db, monkeypatch):
    from selfwatch.config import settings

    monkeypatch.setattr(settings, "public_base_url", "https://my-host.example/")
    w = watches.create(
        name="upload",
        cadence_minutes=10,
        webhook_url=None,
        image_filename="abc123.jpg",
    )
    fetched = watches.get(w.id)
    assert watches._resolve_image_url(fetched) == "https://my-host.example/uploads/abc123.jpg"


def test_resolve_image_url_returns_none_when_base_missing(temp_db, monkeypatch):
    from selfwatch.config import settings

    monkeypatch.setattr(settings, "public_base_url", None)
    w = watches.create(
        name="upload",
        cadence_minutes=10,
        webhook_url=None,
        image_filename="abc123.jpg",
    )
    assert watches._resolve_image_url(watches.get(w.id)) is None
