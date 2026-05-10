from pydantic import BaseModel, Field


class Match(BaseModel):
    url: str
    domain: str
    title: str | None = None
    thumbnail_url: str | None = None
    sources: list[str] = Field(default_factory=list)
    score: float | None = None


class ScanResponse(BaseModel):
    providers_used: list[str]
    providers_failed: list[dict]
    matches: list[Match]


class ProviderInfo(BaseModel):
    name: str
    enabled: bool
    accepts_url: bool
    accepts_upload: bool
    note: str | None = None
