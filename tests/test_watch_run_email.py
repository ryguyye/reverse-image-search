"""End-to-end tests for the email notification path in watches.run()."""

from unittest.mock import AsyncMock, patch

import pytest

from selfwatch import watches
from selfwatch.config import settings
from selfwatch.models import Match, ScanResponse


@pytest.fixture
def smtp_on(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_from", "noreply@example.com")


async def test_run_sends_email_only_for_new_matches(temp_db, smtp_on):
    w = watches.create(
        name="me",
        cadence_minutes=10,
        webhook_url=None,
        notify_email="me@example.com",
        image_url="https://e.com/x",
    )

    fake_scan = ScanResponse(
        providers_used=["google_lens"],
        providers_failed=[],
        matches=[Match(url="https://impostor.com/p", domain="impostor.com", sources=["google_lens"])],
    )
    fake_send_email = AsyncMock(return_value="ok")

    with patch("selfwatch.watches.run_scan", AsyncMock(return_value=fake_scan)), \
         patch("selfwatch.watches.send_email", fake_send_email):
        result1 = await watches.run(watches.get(w.id))

    assert result1.email_status == "ok"
    fake_send_email.assert_called_once()
    args = fake_send_email.call_args.kwargs
    assert args["to"] == "me@example.com"
    assert "1 new match" in args["subject"]
    assert "impostor.com/p" in args["body"]

    # Second run with the same matches: no new ones, no email.
    fake_send_email.reset_mock()
    with patch("selfwatch.watches.run_scan", AsyncMock(return_value=fake_scan)), \
         patch("selfwatch.watches.send_email", fake_send_email):
        result2 = await watches.run(watches.get(w.id))

    assert result2.email_status is None
    fake_send_email.assert_not_called()


async def test_run_skips_email_when_not_set(temp_db):
    w = watches.create(
        name="me",
        cadence_minutes=10,
        webhook_url=None,
        image_url="https://e.com/x",
    )
    fake_scan = ScanResponse(
        providers_used=["g"],
        providers_failed=[],
        matches=[Match(url="https://x.com/p", domain="x.com", sources=["g"])],
    )
    fake_send_email = AsyncMock(return_value="ok")
    with patch("selfwatch.watches.run_scan", AsyncMock(return_value=fake_scan)), \
         patch("selfwatch.watches.send_email", fake_send_email):
        result = await watches.run(watches.get(w.id))
    assert result.email_status is None
    fake_send_email.assert_not_called()


async def test_run_propagates_email_send_failure(temp_db, smtp_on):
    w = watches.create(
        name="me",
        cadence_minutes=10,
        webhook_url=None,
        notify_email="me@example.com",
        image_url="https://e.com/x",
    )
    fake_scan = ScanResponse(
        providers_used=["g"],
        providers_failed=[],
        matches=[Match(url="https://x.com/p", domain="x.com", sources=["g"])],
    )
    fake_send_email = AsyncMock(return_value="error: relay denied")
    with patch("selfwatch.watches.run_scan", AsyncMock(return_value=fake_scan)), \
         patch("selfwatch.watches.send_email", fake_send_email):
        result = await watches.run(watches.get(w.id))
    assert result.email_status == "error: relay denied"
