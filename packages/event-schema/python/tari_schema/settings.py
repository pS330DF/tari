"""User-adjustable settings sent from the desktop app to the engine."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import Domain, Language, TariModel

TargetColor = Literal["red", "yellow", "purple"]


class CoachingSettings(TariModel):
    language: Language = "en"
    intensity: Literal["low", "balanced", "high"] = "balanced"
    voice_frequency: Literal["off", "minimal", "normal", "frequent"] = "normal"
    strictness: Literal["lenient", "balanced", "strict"] = "balanced"
    overlay_density: Literal["minimal", "standard", "detailed"] = "standard"
    skill_level: Literal["new", "intermediate", "advanced"] = "intermediate"
    focus: list[Domain] = Field(default_factory=lambda: ["aim"])
    training_goals: list[str] = Field(default_factory=list)
    min_confidence: float = Field(default=0.5, ge=0.2, le=0.95)


class PerceptionSettings(TariModel):
    crosshair_color: str = Field(default="#00f0ff", pattern=r"^#[0-9a-fA-F]{6}$")
    target_color: TargetColor = "red"
    hfov_deg: float = Field(default=103.0, ge=60, le=140)
    hud_profile: Literal["training_lab_v1", "none"] = "training_lab_v1"
