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


class Watch(BaseModel):
    id: int
    name: str
    image_url: str | None = None
    image_filename: str | None = None
    image_phash: str | None = None
    cadence_minutes: int
    webhook_url: str | None = None
    notify_email: str | None = None
    active: bool
    created_at: str
    last_run_at: str | None = None


class WatchCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    cadence_minutes: int = Field(..., ge=5)
    webhook_url: str | None = None
    notify_email: str | None = None
    image_url: str | None = None


class WatchRunResult(BaseModel):
    watch_id: int
    ran_at: str
    providers_used: list[str]
    providers_failed: list[dict]
    new_matches: list[Match]
    webhook_status: str | None = None
    email_status: str | None = None


class WatchUpdate(BaseModel):
    active: bool | None = None


class SeenMatch(BaseModel):
    canonical_url: str
    domain: str | None = None
    title: str | None = None
    thumbnail_url: str | None = None
    sources: list[str] = Field(default_factory=list)
    first_seen_at: str
