from .base import Provider, ProviderResult, RawMatch
from .google_lens import GoogleLensProvider
from .yandex import YandexProvider


def all_providers() -> list[Provider]:
    return [GoogleLensProvider(), YandexProvider()]


__all__ = [
    "Provider",
    "ProviderResult",
    "RawMatch",
    "GoogleLensProvider",
    "YandexProvider",
    "all_providers",
]
