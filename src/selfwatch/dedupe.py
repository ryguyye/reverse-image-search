from urllib.parse import urlparse, urlunparse

from .models import Match
from .providers.base import ProviderResult


def _canonicalize(url: str) -> str:
    p = urlparse(url)
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower() or "https", netloc, path, "", p.query, ""))


def _domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def merge(results: list[ProviderResult]) -> list[Match]:
    by_key: dict[str, Match] = {}
    for result in results:
        for raw in result.matches:
            key = _canonicalize(raw.url)
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = Match(
                    url=raw.url,
                    domain=_domain(raw.url),
                    title=raw.title,
                    thumbnail_url=raw.thumbnail_url,
                    sources=[result.name],
                    score=raw.score,
                )
            else:
                if result.name not in existing.sources:
                    existing.sources.append(result.name)
                if not existing.title and raw.title:
                    existing.title = raw.title
                if not existing.thumbnail_url and raw.thumbnail_url:
                    existing.thumbnail_url = raw.thumbnail_url
    merged = list(by_key.values())
    merged.sort(key=lambda m: (-len(m.sources), m.domain))
    return merged
