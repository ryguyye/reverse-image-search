"""TinEye Search API provider.

Uses HMAC-SHA256 request signing per TinEye's documented spec.
Both `TINEYE_API_KEY` (public) and `TINEYE_PRIVATE_KEY` are required.
"""

import hashlib
import hmac
import secrets
import time
from urllib.parse import quote, urlencode

import httpx

from ..config import settings
from .base import Provider, ProviderResult, RawMatch

TINEYE_URL = "https://api.tineye.com/rest/search/"


def _hmac_sha256(key: str, message: str) -> str:
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def _sign_post_multipart(
    *,
    private_key: str,
    api_key: str,
    image_filename: str,
    content_type: str,
    date: int,
    nonce: str,
) -> str:
    qs = urlencode(sorted({"api_key": api_key, "date": str(date), "nonce": nonce}.items()))
    url = f"{TINEYE_URL}?{qs}"
    string_to_sign = (
        private_key
        + "POST"
        + content_type.lower()
        + quote(image_filename, safe="")
        + str(date)
        + nonce
        + url
    )
    return _hmac_sha256(private_key, string_to_sign)


def _sign_get(
    *,
    private_key: str,
    api_key: str,
    date: int,
    nonce: str,
    extra: dict[str, str] | None = None,
) -> str:
    params: dict[str, str] = {"api_key": api_key, "date": str(date), "nonce": nonce}
    if extra:
        params.update(extra)
    qs = urlencode(sorted(params.items()))
    url = f"{TINEYE_URL}?{qs}"
    string_to_sign = private_key + "GET" + str(date) + nonce + url
    return _hmac_sha256(private_key, string_to_sign)


def _build_multipart(image_bytes: bytes, filename: str) -> tuple[bytes, str, str]:
    boundary = "----selfwatch" + secrets.token_hex(12)
    safe_filename = filename.replace('"', "").replace("\r", "").replace("\n", "")
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image_upload"; filename="{safe_filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    body = head + image_bytes + tail
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type, safe_filename


def _parse_response(data: dict, *, max_results: int) -> ProviderResult:
    code = data.get("code")
    if code is not None and code != 200:
        return ProviderResult(
            name="tineye",
            error=f"TinEye error {code}: {data.get('messages')}",
        )
    matches: list[RawMatch] = []
    for m in (data.get("results") or {}).get("matches") or []:
        thumb = m.get("image_url")
        score = m.get("score")
        domain = m.get("domain")
        for backlink in m.get("backlinks") or []:
            url = backlink.get("backlink") or backlink.get("url")
            if not url:
                continue
            matches.append(RawMatch(url=url, title=domain, thumbnail_url=thumb, score=score))
            if len(matches) >= max_results:
                return ProviderResult(name="tineye", matches=matches)
    return ProviderResult(name="tineye", matches=matches)


class TinEyeProvider(Provider):
    name = "tineye"
    accepts_url = True
    accepts_upload = True

    def is_enabled(self) -> bool:
        return bool(settings.tineye_api_key and settings.tineye_private_key)

    def note(self) -> str | None:
        if not (settings.tineye_api_key and settings.tineye_private_key):
            return "Set TINEYE_API_KEY and TINEYE_PRIVATE_KEY to enable."
        return (
            "Experimental — HMAC signing follows TinEye's documented spec "
            "but is not yet validated against live credentials."
        )

    async def search(
        self,
        client: httpx.AsyncClient,
        *,
        image_url: str | None,
        image_bytes: bytes | None,
        image_filename: str | None,
    ) -> ProviderResult:
        api_key = settings.tineye_api_key
        private_key = settings.tineye_private_key
        if not (api_key and private_key):
            return ProviderResult(name=self.name, error="missing TinEye credentials")

        date = int(time.time())
        nonce = secrets.token_hex(16)

        if image_bytes is not None and image_filename:
            body, content_type, safe_filename = _build_multipart(image_bytes, image_filename)
            api_sig = _sign_post_multipart(
                private_key=private_key,
                api_key=api_key,
                image_filename=safe_filename,
                content_type=content_type,
                date=date,
                nonce=nonce,
            )
            params = {"api_key": api_key, "date": str(date), "nonce": nonce, "api_sig": api_sig}
            try:
                resp = await client.post(
                    TINEYE_URL,
                    params=params,
                    content=body,
                    headers={"Content-Type": content_type},
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                return ProviderResult(name=self.name, error=str(exc))
        elif image_url:
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
            try:
                resp = await client.get(TINEYE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                return ProviderResult(name=self.name, error=str(exc))
        else:
            return ProviderResult(name=self.name, error="tineye requires image bytes or URL")

        return _parse_response(data, max_results=settings.max_results_per_provider)
