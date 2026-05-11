"""Perceptual-hash helpers for near-duplicate detection on watch images."""

import ipaddress
import logging
import socket
from io import BytesIO
from urllib.parse import urlparse

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
_STREAM_CHUNK = 64 * 1024


def compute_phash(image_bytes: bytes) -> str | None:
    """Return a hex pHash of the image, or None if the bytes aren't a valid image."""
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            return str(imagehash.phash(img))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        log.warning("phash decode failed: %s", exc)
        return None


def validate_fetch_url(url: str) -> str | None:
    """Return None if the URL is safe to fetch, else a short error message.

    Blocks non-http(s) schemes and hostnames that resolve to loopback, link-local
    (incl. cloud metadata 169.254.169.254), private RFC1918, multicast, reserved,
    or unspecified addresses. Mitigates SSRF on the duplicate-detection fetch path.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return "invalid url"
    if parsed.scheme not in ("http", "https"):
        return f"scheme {parsed.scheme!r} not allowed"
    hostname = parsed.hostname
    if not hostname:
        return "missing hostname"
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return "hostname did not resolve"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return f"host resolves to non-public address {ip}"
    return None


async def fetch_image_bytes(url: str, client: httpx.AsyncClient | None = None) -> bytes | None:
    """Fetch an image from URL with SSRF + size guards. Returns bytes or None."""
    err = validate_fetch_url(url)
    if err:
        log.warning("refusing to fetch %s: %s", url, err)
        return None

    own_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.http_timeout)
    try:
        chunks: list[bytes] = []
        total = 0
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(chunk_size=_STREAM_CHUNK):
                chunks.append(chunk)
                total += len(chunk)
                if total >= MAX_FETCH_BYTES:
                    log.warning("image at %s exceeded %s bytes; truncating", url, MAX_FETCH_BYTES)
                    return b"".join(chunks)[:MAX_FETCH_BYTES]
        return b"".join(chunks)
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
