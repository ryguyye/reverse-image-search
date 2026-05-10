import httpx

from ..config import settings
from .base import Provider, ProviderResult, RawMatch

SERPAPI_URL = "https://serpapi.com/search.json"


class BingReverseImageProvider(Provider):
    """SerpAPI Bing Reverse Image (engine=bing_reverse_image).

    Microsoft retired the official Bing Visual Search API on 2025-08-11.
    SerpAPI scrapes Bing's public reverse-image UI and exposes a structured
    response. This provider is therefore subject to upstream UI changes and
    may break with no warning.
    """

    name = "bing_reverse_image"
    accepts_url = True
    accepts_upload = False

    def is_enabled(self) -> bool:
        return bool(settings.serpapi_key)

    def note(self) -> str | None:
        if not settings.serpapi_key:
            return "Set SERPAPI_KEY to enable."
        return (
            "Experimental — Microsoft retired the official Bing Visual Search API in 2025. "
            "Results come from SerpAPI scraping Bing's public UI and may break upstream."
        )

    async def search(
        self,
        client: httpx.AsyncClient,
        *,
        image_url: str | None,
        image_bytes: bytes | None,
        image_filename: str | None,
    ) -> ProviderResult:
        if not image_url:
            return ProviderResult(
                name=self.name,
                error="bing_reverse_image requires a public image URL",
            )
        params = {
            "engine": "bing_reverse_image",
            "image_url": image_url,
            "api_key": settings.serpapi_key,
        }
        try:
            resp = await client.get(SERPAPI_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return ProviderResult(name=self.name, error=str(exc))

        matches: list[RawMatch] = []
        candidates = (
            data.get("pages_with_matching_images")
            or data.get("image_results")
            or data.get("visual_matches")
            or data.get("inline_images")
            or []
        )
        for item in candidates[: settings.max_results_per_provider]:
            link = item.get("link") or item.get("url") or item.get("source")
            if not link:
                continue
            matches.append(
                RawMatch(
                    url=link,
                    title=item.get("title") or item.get("name"),
                    thumbnail_url=item.get("thumbnail") or item.get("image"),
                )
            )
        return ProviderResult(name=self.name, matches=matches)
