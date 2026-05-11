"""Perceptual-hash helpers for near-duplicate detection on watch images."""

import logging
from io import BytesIO

import httpx
import imagehash
from PIL import Image, UnidentifiedImageError

from .config import settings

log = logging.getLogger(__name__)

# Hamming distance ≤ this counts as "near-duplicate" for a 64-bit pHash.
# 10 is a common threshold in the imagehash literature for "looks the same"
# while still rejecting unrelated images.
DUPLICATE_THRESHOLD = 10

MAX_FETCH_BYTES = 10 * 1024 * 1024


def compute_phash(image_bytes: bytes) -> str | None:
    """Return a hex pHash of the image, or None if the bytes aren't a valid image."""
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            return str(imagehash.phash(img))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        log.warning("phash decode failed: %s", exc)
        return None


async def fetch_image_bytes(url: str, client: httpx.AsyncClient | None = None) -> bytes | None:
    """Fetch an image from URL, returning bytes (capped) or None on any error."""
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.http_timeout)
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content
        if len(data) > MAX_FETCH_BYTES:
            log.warning("image at %s exceeds max fetch size; truncating", url)
            return data[:MAX_FETCH_BYTES]
        return data
    except httpx.HTTPError as exc:
        log.warning("image fetch from %s failed: %s", url, exc)
        return None
    finally:
        if own_client:
            await client.aclose()


def hamming_distance(a: str, b: str) -> int:
    """Hamming distance between two hex pHash strings."""
    # imagehash returns numpy int64; cast to plain int for JSON serializability.
    return int(imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b))
