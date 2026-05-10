from dataclasses import dataclass, field

import httpx


@dataclass
class RawMatch:
    url: str
    title: str | None = None
    thumbnail_url: str | None = None
    score: float | None = None


@dataclass
class ProviderResult:
    name: str
    matches: list[RawMatch] = field(default_factory=list)
    error: str | None = None


class Provider:
    name: str = "base"
    accepts_url: bool = False
    accepts_upload: bool = False

    def is_enabled(self) -> bool:
        return False

    def note(self) -> str | None:
        return None

    async def search(
        self,
        client: httpx.AsyncClient,
        *,
        image_url: str | None,
        image_bytes: bytes | None,
        image_filename: str | None,
    ) -> ProviderResult:
        raise NotImplementedError
