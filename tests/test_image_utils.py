from selfwatch.image_utils import compute_phash, hamming_distance


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
