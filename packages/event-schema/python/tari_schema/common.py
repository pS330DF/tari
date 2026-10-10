"""Primitive types shared by every schema module.

Coordinate convention: unless a field name says otherwise, points and rects are
*normalized* to the source frame (0..1, origin top-left, y down). This keeps
results valid across window resizes and capture-resolution changes.
Timestamps are wall-clock epoch milliseconds (float) named ``*_ts_ms``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .version import SCHEMA_VERSION


class TariModel(BaseModel):
    # Fields with defaults are always present in serialized output, so the exported
    # (serialization-mode) JSON Schema marks them required for TypeScript consumers.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class VersionedModel(TariModel):
    schema_version: str = Field(default=SCHEMA_VERSION)


class Point2(TariModel):
    x: float
    y: float


class Rect(TariModel):
    x: float
    y: float
    w: float
    h: float


class PixelRect(TariModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


Priority = Literal["P0", "P1", "P2", "P3"]
Language = Literal["en", "ko"]
Domain = Literal["aim", "utility", "positioning", "tactical", "agent", "team", "communication", "system"]
ObservationStatus = Literal["observed", "estimated", "unknown", "stale"]

PRIORITY_RANK: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
