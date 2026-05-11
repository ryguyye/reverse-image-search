"""TinEye credential ping — validate live API + HMAC signing in one shot.

Usage:
    python -m selfwatch.tineye_ping --image-url https://example.com/photo.jpg
    python -m selfwatch.tineye_ping --file ./photo.jpg [--verbose]

Reads TINEYE_API_KEY and TINEYE_PRIVATE_KEY from .env / environment. Prints
the request, the raw JSON response, and a parsed summary. Exit code 0 on
HTTP 200 with no provider error, 1 otherwise — handy to wire up in CI or
just run by hand to verify a TinEye account works.
"""

import argparse
import asyncio
import json
import secrets
import sys
import time
from pathlib import Path

import httpx

from .config import settings
from .providers.tineye import (
    TINEYE_URL,
    _build_multipart,
    _parse_response,
    _sign_get,
    _sign_post_multipart,
)


def _credentials() -> tuple[str, str] | None:
    if not (settings.tineye_api_key and settings.tineye_private_key):
        print(
            "error: TINEYE_API_KEY and TINEYE_PRIVATE_KEY must be set in .env / env",
            file=sys.stderr,
        )
        return None
    return settings.tineye_api_key, settings.tineye_private_key


def _report(resp: httpx.Response) -> int:
    print(f"status: {resp.status_code}")
    try:
        data = resp.json()
    except json.JSONDecodeError:
        print(resp.text)
        return 1
    print(json.dumps(data, indent=2))
    if resp.status_code != 200:
        return 1
    parsed = _parse_response(data, max_results=10)
    if parsed.error:
        print(f"\nerror: {parsed.error}", file=sys.stderr)
        return 1
    print(f"\nOK — {len(parsed.matches)} match(es)")
    return 0


async def _ping_url(image_url: str, verbose: bool) -> int:
    creds = _credentials()
    if creds is None:
        return 1
    api_key, private_key = creds

    date = int(time.time())
    nonce = secrets.token_hex(16)
    api_sig = _sign_get(
        private_key=private_key,
        api_key=api_key,
        date=date,
        nonce=nonce,
        extra={"image_url": image_url},
    )
    params = {
        "api_key": api_key,
        "date": str(date),
        "nonce": nonce,
        "image_url": image_url,
        "api_sig": api_sig,
    }
    print(f"GET {TINEYE_URL}")
    if verbose:
        print(json.dumps({k: ("***" if k == "api_key" else v) for k, v in params.items()}, indent=2))
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            resp = await client.get(TINEYE_URL, params=params)
    except httpx.HTTPError as exc:
        print(f"error: network failure: {exc}", file=sys.stderr)
        return 1
    return _report(resp)


async def _ping_file(path: Path, verbose: bool) -> int:
    creds = _credentials()
    if creds is None:
        return 1
    api_key, private_key = creds
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1

    image_bytes = path.read_bytes()
    body, content_type, safe_filename = _build_multipart(image_bytes, path.name)

    date = int(time.time())
    nonce = secrets.token_hex(16)
    api_sig = _sign_post_multipart(
        private_key=private_key,
        api_key=api_key,
        image_filename=safe_filename,
        content_type=content_type,
        date=date,
        nonce=nonce,
    )
    params = {"api_key": api_key, "date": str(date), "nonce": nonce, "api_sig": api_sig}
    print(f"POST {TINEYE_URL} (multipart, {len(image_bytes)} bytes, filename={safe_filename!r})")
    if verbose:
        print(json.dumps({k: ("***" if k == "api_key" else v) for k, v in params.items()}, indent=2))
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            resp = await client.post(
                TINEYE_URL,
                params=params,
                content=body,
                headers={"Content-Type": content_type},
            )
    except httpx.HTTPError as exc:
        print(f"error: network failure: {exc}", file=sys.stderr)
        return 1
    return _report(resp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="selfwatch.tineye_ping", description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--image-url", help="Public URL of an image to search")
    src.add_argument("--file", type=Path, help="Local path to an image file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print signed parameters")
    args = parser.parse_args(argv)

    if args.image_url:
        return asyncio.run(_ping_url(args.image_url, args.verbose))
    return asyncio.run(_ping_file(args.file, args.verbose))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
