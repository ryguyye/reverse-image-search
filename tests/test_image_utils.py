from unittest.mock import patch

import httpx
import pytest
import respx

from selfwatch.image_utils import (
    MAX_FETCH_BYTES,
    compute_phash,
    fetch_image_bytes,
    hamming_distance,
    validate_fetch_url,
)


def test_compute_phash_returns_hex_string(image_bytes_red):
    phash = compute_phash(image_bytes_red)
    assert phash is not None
    assert isinstance(phash, str)
    assert len(phash) == 16  # 64-bit hash -> 16 hex chars
    int(phash, 16)  # must be valid hex


def test_compute_phash_returns_none_for_garbage():
    assert compute_phash(b"not an image") is None
    assert compute_phash(b"") is None


def test_hamming_distance_zero_for_identical(image_bytes_red):
    phash = compute_phash(image_bytes_red)
    assert hamming_distance(phash, phash) == 0


def test_hamming_distance_nonzero_for_different(image_bytes_red, image_bytes_blue):
    h_red = compute_phash(image_bytes_red)
    h_blue = compute_phash(image_bytes_blue)
    assert h_red != h_blue
    assert hamming_distance(h_red, h_blue) > 0


def _fake_getaddrinfo(ip: str):
    def _inner(host, port, *args, **kwargs):
        return [(0, 0, 0, "", (ip, 0))]

    return _inner


@pytest.mark.parametrize(
    "scheme",
    ["ftp", "file", "gopher", "javascript"],
)
def test_validate_fetch_url_rejects_non_http_schemes(scheme):
    err = validate_fetch_url(f"{scheme}://example.com/x")
    assert err is not None
    assert "scheme" in err


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",      # loopback
        "10.0.0.5",       # private
        "192.168.1.10",   # private
        "172.16.5.5",     # private
        "169.254.169.254",  # AWS/GCP metadata (link-local)
        "0.0.0.0",        # unspecified
        "224.0.0.1",      # multicast
        "::1",            # IPv6 loopback
        "fc00::1",        # IPv6 unique-local (private)
    ],
)
def test_validate_fetch_url_rejects_non_public_ips(ip):
    with patch("selfwatch.image_utils.socket.getaddrinfo", _fake_getaddrinfo(ip)):
        err = validate_fetch_url("http://victim.example/x")
    assert err is not None
    assert "non-public" in err


def test_validate_fetch_url_accepts_public_ip():
    with patch("selfwatch.image_utils.socket.getaddrinfo", _fake_getaddrinfo("8.8.8.8")):
        assert validate_fetch_url("https://example.com/img.jpg") is None


def test_validate_fetch_url_rejects_unresolvable():
    import socket as _socket

    def boom(*a, **k):
        raise _socket.gaierror("nope")

    with patch("selfwatch.image_utils.socket.getaddrinfo", boom):
        err = validate_fetch_url("https://nx.example/x")
    assert err == "hostname did not resolve"


@respx.mock
async def test_fetch_image_bytes_blocked_by_ssrf_guard():
    # Use a hostname that resolves to loopback.
    with patch("selfwatch.image_utils.socket.getaddrinfo", _fake_getaddrinfo("127.0.0.1")):
        result = await fetch_image_bytes("http://attacker-controlled.example/x")
    assert result is None


@respx.mock
async def test_fetch_image_bytes_streams_within_cap(image_bytes_red):
    with patch("selfwatch.image_utils.socket.getaddrinfo", _fake_getaddrinfo("8.8.8.8")):
        respx.get("https://ok.example/img.png").mock(
            return_value=httpx.Response(200, content=image_bytes_red)
        )
        result = await fetch_image_bytes("https://ok.example/img.png")
    assert result == image_bytes_red


@respx.mock
async def test_fetch_image_bytes_truncates_oversized_stream():
    big = b"\xff" * (MAX_FETCH_BYTES + 256 * 1024)
    with patch("selfwatch.image_utils.socket.getaddrinfo", _fake_getaddrinfo("8.8.8.8")):
        respx.get("https://ok.example/big.bin").mock(
            return_value=httpx.Response(200, content=big)
        )
        result = await fetch_image_bytes("https://ok.example/big.bin")
    assert result is not None
    assert len(result) == MAX_FETCH_BYTES


@respx.mock
async def test_fetch_image_bytes_returns_none_on_http_error():
    with patch("selfwatch.image_utils.socket.getaddrinfo", _fake_getaddrinfo("8.8.8.8")):
        respx.get("https://ok.example/img.png").mock(return_value=httpx.Response(500))
        result = await fetch_image_bytes("https://ok.example/img.png")
    assert result is None
