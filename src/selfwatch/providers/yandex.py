import httpx

from ..config import settings
from .base import Provider, ProviderResult, RawMatch

SERPAPI_URL = "https://serpapi.com/search.json"


class YandexProvider(Provider):
    name = "yandex_images"
    accepts_url = True
    accepts_upload = False

    def is_enabled(self) -> bool:
        return bool(settings.serpapi_key)

    def note(self) -> str | None:
        if not settings.serpapi_key:
            return "Set SERPAPI_KEY to enable."
        return "Requires a publicly reachable image URL."

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
                error="yandex_images requires a public image URL",
            )
        params = {
            "engine": "yandex_images",
            "url": image_url,
            "api_key": settings.serpapi_key,
        }
        try:
            resp = await client.get(SERPAPI_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            return ProviderResult(name=self.name, error=str(exc))

        matches: list[RawMatch] = []
        sites = data.get("sites_with_image") or data.get("images_results") or []
        for item in sites[: settings.max_results_per_provider]:
            link = item.get("link") or item.get("url")
            if not link:
                continue
            matches.append(
                RawMatch(
                    url=link,
                    title=item.get("title") or item.get("source"),
                    thumbnail_url=item.get("thumbnail") or item.get("original_image"),
                )
            )
        return ProviderResult(name=self.name, matches=matches)
