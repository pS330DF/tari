"""Coaching recommendations: every one carries its evidence and calculation method."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Domain, Language, Priority, TariModel, VersionedModel


class Evidence(TariModel):
    metric: str
    value: float
    unit: str
    samples: int = Field(ge=0)
    method: str = Field(description="How the value was calculated, in plain language")
    detail: str | None = None


class Expiration(TariModel):
    ttl_ms: float
    expires_ts_ms: float
    until_event: str | None = Field(default=None, description="Event type that supersedes this recommendation")


class CoachingRecommendation(VersionedModel):
    rec_id: str
    session_id: str
    created_ts_ms: float
    source_frame_id: int
    source_ts_ms: float
    domain: Domain
    rule_id: str
    dedupe_key: str
    priority: Priority
    confidence: float = Field(ge=0, le=1)
    tone: Literal["corrective", "reinforcing", "informational"]
    observation: str
    suggestion: str
    reasoning: str
    short_text: str
    evidence: list[Evidence]
    context: dict[str, str] = Field(default_factory=dict)
    expiration: Expiration
    language: Language
