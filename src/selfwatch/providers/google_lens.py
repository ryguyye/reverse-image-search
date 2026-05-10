import httpx

from ..config import settings
from .base import Provider, ProviderResult, RawMatch

SERPAPI_URL = "https://serpapi.com/search.json"


class GoogleLensProvider(Provider):
    name = "google_lens"
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
                error="google_lens requires a public image URL",
            )
        params = {
            "engine": "google_lens",
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
        for item in (data.get("visual_matches") or [])[: settings.max_results_per_provider]:
            link = item.get("link")
            if not link:
                continue
            matches.append(
                RawMatch(
                    url=link,
                    title=item.get("title"),
                    thumbnail_url=item.get("thumbnail"),
                )
            )
        return ProviderResult(name=self.name, matches=matches)
