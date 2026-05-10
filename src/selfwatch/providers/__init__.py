from .base import Provider, ProviderResult, RawMatch
from .google_lens import GoogleLensProvider
from .tineye import TinEyeProvider
from .yandex import YandexProvider


def all_providers() -> list[Provider]:
    return [GoogleLensProvider(), YandexProvider(), TinEyeProvider()]


__all__ = [
    "Provider",
    "ProviderResult",
    "RawMatch",
    "GoogleLensProvider",
    "TinEyeProvider",
    "YandexProvider",
    "all_providers",
]
