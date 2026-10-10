"""Voice instruction builder: what TARI says, at which priority.

P0 system/safety · P1 essential training feedback · P2 tactical explanation ·
P3 general advice. The voice-frequency setting caps which priorities speak.
Playback (queueing, interruption, duplicate suppression) lives in the client's
voice controller; this side only decides content and priority.
"""

from __future__ import annotations

import uuid

from tari_schema import CoachingRecommendation, CoachingSettings, VoiceInstruction

ALLOWED = {
    "off": set(),
    "minimal": {"P0", "P1"},
    "normal": {"P0", "P1", "P2"},
    "frequent": {"P0", "P1", "P2", "P3"},
}
VOICE_TTL_MS = 4000.0


class VoiceBuilder:
    def __init__(self, session_id: str, settings: CoachingSettings):
        self.session_id = session_id
        self.settings = settings

    def configure(self, settings: CoachingSettings) -> None:
        self.settings = settings

    def from_recommendations(self, recs: list[CoachingRecommendation]) -> list[VoiceInstruction]:
        allowed = ALLOWED[self.settings.voice_frequency]
        return [
            VoiceInstruction(
                voice_id=uuid.uuid4().hex[:16], session_id=self.session_id, created_ts_ms=r.created_ts_ms,
                priority=r.priority, domain=r.domain, text=r.short_text, language=r.language,
                dedupe_key=r.dedupe_key, interrupt=r.priority == "P0", ttl_ms=VOICE_TTL_MS, rec_id=r.rec_id,
            )
            for r in recs if r.priority in allowed
        ]

    def system(self, text: str, key: str, ts_ms: float, priority: str = "P0") -> list[VoiceInstruction]:
        if priority not in ALLOWED[self.settings.voice_frequency] and priority != "P0":
            return []
        if self.settings.voice_frequency == "off":
            return []
        return [VoiceInstruction(
            voice_id=uuid.uuid4().hex[:16], session_id=self.session_id, created_ts_ms=ts_ms,
            priority=priority, domain="system", text=text, language=self.settings.language,  # type: ignore[arg-type]
            dedupe_key=key, interrupt=priority == "P0", ttl_ms=VOICE_TTL_MS,
        )]
