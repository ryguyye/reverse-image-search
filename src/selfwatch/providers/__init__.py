from .base import Provider, ProviderResult, RawMatch
from .bing import BingReverseImageProvider
from .google_lens import GoogleLensProvider
from .tineye import TinEyeProvider
from .yandex import YandexProvider


def all_providers() -> list[Provider]:
    return [
        GoogleLensProvider(),
        YandexProvider(),
        BingReverseImageProvider(),
        TinEyeProvider(),
    ]


__all__ = [
    "Provider",
    "ProviderResult",
    "RawMatch",
    "BingReverseImageProvider",
    "GoogleLensProvider",
    "TinEyeProvider",
    "YandexProvider",
    "all_providers",
]
