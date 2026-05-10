import httpx
import pytest
import respx

from selfwatch import config as cfg
from selfwatch.providers.bing import SERPAPI_URL, BingReverseImageProvider


@pytest.fixture
def serpapi_key(monkeypatch):
    monkeypatch.setattr(cfg.settings, "serpapi_key", "key")


def test_disabled_without_key(monkeypatch):
    monkeypatch.setattr(cfg.settings, "serpapi_key", None)
    p = BingReverseImageProvider()
    assert p.is_enabled() is False
    assert "SERPAPI_KEY" in (p.note() or "")


def test_enabled_with_key(serpapi_key):
    p = BingReverseImageProvider()
    assert p.is_enabled() is True
    note = p.note() or ""
    assert "Experimental" in note


async def test_search_without_image_url(serpapi_key):
    async with httpx.AsyncClient() as client:
        result = await BingReverseImageProvider().search(
            client, image_url=None, image_bytes=None, image_filename=None
        )
    assert result.error is not None
    assert "image URL" in result.error


@respx.mock
async def test_search_extracts_pages_with_matching_images(serpapi_key):
    respx.get(SERPAPI_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "pages_with_matching_images": [
                    {"link": "https://example.com/p1", "title": "match 1", "thumbnail": "t1.jpg"},
                    {"url": "https://example.com/p2", "name": "match 2"},
                ]
            },
        )
    )
    async with httpx.AsyncClient() as client:
        result = await BingReverseImageProvider().search(
            client,
            image_url="https://me.example/me.jpg",
            image_bytes=None,
            image_filename=None,
        )
    assert result.error is None
    assert [m.url for m in result.matches] == [
        "https://example.com/p1",
        "https://example.com/p2",
    ]
    assert result.matches[0].title == "match 1"
    assert result.matches[1].title == "match 2"


@respx.mock
async def test_search_falls_back_to_image_results_shape(serpapi_key):
    respx.get(SERPAPI_URL).mock(
        return_value=httpx.Response(
            200,
            json={"image_results": [{"link": "https://other.example/x"}]},
        )
    )
    async with httpx.AsyncClient() as client:
        result = await BingReverseImageProvider().search(
            client,
            image_url="https://me.example/me.jpg",
            image_bytes=None,
            image_filename=None,
        )
    assert [m.url for m in result.matches] == ["https://other.example/x"]


@respx.mock
async def test_search_propagates_http_error(serpapi_key):
    respx.get(SERPAPI_URL).mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        result = await BingReverseImageProvider().search(
            client,
            image_url="https://me.example/me.jpg",
            image_bytes=None,
            image_filename=None,
        )
    assert result.error is not None
    assert result.matches == []


@respx.mock
async def test_search_sends_engine_and_image_url(serpapi_key):
    route = respx.get(SERPAPI_URL).mock(
        return_value=httpx.Response(200, json={"pages_with_matching_images": []})
    )
    async with httpx.AsyncClient() as client:
        await BingReverseImageProvider().search(
            client,
            image_url="https://me.example/me.jpg",
            image_bytes=None,
            image_filename=None,
        )
    sent = route.calls.last.request
    assert sent.url.params["engine"] == "bing_reverse_image"
    assert sent.url.params["image_url"] == "https://me.example/me.jpg"
    assert sent.url.params["api_key"] == "key"
