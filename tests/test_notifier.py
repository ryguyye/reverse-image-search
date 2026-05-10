from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from selfwatch.config import settings
from selfwatch.notifier import send_email, send_webhook, smtp_configured


@respx.mock
async def test_send_webhook_returns_ok():
    route = respx.post("https://hook.example/x").mock(return_value=httpx.Response(200))
    status = await send_webhook("https://hook.example/x", {"hello": "world"})
    assert status == "ok"
    assert route.called
    assert route.calls.last.request.headers["content-type"].startswith("application/json")


@respx.mock
async def test_send_webhook_returns_error_on_http_failure():
    respx.post("https://hook.example/x").mock(return_value=httpx.Response(500))
    status = await send_webhook("https://hook.example/x", {"hello": "world"})
    assert status.startswith("error:")


@respx.mock
async def test_send_webhook_returns_error_on_network():
    respx.post("https://hook.example/x").mock(side_effect=httpx.ConnectError("boom"))
    status = await send_webhook("https://hook.example/x", {"hello": "world"})
    assert status.startswith("error:")


@pytest.fixture
def smtp_settings(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "user@example.com")
    monkeypatch.setattr(settings, "smtp_password", "secret")
    monkeypatch.setattr(settings, "smtp_from", "noreply@example.com")
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(settings, "smtp_starttls", True)


def test_smtp_configured_requires_host_and_from(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "smtp_from", None)
    assert smtp_configured() is False
    monkeypatch.setattr(settings, "smtp_host", "h")
    assert smtp_configured() is False
    monkeypatch.setattr(settings, "smtp_from", "f@x")
    assert smtp_configured() is True


async def test_send_email_returns_error_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    status = await send_email(to="a@b.com", subject="hi", body="hello")
    assert status.startswith("error:")


async def test_send_email_starttls_path(smtp_settings):
    fake_smtp = MagicMock()
    fake_smtp.return_value = fake_smtp
    with patch("selfwatch.notifier.smtplib.SMTP", return_value=fake_smtp) as smtp_cls:
        status = await send_email(to="dest@example.com", subject="hi", body="hello world")
    assert status == "ok"
    smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=settings.smtp_timeout)
    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once_with("user@example.com", "secret")
    sent_msg = fake_smtp.send_message.call_args.args[0]
    assert isinstance(sent_msg, EmailMessage)
    assert sent_msg["To"] == "dest@example.com"
    assert sent_msg["From"] == "noreply@example.com"
    assert sent_msg["Subject"] == "hi"
    assert "hello world" in sent_msg.get_content()


async def test_send_email_ssl_path(smtp_settings, monkeypatch):
    monkeypatch.setattr(settings, "smtp_use_ssl", True)
    monkeypatch.setattr(settings, "smtp_port", 465)
    fake_smtp = MagicMock()
    fake_smtp.return_value = fake_smtp
    with patch("selfwatch.notifier.smtplib.SMTP_SSL", return_value=fake_smtp) as smtp_cls, \
         patch("selfwatch.notifier.smtplib.SMTP") as plain_cls:
        status = await send_email(to="d@e.com", subject="s", body="b")
    assert status == "ok"
    smtp_cls.assert_called_once()
    plain_cls.assert_not_called()
    fake_smtp.starttls.assert_not_called()


async def test_send_email_returns_error_on_smtp_failure(smtp_settings):
    import smtplib

    def raise_err(*args, **kwargs):
        raise smtplib.SMTPException("relay denied")

    with patch("selfwatch.notifier.smtplib.SMTP", side_effect=raise_err):
        status = await send_email(to="d@e.com", subject="s", body="b")
    assert status.startswith("error:")
