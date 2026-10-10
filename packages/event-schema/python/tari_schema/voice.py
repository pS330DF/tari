from __future__ import annotations

from pydantic import Field

from .common import Domain, Language, Priority, VersionedModel


class VoiceInstruction(VersionedModel):
    """A request to speak. P0 system/safety, P1 essential training, P2 tactical, P3 general."""

    voice_id: str
    session_id: str
    created_ts_ms: float
    priority: Priority
    domain: Domain
    text: str = Field(max_length=400)
    language: Language
    dedupe_key: str
    interrupt: bool = False
    ttl_ms: float = Field(description="Discard if not started within this many ms of creation")
    rec_id: str | None = None
