import hashlib
import hmac
from urllib.parse import urlencode

import httpx
import pytest
import respx

from selfwatch import config as cfg
from selfwatch.providers.tineye import (
    TINEYE_URL,
    TinEyeProvider,
    _parse_response,
    _sign_get,
    _sign_post_multipart,
)


def test_sign_get_matches_manual_hmac():
    sig = _sign_get(
        private_key="priv",
        api_key="pub",
        date=1700000000,
        nonce="abc",
        extra={"image_url": "https://x.com/y.jpg"},
    )
    qs = urlencode(
        sorted(
            {
                "api_key": "pub",
                "date": "1700000000",
                "nonce": "abc",
                "image_url": "https://x.com/y.jpg",
            }.items()
        )
    )
    expected_string = "priv" + "GET" + "1700000000" + "abc" + f"{TINEYE_URL}?{qs}"
    expected = hmac.new(b"priv", expected_string.encode(), hashlib.sha256).hexdigest()
    assert sig == expected


def test_sign_post_multipart_includes_filename_and_content_type():
    sig = _sign_post_multipart(
        private_key="priv",
        api_key="pub",
        image_filename="me.jpg",
        content_type="multipart/form-data; boundary=ZZZ",
        date=1700000000,
        nonce="abc",
    )
    qs = urlencode(
        sorted({"api_key": "pub", "date": "1700000000", "nonce": "abc"}.items())
    )
    expected_string = (
        "priv"
        + "POST"
        + "multipart/form-data; boundary=zzz"
        + "me.jpg"
        + "1700000000"
        + "abc"
        + f"{TINEYE_URL}?{qs}"
    )
    expected = hmac.new(b"priv", expected_string.encode(), hashlib.sha256).hexdigest()
    assert sig == expected


def test_parse_response_extracts_backlinks():
    payload = {
        "code": 200,
        "results": {
            "matches": [
                {
                    "score": 95.0,
                    "domain": "example.com",
                    "image_url": "https://example.com/img.jpg",
                    "backlinks": [
                        {"backlink": "https://example.com/page1", "url": "https://example.com/img.jpg"},
                        {"backlink": "https://example.com/page2"},
                    ],
                }
            ]
        },
    }
    result = _parse_response(payload, max_results=10)
    assert result.error is None
    assert [m.url for m in result.matches] == [
        "https://example.com/page1",
        "https://example.com/page2",
    ]
    assert all(m.score == 95.0 for m in result.matches)
    assert all(m.thumbnail_url == "https://example.com/img.jpg" for m in result.matches)


def test_parse_response_propagates_api_error():
    result = _parse_response({"code": 401, "messages": ["Bad sig"]}, max_results=10)
    assert result.error is not None
    assert "401" in result.error


def test_parse_response_respects_max_results():
    payload = {
        "code": 200,
        "results": {
            "matches": [
                {
                    "domain": "example.com",
                    "image_url": "https://example.com/img.jpg",
                    "backlinks": [{"backlink": f"https://example.com/p{i}"} for i in range(20)],
                }
            ]
        },
    }
    result = _parse_response(payload, max_results=5)
    assert len(result.matches) == 5


@pytest.fixture
def tineye_creds(monkeypatch):
    monkeypatch.setattr(cfg.settings, "tineye_api_key", "pub")
    monkeypatch.setattr(cfg.settings, "tineye_private_key", "priv")


@respx.mock
async def test_search_with_image_url_hits_get_with_signature(tineye_creds):
    route = respx.get(TINEYE_URL).mock(
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
    async with httpx.AsyncClient() as client:
        result = await TinEyeProvider().search(
            client,
            image_url="https://me.example/me.jpg",
            image_bytes=None,
            image_filename=None,
        )
    assert route.called
    sent = route.calls.last.request
    qs = dict(sent.url.params)
    assert qs["api_key"] == "pub"
    assert "api_sig" in qs and len(qs["api_sig"]) == 64
    assert qs["image_url"] == "https://me.example/me.jpg"
    assert [m.url for m in result.matches] == ["https://found.com/page"]


@respx.mock
async def test_search_with_upload_posts_multipart(tineye_creds):
    route = respx.post(TINEYE_URL).mock(
        return_value=httpx.Response(200, json={"code": 200, "results": {"matches": []}})
    )
    async with httpx.AsyncClient() as client:
        result = await TinEyeProvider().search(
            client,
            image_url=None,
            image_bytes=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
            image_filename="me.png",
        )
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert b'name="image_upload"' in sent.content
    assert b'filename="me.png"' in sent.content
    assert result.error is None


async def test_search_without_credentials_returns_error():
    async with httpx.AsyncClient() as client:
        result = await TinEyeProvider().search(
            client, image_url="https://x.com/y", image_bytes=None, image_filename=None
        )
    assert result.error == "missing TinEye credentials"
