from selfwatch.dedupe import merge
from selfwatch.providers.base import ProviderResult, RawMatch


def test_merge_collapses_canonical_urls_across_providers():
    a = ProviderResult(
        name="prov_a",
        matches=[
            RawMatch(url="https://Example.com/foo/", title="A"),
            RawMatch(url="https://other.com/x"),
        ],
    )
    b = ProviderResult(
        name="prov_b",
        matches=[RawMatch(url="https://www.example.com/foo", thumbnail_url="t.jpg")],
    )

    merged = merge([a, b])

    assert len(merged) == 2
    example = next(m for m in merged if m.domain == "example.com")
    assert sorted(example.sources) == ["prov_a", "prov_b"]
    assert example.title == "A"
    assert example.thumbnail_url == "t.jpg"


def test_merge_sorts_by_source_count_desc():
    a = ProviderResult(name="a", matches=[RawMatch(url="https://shared.com/p")])
    b = ProviderResult(
        name="b",
        matches=[
            RawMatch(url="https://shared.com/p"),
            RawMatch(url="https://solo.com/x"),
        ],
    )
    merged = merge([a, b])
    assert merged[0].domain == "shared.com"
    assert len(merged[0].sources) == 2


def test_merge_handles_empty_results():
    assert merge([]) == []
    assert merge([ProviderResult(name="x", matches=[])]) == []
