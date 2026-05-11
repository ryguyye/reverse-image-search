import httpx
import pytest
import respx

from selfwatch import config as cfg
from selfwatch.providers.tineye import TINEYE_URL
from selfwatch.tineye_ping import main


@pytest.fixture
def tineye_creds(monkeypatch):
    monkeypatch.setattr(cfg.settings, "tineye_api_key", "pub")
    monkeypatch.setattr(cfg.settings, "tineye_private_key", "priv")


def test_exits_1_when_credentials_missing(monkeypatch, capsys):
    monkeypatch.setattr(cfg.settings, "tineye_api_key", None)
    monkeypatch.setattr(cfg.settings, "tineye_private_key", None)
    rc = main(["--image-url", "https://example.com/x.jpg"])
    assert rc == 1
    assert "TINEYE_API_KEY" in capsys.readouterr().err


def test_exits_1_when_file_missing(tineye_creds, tmp_path, capsys):
    rc = main(["--file", str(tmp_path / "nope.jpg")])
    assert rc == 1
    assert "file not found" in capsys.readouterr().err


@respx.mock
def test_url_ping_success_exits_0(tineye_creds, capsys):
    respx.get(TINEYE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 200,
                "results": {
                    "matches": [
                        {
                            "domain": "found.com",
                            "image_url": "https://found.com/i.jpg",
                            "backlinks": [{"backlink": "https://found.com/page"}],
                        }
                    ]
                },
            },
        )
    )
    rc = main(["--image-url", "https://me.example/me.jpg"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "OK" in captured.out
    assert "1 match" in captured.out


@respx.mock
def test_url_ping_returns_1_on_http_error(tineye_creds, capsys):
    respx.get(TINEYE_URL).mock(return_value=httpx.Response(401, json={"messages": ["Bad sig"]}))
    rc = main(["--image-url", "https://me.example/me.jpg"])
    assert rc == 1
    assert "status: 401" in capsys.readouterr().out


@respx.mock
def test_url_ping_returns_1_when_response_signals_provider_error(tineye_creds, capsys):
    respx.get(TINEYE_URL).mock(
        return_value=httpx.Response(200, json={"code": 401, "messages": ["bad sig"]})
    )
    rc = main(["--image-url", "https://me.example/me.jpg"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "error:" in captured.err


@respx.mock
def test_file_ping_posts_multipart(tineye_creds, tmp_path, image_bytes_red, capsys):
    img = tmp_path / "me.png"
    img.write_bytes(image_bytes_red)
    route = respx.post(TINEYE_URL).mock(
        return_value=httpx.Response(200, json={"code": 200, "results": {"matches": []}})
    )
    rc = main(["--file", str(img)])
    assert rc == 0
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert b"me.png" in sent.content
    assert "OK" in capsys.readouterr().out


@respx.mock
def test_verbose_masks_api_key(tineye_creds, capsys):
    respx.get(TINEYE_URL).mock(
        return_value=httpx.Response(200, json={"code": 200, "results": {"matches": []}})
    )
    main(["--image-url", "https://me.example/me.jpg", "--verbose"])
    out = capsys.readouterr().out
    assert "***" in out
    assert "pub" not in out.split("\nstatus:")[0]  # api key masked in the params block
