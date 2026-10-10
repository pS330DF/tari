"""Longitudinal player profile built only from persisted measurements."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import TariModel, VersionedModel


class SkillDataPoint(TariModel):
    session_id: str
    ts_ms: float
    value: float
    samples: int


class SkillProgress(TariModel):
    skill: str
    label: str
    unit: str
    method: str
    better: Literal["lower", "higher"]
    points: list[SkillDataPoint]
    trend: Literal["improving", "declining", "stable", "insufficient_data"]
    trend_detail: str | None = None


class RecurringIssue(TariModel):
    rule_id: str
    sessions: int
    occurrences: int
    last_ts_ms: float


class PlayerProfile(VersionedModel):
    player_id: str
    generated_ts_ms: float
    sessions_total: int
    validated_sessions: int = Field(description="Sessions with enough measured samples to count toward trends")
    total_exposures: int
    skills: list[SkillProgress]
    recurring_issues: list[RecurringIssue]
    environments: dict[str, int]
    next_focus: str | None = None
    next_focus_reason: str | None = None
